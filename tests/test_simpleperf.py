import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend import simpleperf, server, experiments


def run_fixture():
    return dict(id="a" * 32, serial="phone", target_package="org.agent", duration_seconds=40,
                workload="W0", mode="trace", status="preparing", created_at="2026-11-15",
                simpleperf_requested=True, markers=[], repetition=1)


def adb_fixture(app_type="profileable", uid="2000", processes="123 org.agent"):
    def adb(*args, **kwargs):
        assert kwargs["serial"] == "phone"
        if args[1:] == ("id", "-u"): return uid
        if args[1:3] == ("am", "get-current-user"): return "0"
        if args[1] == "getprop": return "16"
        if args[1] == "simpleperf_app_runner": return app_type
        if args[1:] == (simpleperf.BINARY, "--version"): return "Simpleperf"
        if args[1:] == (simpleperf.BINARY, "help", "record"): return "--start_profiling_fd --clockid"
        if args[1] == "timeout": return "timeout help"
        if args[1] == "ps": return "PID NAME\n" + processes
        raise AssertionError(args)
    return adb


class SimpleperfTests(unittest.TestCase):
    def test_preflight_policy_and_running_process(self):
        for kind, uid, processes, eligible in (
            ("profileable", "2000", "123 org.agent", True),
            ("debuggable", "2000", "123 org.agent:worker", True),
            ("non_profileable", "2000", "123 org.agent", False),
            ("profileable", "0", "123 org.agent", False),
            ("profileable", "2000", "123 org.agent.other", False),
        ):
            with self.subTest(kind=kind, uid=uid, processes=processes), patch.object(
                    simpleperf.collector, "adb", side_effect=adb_fixture(kind, uid, processes)):
                self.assertEqual(simpleperf.capabilities("phone", "org.agent")["eligible"], eligible)

    def test_missing_tool_and_invalid_package(self):
        with patch.object(simpleperf.collector, "adb", side_effect=RuntimeError("not found")):
            self.assertFalse(simpleperf.capabilities("phone", "org.agent")["eligible"])
        with self.assertRaises(ValueError): simpleperf.capabilities("phone", "org.agent; id")

    def test_denial_saves_evidence_without_launch(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(simpleperf, "capabilities", return_value={
                "eligible": False, "reason": "not profileable"}), patch.object(simpleperf.subprocess, "Popen") as launch:
            rec = simpleperf.Recording(run_fixture(), Path(temp), Mock())
            rec.start(); rec.finish()
            launch.assert_not_called()
            self.assertEqual(json.loads((Path(temp) / "simpleperf.json").read_text())["status"], "unavailable")

    def test_capture_command_readiness_stop_and_report(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(simpleperf, "capabilities", return_value={"eligible": True}):
            folder = Path(temp)
            rec = simpleperf.Recording(run_fixture(), folder, Mock())
            proc = Mock(stdout=io.BytesIO(b"PROJECTB_PID=321\r\nSTARTED"), returncode=0)
            proc.poll.return_value = None
            def wait(**kwargs): proc.poll.return_value = 0
            proc.wait.side_effect = wait
            def adb(*args, **kwargs):
                self.assertEqual(kwargs["serial"], "phone")
                if args[:2] == ("shell", "cat"): return simpleperf.BINARY + "\0" + rec.remote
                if args[:3] == ("shell", "kill", "-INT"): return ""
                if args[0] == "pull": Path(args[2]).write_bytes(b"PERFILE2" + b"fixture"); return ""
                if "report" in args: return "Samples: 123\nOverhead  Command  Symbol\n100.0% org.agent function"
                if args[:3] == ("shell", "rm", "-f"): return ""
                raise AssertionError(args)
            with patch.object(simpleperf.subprocess, "Popen", return_value=proc) as launch, \
                    patch.object(simpleperf.collector, "adb", side_effect=adb) as calls:
                rec.start()
                self.assertEqual(rec.result["status"], "recording")
                command = launch.call_args.args[0]
                self.assertEqual(command[:5], ["adb", "-s", "phone", "shell", "-T"])
                self.assertIn("--app org.agent", command[-1])
                self.assertIn("--size-limit 64M", command[-1])
                rec.request_stop(); rec.finish(); rec.finish()
                self.assertEqual(rec.result["status"], "complete")
                self.assertEqual(rec.result["sample_count"], 123)
                self.assertEqual(sum(c.args[:2] == ("shell", "kill") for c in calls.call_args_list), 1)
                self.assertTrue((folder / "simpleperf_report.txt").is_file())

    def test_stop_refuses_reused_pid(self):
        with tempfile.TemporaryDirectory() as temp:
            rec = simpleperf.Recording(run_fixture(), Path(temp), Mock())
            rec.proc = Mock(); rec.proc.poll.return_value = None; rec.pid = "321"
            with patch.object(simpleperf.collector, "adb", return_value="unrelated.process") as adb:
                rec.request_stop()
                self.assertEqual(adb.call_count, 1)
                self.assertIn("ownership", rec.result["issues"][0])

    def test_empty_partial_and_report_failure_preserve_raw_data(self):
        for text, code, expected in (("Samples: 0", 0, "empty"), ("Samples: 2", 1, "partial"),
                                     (None, 0, "recorded")):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp); rec = simpleperf.Recording(run_fixture(), folder, Mock())
                rec.proc = Mock(returncode=code); rec.proc.poll.return_value = code
                rec.reader = Mock(); rec.ready.set(); rec.stop_requested = True
                def adb(*args, **kwargs):
                    if args[0] == "pull": Path(args[2]).write_bytes(b"PERFILE2fixture"); return ""
                    if "report" in args:
                        if text is None: raise RuntimeError("report denied")
                        return text
                    return ""
                with patch.object(simpleperf.collector, "adb", side_effect=adb): rec.finish()
                self.assertEqual(rec.result["status"], expected)
                self.assertTrue((folder / "simpleperf.data").exists())

    def test_diagnostic_runs_excluded_from_formal_comparisons(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); folder = root / ("a" * 32); folder.mkdir()
            run = run_fixture(); run.update(status="complete", outcome="success")
            (folder / "metadata.json").write_text(json.dumps(run))
            report = experiments.report(root)
            self.assertEqual(len(report["simpleperf_runs"]), 1)
            self.assertEqual(report["coverage"], [])
            self.assertEqual(report["overhead"]["pairs"], [])

    def test_invalid_modes_rejected_before_device_commands(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(server.collector, "devices") as devices:
            manager = server.Runs(Path(temp))
            for mode, enabled in (("baseline", True), ("resource_agent", False), ("resource_controller", False), ("resource_trace", False), ("trace", "true")):
                with self.assertRaises(server.APIError): manager.start({**run_fixture(), "mode": mode, "simpleperf_enabled": enabled})
            devices.assert_not_called()

    def test_denied_sampling_does_not_fail_binder_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manager = server.Runs(root); run = run_fixture()
            folder = root / run["id"]; folder.mkdir(); trace = folder / "capture.pftrace"; trace.write_bytes(b"fixture")
            manager.runs[run["id"]] = run
            perfetto = Mock(); perfetto.running.return_value = False; perfetto.collect.return_value = trace
            with patch.object(server.collector, "packages", return_value={"org.agent": 10001}), \
                    patch.object(server.collector, "adb", return_value="36"), \
                    patch.object(server.collector, "Recording", return_value=perfetto), \
                    patch.object(simpleperf, "capabilities", return_value={"eligible": False, "reason": "denied"}), \
                    patch.object(server.analyzer, "analyze", return_value=([], {})), \
                    patch.object(server.analyzer, "export"):
                stop = threading.Event(); stop.set(); manager.run(run["id"], stop)
            result = manager.get(run["id"])
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["simpleperf"]["status"], "unavailable")

    def test_authenticated_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); run = run_fixture(); run["status"] = "complete"
            folder = root / run["id"]; folder.mkdir()
            (folder / "metadata.json").write_text(json.dumps(run))
            for name in simpleperf.EXPORTS: (folder / name).write_bytes(b'{}')
            with server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler) as http:
                http.token = "test"; http.runs = server.Runs(root)
                worker = threading.Thread(target=http.serve_forever, daemon=True); worker.start()
                try:
                    base = f"http://127.0.0.1:{http.server_port}/api/runs/{run['id']}/"
                    for name in simpleperf.EXPORTS:
                        with urlopen(Request(base + name, headers={"Authorization": "Bearer test"}), timeout=3) as response:
                            self.assertEqual(response.status, 200)
                    with self.assertRaises(HTTPError) as err: urlopen(base + "simpleperf.data", timeout=3)
                    self.assertEqual(err.exception.code, 401); err.exception.close()
                finally: http.shutdown(); worker.join()
