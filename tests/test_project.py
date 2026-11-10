import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend import analyzer, experiments, server, protocol


class BinderTests(unittest.TestCase):
    def test_shared_uid_requires_name_evidence(self):
        processes = [
            {"upid": 1, "uid": 123, "name": "org.agent", "cmdline": None},
            {"upid": 2, "uid": 123, "name": "org.other", "cmdline": None},
            {"upid": 3, "uid": 456, "name": "org.agent:worker", "cmdline": None},
        ]
        self.assertEqual(analyzer.target_processes(
            processes, "org.agent", 123, {123: {"org.agent", "org.other"}}), {1, 3})

    def test_matched_requests_and_raw_fallback_do_not_count_replies(self):
        matched = [{"binder_txn_id": 8, "client_upid": 1, "client_utid": 3, "client_ts": 11,
                    "server_upid": 2, "server_ts": 20, "server_dur": 7,
                    "is_sync": 1, "binder_reply_id": 9, "client_dur": 90}]
        raw = [{"reply": 0, "utid": 3, "ts": 11, "code": 7},
               {"reply": 1, "utid": 4, "ts": 27, "code": 0},
               {"reply": 0, "utid": 3, "ts": 50, "code": 8, "upid": 1, "name": "org.agent",
                "pid": 2, "uid": 123, "tid": 3, "to_pid": 5, "flags": 1}]
        requests = list(analyzer.extract(matched * 2, raw, {1}))
        self.assertEqual([(r["type"], r["code"]) for r in requests], [("sync", 7), ("async", 8)])
        selected, summary = analyzer.summarize(requests, {1}, 0, 10**9, [], [])
        self.assertEqual(len(selected), 2)
        self.assertEqual(summary["direction_counts"], {"outgoing": 2})
        self.assertEqual(summary["matched_sync_calls"], 1)
        self.assertEqual(summary["unresolved_endpoint_requests"], 1)

    def test_classifier_abstains_without_cross_agent_training(self):
        result = experiments.evaluate([{"agent": "org.agent", "actual": "W0", "features": (0,) * 5}])
        self.assertEqual(result[0]["predicted"], "uncertain")


class FakeRecording:
    def __init__(self, run, folder):
        self.file = folder / "capture.pftrace"

    def start(self):
        pass

    def running(self):
        return True

    def collect(self, stop):
        assert stop
        self.file.write_bytes(b"fixture")
        return self.file


class APITests(unittest.TestCase):
    def test_record_marker_stop_and_export(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(server.collector, "devices", return_value=["phone:123"]), \
                patch.object(server.collector, "packages", return_value={"org.agent": 123}), \
                patch.object(server.collector, "adb", return_value="35"), \
                patch.object(server.collector, "Recording", FakeRecording), \
                patch.object(server.analyzer, "analyze",
                             side_effect=lambda _, run: analyzer.summarize([], {1}, 0, 100,
                                                                           run["markers"], [])):
            with server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler) as http:
                http.token = "test-token"
                http.runs = server.Runs(Path(temp))
                thread = threading.Thread(target=http.serve_forever, daemon=True)
                thread.start()
                try:
                    self.exercise(http.server_port)
                finally:
                    http.shutdown()
                    thread.join()

    def exercise(self, port):
        def request(path, body=None, token="test-token"):
            req = Request(f"http://127.0.0.1:{port}/api/{path}",
                          data=None if body is None else json.dumps(body).encode(),
                          headers={"Authorization": f"Bearer {token}"})
            with urlopen(req, timeout=4) as response:
                return response.read()

        with self.assertRaises(HTTPError) as unauthorized:
            request("runs", token="wrong")
        self.assertEqual(unauthorized.exception.code, 401)
        unauthorized.exception.close()
        params = {"target_package": "org.agent", "workload": "W1", "serial": "phone:123"}
        run_id = json.loads(request("runs", params))["id"]
        path = "runs/" + run_id

        def status(expected):
            for _ in range(100):
                state = json.loads(request(path))
                if state["status"] == expected:
                    return
                if state["status"] == "failed":
                    self.fail(state.get("error"))
                time.sleep(.02)
            self.fail("Run did not reach " + expected)

        status("recording")
        with self.assertRaises(HTTPError) as conflict:
            request("runs", params)
        self.assertEqual(conflict.exception.code, 409)
        conflict.exception.close()
        request(path + "/markers", {"label": "prompt_submitted", "boottime_ns": 20})
        request(path + "/stop", {})
        request(path + "/stop", {})
        status("complete")
        summary = json.loads(request(path + "/summary.json"))
        self.assertEqual(summary["markers"][0]["source"], "android_elapsed_realtime")
        self.assertIn(b"direction", request(path + "/transactions.csv"))
        self.assertEqual(request(path + "/capture.pftrace"), b"fixture")
        request(path + "/outcome", {"outcome": "success"})
        self.assertIn(b"success", request(path + "/metadata.csv"))
        self.assertIn("capture.pftrace", json.loads(request(path + "/artifacts")))
        self.assertFalse(json.loads(request(path + "/quality"))["valid"])
        self.assertEqual(json.loads(request("evaluation.json"))["predictions"], [])

        # Baseline uses the same control/marker API without starting a recorder.
        with patch.object(FakeRecording, "start", side_effect=AssertionError("Baseline started Perfetto")):
            run_id = json.loads(request("runs", {**params, "mode": "baseline"}))["id"]
            path = "runs/" + run_id
            status("recording")
            request(path + "/stop", {})
            status("complete")
            self.assertEqual(set(json.loads(request(path + "/artifacts"))), {"metadata.json", "metadata.csv"})

        # Analysis failures retain captured evidence and expose it for download.
        with patch.object(server.analyzer, "analyze", side_effect=RuntimeError("fixture analysis error")):
            run_id = json.loads(request("runs", params))["id"]
            path = "runs/" + run_id
            status("recording")
            request(path + "/stop", {})
            status("failed")
            self.assertIn("capture.pftrace", json.loads(request(path + "/artifacts")))
            self.assertEqual(request(path + "/capture.pftrace"), b"fixture")


