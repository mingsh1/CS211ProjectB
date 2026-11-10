"""LAN API and experiment coordinator."""
import argparse
import copy
import csv
import hmac
import json
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import analyzer, collector, experiments, protocol, browser_detection, resources

WEB = Path(__file__).with_name("web")
PACKAGE = re.compile(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+")
RUN_ID = re.compile(r"[0-9a-f]{32}")
TERMINAL = {"complete", "failed"}
EXPORTS = {"metadata.json", "metadata.csv", "summary.json", "summary.csv", "transactions.json",
           "transactions.csv", "edges.csv", "timeline.csv", "capture.pftrace",
           "resources.json", "resources.csv", "resources_summary.json"}


def now():
    return datetime.now(timezone.utc).isoformat()


class APIError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class Runs:
    def __init__(self, root):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.runs = {}
        self.stops = {}
        for path in root.glob("*/metadata.json"):
            if not RUN_ID.fullmatch(path.parent.name):
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if data["status"] not in TERMINAL:
                data.update(error="Backend restarted before completion.", failed_stage=data["status"],
                            status="failed", finished_at=now())
                analyzer.save_json(path, data)
            self.runs[data["id"]] = data

    def folder(self, run_id):
        return self.root / run_id

    def get(self, run_id):
        with self.lock:
            if run_id not in self.runs:
                raise APIError(404, "Run not found.")
            return copy.deepcopy(self.runs[run_id])

    def list(self):
        with self.lock:
            return [copy.deepcopy(run) for run in sorted(self.runs.values(),
                    key=lambda item: item["created_at"], reverse=True)]

    def artifacts(self, run_id):
        run = self.get(run_id)
        names = ["metadata.json", "metadata.csv"]
        if run["status"] in TERMINAL:
            names.extend(name for name in sorted(EXPORTS - set(names))
                         if (self.folder(run_id) / name).is_file())
            if "summary.json" in names:
                names.append("summary.csv")
        return names

    def quality(self, run_id):
        run = self.get(run_id)
        if run.get("mode") in resources.MODES:
            path = self.folder(run_id) / "resources_summary.json"
            issues = []
            if path.is_file():
                result = json.loads(path.read_bytes())
                issues.extend(result["issues"])
                if any(v["median"] is None for v in result["metrics"].values()):
                    issues.append("Some resource metrics are unavailable; inspect resource results")
                if result["battery"]["reason"]:
                    issues.append(result["battery"]["reason"])
            else:
                issues.append("No resource summary is available")
            if run["status"] != "complete":
                issues.append("Resource capture has not completed")
            if run.get("outcome") != "success":
                issues.append("Confirm the resource scenario outcome before comparison")
            return {"valid": not issues, "issues": issues, "task_duration_seconds": None}
        path = self.folder(run_id) / "summary.json"
        summary = json.loads(path.read_bytes()) if path.is_file() else None
        result = protocol.validate(run, summary)
        if run["status"] != "complete":
            result["issues"].append("Experiment has not completed")
        if run.get("mode", "trace") == "trace" and summary is None:
            result["issues"].append("No communication summary is available")
        result["valid"] = not result["issues"]
        return result

    def update(self, run_id, **changes):
        with self.lock:
            run = {**self.runs[run_id], **changes}
            analyzer.save_json(self.folder(run_id) / "metadata.json", run)
            self.runs[run_id] = run

    def start(self, body, client="desktop"):
        package = body.get("target_package", "")
        workload = body.get("workload")
        duration = body.get("duration_seconds", 40 if workload == "W0" else 90)
        serial = body.get("serial")
        repetition = body.get("repetition", 1)
        mode = body.get("mode", "trace")
        context = {key: body.get(key, "") for key in ("device_label", "conditions")}
        resource_mode = mode in resources.MODES
        if mode not in ("trace", "baseline", *resources.MODES) or any(
                not isinstance(v, str) or len(v) > 200 for v in context.values()):
            raise APIError(400, "Select a supported mode; context fields must be at most 200 characters.")
        interval = body.get("sample_interval_seconds", 15)
        settling = body.get("settle_seconds", 30)
        if resource_mode:
            if client != "desktop":
                raise APIError(400, "Start all resource arms from the laptop browser; the Agent-only arm closes the APK.")
            if package == resources.CONTROLLER:
                raise APIError(400, "Select an Agent distinct from the Project B controller.")
            if not all(v.strip() for v in context.values()):
                raise APIError(400, "Resource comparisons need a stable phone label and documented conditions.")
            if type(interval) is not int or not 10 <= interval <= 60 or type(settling) is not int or not 10 <= settling <= 120:
                raise APIError(400, "Use a 10–60 second sample interval and 10–120 second settling delay.")
            if mode == "resource_agent" and body.get("controller_stop_ack") is not True:
                raise APIError(400, "Acknowledge that Agent-only stops the Project B controller on the selected phone.")
        if not isinstance(package, str) or not PACKAGE.fullmatch(package):
            raise APIError(400, "Enter an installed Android package name.")
        low, high = (30, 540) if resource_mode else (5, 180)
        if workload not in ("W0", "W1", "W2") or type(duration) is not int or not low <= duration <= high:
            raise APIError(400, f"Select W0, W1 or W2 and a duration of {low}–{high} seconds.")
        if resource_mode and duration < 2 * interval:
            raise APIError(400, "Resource duration must be at least twice the sampling interval.")
        if type(repetition) is not int or not 1 <= repetition <= 100:
            raise APIError(400, "Enter a repetition number of 1–100.")
        if not isinstance(serial, str) or not serial:
            raise APIError(400, "Select an ADB device.")
        if serial not in collector.devices():
            raise APIError(400, "Selected ADB device is unavailable.")
        with self.lock:
            if any(run["status"] not in TERMINAL for run in self.runs.values()):
                raise APIError(409, "An experiment is already active.")
            run_id = uuid.uuid4().hex
            self.folder(run_id).mkdir()
            run = dict(id=run_id, status="preparing", serial=serial, target_package=package,
                       workload=workload, duration_seconds=duration, repetition=repetition,
                       created_at=now(), markers=[], outcome=None, notes="", browser_package="",
                       recognized_text="", actual_response="")
            run.update(mode=mode, **context)
            if resource_mode:
                run.update(sample_interval_seconds=interval, settle_seconds=settling,
                           observer=resources.VERSION, controller_stop_ack=body.get("controller_stop_ack", False))
            analyzer.save_json(self.folder(run_id) / "metadata.json", run)
            self.runs[run_id] = run
            stop = self.stops[run_id] = threading.Event()
            threading.Thread(target=self.run, args=(run_id, stop), daemon=True).start()
            return self.get(run_id)

    def run(self, run_id, stop):
        stage = "preparing"
        try:
            run = self.get(run_id)
            folder = self.folder(run_id)
            serial, package = run["serial"], run["target_package"]
            packages = collector.packages(serial)
            if package not in packages:
                raise RuntimeError("Target package is not installed for the current Android user.")
            self.update(run_id, target_uid=packages[package], packages=packages,
                        android_sdk=collector.adb("shell", "getprop", "ro.build.version.sdk", serial=serial))
            if run.get("mode") in resources.MODES:
                stage = "resources"
                trace = resources.capture(run, folder, stop, lambda **changes: self.update(run_id, **changes))
                self.update(run_id, status="complete", finished_at=now(),
                            trace_bytes=trace.stat().st_size if trace else None)
                return
            recording = collector.Recording(run, folder)
            baseline = run.get("mode") == "baseline"
            if not baseline:
                recording.start()
            stage = "recording"
            self.update(run_id, status=stage, recording_at=now())
            deadline = time.monotonic() + run["duration_seconds"] + 2
            while not stop.wait(.4) and time.monotonic() < deadline and (baseline or recording.running()):
                pass
            if baseline:
                self.update(run_id, status="complete", finished_at=now())
                return
            stage = "collecting"
            self.update(run_id, status=stage)
            trace = recording.collect(stop.is_set())
            self.update(run_id, trace_bytes=trace.stat().st_size)
            stage = "analyzing"
            self.update(run_id, status=stage)
            started = time.monotonic()
            analyzer.export(folder, *analyzer.analyze(trace, self.get(run_id)))
            self.update(run_id, status="complete", finished_at=now(),
                        analysis_wall_seconds=time.monotonic() - started)
        except Exception as exc:
            self.update(run_id, status="failed", failed_stage=stage, error=str(exc), finished_at=now())
        finally:
            with self.lock:
                self.stops.pop(run_id, None)

    def stop(self, run_id):
        with self.lock:
            run = self.get(run_id)
            if run["status"] in {"preparing", "settling", "recording"}:
                self.stops[run_id].set()
            return run

    def marker(self, run_id, body):
        label = body.get("label")
        if not isinstance(label, str) or not label.strip() or len(label) > 80:
            raise APIError(400, "Enter a marker label of 1–80 characters.")
        run = self.get(run_id)
        if run.get("mode") in resources.MODES:
            raise APIError(409, "Resource runs use a fixed window and laptop ground truth, not phone markers.")
        if run["status"] != "recording":
            raise APIError(409, "Markers require an active recording.")
        phone_time = body.get("boottime_ns")
        if type(phone_time) is int and 0 < phone_time < 10**17:
            clock = {"boottime_ns": phone_time, "source": "android_elapsed_realtime"}
        else:
            clock = collector.Recording(run, self.folder(run_id)).mark()
            clock["source"] = "adb_uptime_sample"
        marker = {"label": label.strip(), "received_at": now(), **clock}
        with self.lock:
            run = self.get(run_id)
            if run["status"] != "recording":
                raise APIError(409, "Recording ended before the marker was saved.")
            self.update(run_id, markers=[*run["markers"], marker])
            if marker["label"] == "browser_launched":
                self.update(run_id, browser_detection={"status": "pending", "marker_received_at": marker["received_at"]})
        if marker["label"] == "browser_launched":
            threading.Thread(target=self.detect_browser, args=(run_id, marker), daemon=True).start()
        return marker

    def detect_browser(self, run_id, marker):
        run = self.get(run_id)
        try:
            result = browser_detection.detect(run["serial"], run["target_package"])
        except Exception as exc:
            result = {"status": "unavailable", "reason": "Browser detection failed: " + str(exc)}
        result.update(checked_at=now(), marker_received_at=marker["received_at"],
                      marker_boottime_ns=marker["boottime_ns"])
        with self.lock:
            run = self.get(run_id)
            if run.get("browser_detection", {}).get("marker_received_at") != marker["received_at"]:
                return  # A newer browser marker owns the current detection request.
            changes = {"browser_detection": result}
            if result["status"] == "detected" and not run.get("browser_package") \
                    and run.get("browser_package_source") != "manual":
                changes.update(browser_package=result["package"], browser_package_source="foreground_after_marker")
            self.update(run_id, **changes)

    def outcome(self, run_id, body):
        if body.get("outcome") not in ("success", "failure", "timeout", "unexpected_activity"):
            raise APIError(400, "Choose an experiment outcome.")
        fields = {"outcome": body["outcome"]}
        for key in ("notes", "browser_package", "recognized_text", "actual_response"):
            value = body.get(key, "")
            if not isinstance(value, str) or len(value) > 2000:
                raise APIError(400, f"Invalid {key}.")
            fields[key] = value
        with self.lock:
            run = self.get(run_id)
            if fields["browser_package"] != run.get("browser_package", ""):
                fields["browser_package_source"] = "manual"
            self.update(run_id, **fields)
        return self.get(run_id)


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body, kind="application/json", filename=None):
        data = json.dumps(body, ensure_ascii=False).encode() if kind == "application/json" and not isinstance(body, bytes) else body
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 <= length <= 16384:
                raise ValueError()
            data = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (ValueError, UnicodeError) as exc:
            raise APIError(400, "Expected a JSON object of at most 16 KiB.") from exc

    def route(self):
        path = urlsplit(self.path).path
        method = self.command
        static = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                  "/style.css": ("style.css", "text/css")}
        if method == "GET" and path in static:
            file, kind = static[path]
            return self.respond(200, (WEB / file).read_bytes(), kind + "; charset=utf-8")
        if not hmac.compare_digest(self.headers.get("Authorization", "").encode(),
                                   f"Bearer {self.server.token}".encode()):
            raise APIError(401, "Enter the backend access token.")
        runs = self.server.runs
        if method == "GET" and path == "/api/devices":
            return self.respond(200, collector.devices())
        if method == "GET" and path == "/api/runs":
            return self.respond(200, runs.list())
        if method == "GET" and path == "/api/evaluation.json":
            with runs.lock:
                result = experiments.report(runs.root)
            return self.respond(200, result, filename="evaluation.json")
        if method == "POST" and path == "/api/runs":
            return self.respond(202, runs.start(self.body(), self.headers.get("X-ProjectB-Client", "desktop")))
        parts = path.strip("/").split("/")
        if parts == ["api", "devices", "resource-capabilities"] and method == "POST":
            body = self.body()
            serial, package = body.get("serial"), body.get("package")
            if not isinstance(serial, str) or serial not in collector.devices():
                raise APIError(400, "Selected ADB device is unavailable.")
            if not isinstance(package, str) or not PACKAGE.fullmatch(package):
                raise APIError(400, "Enter a valid Agent package.")
            with runs.lock:
                if any(r["status"] not in TERMINAL for r in runs.runs.values()):
                    raise APIError(409, "Run capability checks only when no experiment is active.")
                return self.respond(200, resources.capabilities(serial, package))
        if parts == ["api", "devices", "package-details"] and method == "POST":
            body = self.body()
            serial, package = body.get("serial"), body.get("package")
            if not isinstance(serial, str) or serial not in collector.devices():
                raise APIError(400, "Selected ADB device is unavailable.")
            if not isinstance(package, str) or not PACKAGE.fullmatch(package):
                raise APIError(400, "Enter a valid package name.")
            try:
                return self.respond(200, collector.package_details(serial, package))
            except ValueError as exc:
                raise APIError(400, str(exc)) from exc
        if parts[:2] == ["api", "devices"] and parts[2:] == ["packages"] and method == "POST":
            serial = self.body().get("serial")
            if not isinstance(serial, str) or serial not in collector.devices():
                raise APIError(400, "Selected ADB device is unavailable.")
            return self.respond(200, sorted(collector.packages(serial)))
        if parts[:2] != ["api", "runs"] or len(parts) < 3 or not RUN_ID.fullmatch(parts[2]):
            raise APIError(404, "Unknown endpoint.")
        run_id, action = parts[2], parts[3:]
        if method == "GET" and not action:
            return self.respond(200, runs.get(run_id))
        if method == "GET" and action == ["artifacts"]:
            return self.respond(200, runs.artifacts(run_id))
        if method == "GET" and action == ["quality"]:
            return self.respond(200, runs.quality(run_id))
        if method == "POST" and action == ["stop"]:
            return self.respond(202, runs.stop(run_id))
        if method == "POST" and action == ["markers"]:
            return self.respond(201, runs.marker(run_id, self.body()))
        if method == "POST" and action == ["outcome"]:
            return self.respond(200, runs.outcome(run_id, self.body()))
        if method == "GET" and len(action) == 1 and action[0] in EXPORTS:
            run = runs.get(run_id)
            name = action[0]
            kind = {"csv": "text/csv", "json": "application/json",
                    "pftrace": "application/octet-stream"}[name.split(".")[-1]]
            file = runs.folder(run_id) / name
            if name == "metadata.csv":
                data = run
            elif name == "summary.csv" and run["status"] in TERMINAL and file.with_suffix(".json").is_file():
                data = json.loads(file.with_suffix(".json").read_bytes())
            elif file.is_file() and (run["status"] in TERMINAL or name == "metadata.json"):
                return self.respond(200, file.read_bytes(), kind, name)
            else:
                raise APIError(409, "This export is not available yet.")
            import io
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["field", "value_json"])
            writer.writerows((key, json.dumps(value, ensure_ascii=False)) for key, value in data.items())
            return self.respond(200, buffer.getvalue().encode(), kind, name)
        raise APIError(404, "Unknown endpoint.")

    def dispatch(self):
        try:
            self.route()
        except APIError as exc:
            self.respond(exc.status, {"error": str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            self.respond(500, {"error": str(exc)})

    do_GET = dispatch
    do_POST = dispatch


def access_token(root):
    """Reuse a short pairing code across backend restarts on the lab LAN."""
    override = os.environ.get("CS211_ACCESS_TOKEN")
    if override:
        return override
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".access-token"
    try:
        with path.open("x", encoding="utf-8") as file:
            token = f"{secrets.randbelow(1_000_000):06d}"
            file.write(token + "\n")
    except FileExistsError:
        pass
    token = path.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9]{6}", token):
        raise ValueError(f"Invalid saved access code in {path}. Set CS211_ACCESS_TOKEN or remove this file to generate a new code.")
    return token


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--runs", type=Path, default=Path("runs"))
    args = parser.parse_args()
    token = access_token(args.runs)
    with ThreadingHTTPServer((args.host, args.port), Handler) as server:
        server.token = token
        server.runs = Runs(args.runs)
        print(f"Project B at http://{args.host}:{args.port} | Access token: {token}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