class ProtocolTests(unittest.TestCase):
    def fixture(self, mode="trace", seconds=10, repetition=1):
        markers = [{"label": label, "boottime_ns": int(t * 1e9),
                    "source": "android_elapsed_realtime", "inside_trace": True}
                   for label, t in [("prompt_submitted", 1), ("browser_launched", 1 + seconds)]]
        run = {"id": mode + str(repetition), "mode": mode, "status": "complete",
               "workload": "W1", "outcome": "success", "target_package": "org.agent",
               "browser_package": "org.browser", "markers": markers, "repetition": repetition,
               "device_label": "phone-one", "conditions": "wiki text v1"}
        summary = {"markers": markers, "warnings": [], "trace_duration_seconds": 60,
                   "transaction_count": 1, "rates_per_second": {"incoming": 0, "outgoing": 1 / 60},
                   "peer_process_count": 1, "transaction_types": {"sync": 1},
                   "timeline": [{"incoming": 0, "outgoing": 1, "internal": 0}]}
        return run, summary

    def test_marker_bounds_order_and_missing_completion(self):
        run, summary = self.fixture()
        self.assertTrue(protocol.validate(run, summary)["valid"])
        summary["markers"][1]["inside_trace"] = False
        self.assertFalse(protocol.validate(run, summary)["valid"])
        run, summary = self.fixture(seconds=-1)
        self.assertFalse(protocol.validate(run, summary)["valid"])
        run, summary = self.fixture()
        run["markers"].pop()
        self.assertFalse(protocol.validate(run, summary)["valid"])
        run["outcome"] = "failure"
        self.assertTrue(protocol.validate(run, summary)["valid"])

    def test_idle_minimum_and_voice_response(self):
        run, summary = self.fixture(seconds=29)
        run["workload"] = "W0"
        for marker, label in zip(run["markers"], ("idle_start", "idle_end")):
            marker["label"] = label
        self.assertFalse(protocol.validate(run, summary)["valid"])
        run["markers"][1]["boottime_ns"] += 10**9
        self.assertTrue(protocol.validate(run, summary)["valid"])
        run["workload"] = "W2"
        self.assertIn("Record the actual voice response", protocol.validate(run, summary)["issues"])

    def test_overhead_pairs_and_duplicate_protection(self):
        base, _ = self.fixture("baseline", 10)
        traced, summary = self.fixture("trace", 12)
        result = experiments.overhead([(base, None), (traced, summary)])
        self.assertEqual(result["pairs"][0]["relative_change_percent"], 20)
        self.assertEqual(result["groups"][0]["median_delta_seconds"], 2)
        self.assertEqual(experiments.overhead([(base, None), (traced, summary), (traced, summary)])["pairs"], [])
        traced["device_label"] = "different-phone"
        self.assertEqual(experiments.overhead([(base, None), (traced, summary)])["pairs"], [])

    def test_failed_tasks_preserved_and_bad_markers_excluded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index in range(2):
                run, summary = self.fixture(repetition=index + 1)
                if index == 0:
                    run["outcome"] = "failure"
                else:
                    summary["markers"][1]["inside_trace"] = False
                folder = root / run["id"]
                folder.mkdir()
                (folder / "metadata.json").write_text(json.dumps(run))
                (folder / "summary.json").write_text(json.dumps(summary))
            result = experiments.report(root)
            self.assertEqual(len(result["run_comparisons"]), 2)
            self.assertEqual(result["predictions"], [])
            self.assertEqual(len(result["excluded_runs"]), 2)
            self.assertEqual(result["coverage"][1]["outcomes"], {"failure": 1})

    def test_classifier_recovers_separated_workloads_and_abstains_on_ties(self):
        samples = [{"agent": a, "actual": w, "features": (float(i),) * 5}
                   for a in ("agent-a", "agent-b") for i, w in enumerate(experiments.WORKLOADS)]
        self.assertTrue(all(p["predicted"] == p["actual"] for p in experiments.evaluate(samples)))
        for s in samples:
            s["features"] = (0,) * 5
        self.assertTrue(all(p["predicted"] == "uncertain" for p in experiments.evaluate(samples)))
