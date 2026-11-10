import copy
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend import resources, server, experiments


def run_fixture(mode="resource_controller"):
    return {"id": "a" * 32, "mode": mode, "target_package": "org.agent", "serial": "phone",
            "duration_seconds": 300, "sample_interval_seconds": 15, "settle_seconds": 30,
            "device_label": "phone-1", "conditions": "idle screen50 wifi", "workload": "W0",
            "repetition": 1, "status": "complete", "outcome": "success",
            "resource_identity": {"build": "fixture-build", "agent": {"version": "1"},
                                  "controller": {"version": "1.4"}, "trace_config_sha256": "fixture"}}


def sample_fixture(offset=150, controller=True, charge=3999500):
    return {"offset_seconds": offset, "cpu_read_offset_seconds": offset + .1,
            "battery_read_offset_seconds": offset + .5, "probe_wall_seconds": 1,
            "agent_present": True, "controller_present": controller, "processes": [],
            "cpu": {"from_ago_ms": 4000, "to_ago_ms": 0, "system_cpu_reported_percent": 10,
                    "agent_cpu_one_core_percent": 20, "controller_cpu_one_core_percent": 2 if controller else 0},
            "agent_pss_kib": 30000, "controller_pss_kib": 10000 if controller else 0, "system_used_kib": 400000,
            "battery": {"charge_uah": charge, "voltage_mv": 4000, "level": 80, "scale": 100,
                        "status": 3, "powered": False, "simulated": False}, "raw": {}}


class ResourceParsingTests(unittest.TestCase):
    def test_cpu_subprocesses_one_core_and_missing_not_zero(self):
        text = "CPU usage from 4000ms to 0ms ago:\n  125% 1/org.agent: 100% user + 25% kernel\n  4.5% 2/org.agent:worker: 4% user\n  9% 3/org.agent.other: 9% user\n20% TOTAL: 10% user + 10% kernel"
        parsed = resources.parse_cpu(text, "org.agent")
        self.assertEqual(parsed["agent_cpu_one_core_percent"], 129.5)
        self.assertIsNone(parsed["controller_cpu_one_core_percent"])
        self.assertEqual(parsed["system_cpu_reported_percent"], 20)

    def test_memory_process_blocks_not_double_counted(self):
        text = "** MEMINFO in pid 1 [org.agent] **\n TOTAL 100 5 2\n TOTAL PSS: 100 TOTAL RSS: 500\n** MEMINFO in pid 2 [org.agent:worker] **\n TOTAL PSS: 200 TOTAL RSS: 900"
        self.assertEqual(resources.parse_pss(text), 300)
        self.assertIsNone(resources.parse_pss("Permission Denial"))
        self.assertEqual(resources.parse_memory("MemTotal: 1000 kB\nMemAvailable: 400 kB"), 600)
        self.assertIsNone(resources.parse_processes("permission denied"))

    def test_capability_errors_are_explicit_not_zeros(self):
        with patch.object(resources.collector, "adb", side_effect=RuntimeError("denied")):
            r = resources.capabilities("phone", "org.agent")
        self.assertFalse(r["cpu_available"])
        self.assertFalse(r["charge_counter_available"])
        self.assertIsNone(r["sample"]["controller_present"])
        self.assertIsNone(r["sample"]["agent_pss_kib"])
        self.assertEqual(r["sample"]["raw"]["cpu"]["error"], "denied")

    def test_battery_units_and_whole_device_estimate(self):
        samples = [sample_fixture(0, charge=4000000), sample_fixture(150), sample_fixture(300, charge=3999000)]
        r = resources.battery_summary(samples)
        self.assertEqual(r["charge_used_uah"], 1000)
        self.assertEqual(r["estimated_energy_mwh"], 4)
        self.assertEqual(r["estimated_mean_power_mw"], 48)
        parsed = resources.parse_battery("AC powered: false\nUSB powered: true\nWireless powered: false\nCharge counter: 4000000\nvoltage: 4000\nstatus: 2\nlevel: 80\nscale: 100")
        self.assertTrue(parsed["powered"])
        self.assertEqual(parsed["charge_uah"], 4000000)

    def test_battery_invalid_states_never_report_zero_overhead(self):
        for change in ("charging", "short", "unchanged", "counter_reset", "unsupported", "simulated"):
            with self.subTest(change=change):
                samples = [sample_fixture(0, charge=4000000), sample_fixture(300, charge=3999000)]
                if change == "charging": samples[1]["battery"]["powered"] = True
                if change == "short": samples[1]["battery_read_offset_seconds"] = 30
                if change == "unchanged": samples[1]["battery"]["charge_uah"] = 4000000
                if change == "counter_reset": samples[1]["battery"]["charge_uah"] = 4001000
                if change == "unsupported": samples[1]["battery"]["charge_uah"] = 0
                if change == "simulated": samples[0]["battery"]["simulated"] = True
                result = resources.battery_summary(samples)
                self.assertIsNone(result["estimated_energy_mwh"])
                self.assertTrue(result["reason"])

    def test_stale_cpu_and_controller_contamination(self):
        samples = [sample_fixture(0), sample_fixture(15), sample_fixture(16)]
        summary = resources.summarize(run_fixture("resource_agent"), samples, 301, True)
        self.assertEqual(summary["cpu_rejected_samples"], 2)
        self.assertIsNone(summary["metrics"]["system_cpu_reported_percent"]["median"])
        self.assertIn("Controller process presence does not match the selected arm", summary["issues"])
        asleep = [sample_fixture(15), sample_fixture(30)]
        for sample in asleep:
            sample["cpu"]["awake_percent"] = 50
        result = resources.summarize(run_fixture(), asleep, 301, True)
        self.assertEqual(result["cpu_rejected_samples"], 2)
        self.assertIsNone(result["metrics"]["system_cpu_reported_percent"]["median"])


class ResourceCaptureTests(unittest.TestCase):
    def test_three_arms_and_no_target_app_force_stop(self):
        for mode in resources.MODES:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                clock = [0.0]
                class Stop:
                    def wait(self, seconds): clock[0] += seconds; return False
                    def is_set(self): return False
                class Probe:
                    def __init__(self, *args): pass
                    def sample(self, start):
                        result = sample_fixture(clock[0] - start, controller=mode != "resource_agent")
                        clock[0] += 1
                        return result
                class Recording:
                    pid = None
                    def __init__(self, run, folder): self.folder = folder
                    def start(self): self.pid = "42"
                    def collect(self, stop):
                        self.file = self.folder / "capture.pftrace"
                        self.file.write_bytes(b"fixture")
                        return self.file
                run = run_fixture(mode)
                run.update(duration_seconds=30, sample_interval_seconds=10, settle_seconds=10)
                with patch.object(resources.time, "monotonic", side_effect=lambda: clock[0]), \
                     patch.object(resources, "Probe", Probe), patch.object(resources.collector, "Recording", Recording), \
                     patch.object(resources.collector, "package_details", return_value={"version": "1"}), \
                     patch.object(resources.collector, "adb", return_value="build") as adb:
                    trace = resources.capture(run, Path(temp), Stop(), lambda **kw: None)
                self.assertEqual(trace is not None, mode == "resource_trace")
                calls = [c.args for c in adb.call_args_list if "force-stop" in c.args]
                self.assertEqual(calls, [("shell", "am", "force-stop", resources.CONTROLLER)] if mode == "resource_agent" else [])
                result = json.loads((Path(temp) / "resources_summary.json").read_text())
                self.assertEqual(result["sample_count"], 4)
                self.assertNotIn("Fixed measurement window was interrupted", result["issues"])

    def test_early_stop_is_excluded(self):
        r = resources.summarize(run_fixture(), [sample_fixture()], 10, False)
        self.assertIn("Fixed measurement window was interrupted", r["issues"])


class ResourceComparisonTests(unittest.TestCase):
    def write_arm(self, root, mode, value, suffix=""):
        run = run_fixture(mode)
        run["id"] = mode + suffix
        folder = root / run["id"]
        folder.mkdir()
        summary = resources.summarize(run, [sample_fixture(150, mode != "resource_agent"), sample_fixture(300, mode != "resource_agent")], 301, True)
        summary["metrics"]["system_cpu_reported_percent"]["median"] = value
        (folder / "metadata.json").write_text(json.dumps(run))
        (folder / "resources_summary.json").write_text(json.dumps(summary))
        if mode == "resource_trace": (folder / "capture.pftrace").write_bytes(b"fixture")
        return folder

    def test_signed_three_arm_differences_and_legacy_isolation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for mode, value in zip(resources.MODES, (10, 12, 11)): self.write_arm(root, mode, value)
            report = experiments.report(root)
            self.assertEqual(report["coverage"], [])
            triple = report["resource_overhead"]["triplets"][0]
            self.assertEqual(triple["differences"]["controller"]["system_cpu_reported_percent"]["delta"], 2)
            self.assertEqual(triple["differences"]["tracing"]["system_cpu_reported_percent"]["delta"], -1)
            self.assertEqual(triple["differences"]["total"]["system_cpu_reported_percent"]["delta"], 1)
            self.assertIsNone(triple["differences"]["total"]["estimated_energy_mwh"]["delta"])
            self.assertFalse(report["resource_overhead"]["groups"][0]["three_repetitions_complete"])

    def test_duplicate_and_version_mismatch_not_paired(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for mode in resources.MODES: self.write_arm(root, mode, 10)
            folder = root / "resource_trace"
            run = json.loads((folder / "metadata.json").read_text())
            run["resource_identity"]["agent"]["version"] = "different-version"
            (folder / "metadata.json").write_text(json.dumps(run))
            self.assertEqual(resources.compare(root)["triplets"], [])
            run["resource_identity"]["agent"]["version"] = "1"
            (folder / "metadata.json").write_text(json.dumps(run))
            self.write_arm(root, "resource_agent", 10, "duplicate")
            self.assertEqual(resources.compare(root)["triplets"], [])


class ResourceAPITests(unittest.TestCase):
    def test_resource_run_uses_resource_pipeline_not_binder_analyzer(self):
        def capture(run, folder, stop, update):
            update(status="recording", resource_identity={"build": "fixture"})
            resources.save(folder, run, [sample_fixture(150), sample_fixture(300)], 301, True)
            trace = folder / "capture.pftrace"; trace.write_bytes(b"fixture")
            return trace
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(server.collector, "devices", return_value=["phone"]), \
             patch.object(server.collector, "packages", return_value={"org.agent": 10001}), \
             patch.object(server.collector, "adb", return_value="35"), \
             patch.object(server.resources, "capture", side_effect=capture), \
             patch.object(server.analyzer, "analyze") as analyze:
            manager = server.Runs(Path(temp))
            run = manager.start(run_fixture("resource_trace"))
            for _ in range(100):
                result = manager.get(run["id"])
                if result["status"] in server.TERMINAL: break
                time.sleep(.01)
            self.assertEqual(result["status"], "complete")
            self.assertIn("resources.csv", manager.artifacts(run["id"]))
            self.assertIn("capture.pftrace", manager.artifacts(run["id"]))
            self.assertNotIn("No communication summary is available", manager.quality(run["id"])["issues"])
            analyze.assert_not_called()

    def test_validation_before_device_mutation(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(server.collector, "adb") as adb:
            manager = server.Runs(Path(temp))
            body = {**run_fixture("resource_agent"), "controller_stop_ack": True}
            for changed, client in ((body, "android"), ({**body, "controller_stop_ack": False}, "desktop"),
                                    ({**body, "target_package": resources.CONTROLLER}, "desktop"),
                                    ({**body, "duration_seconds": 600}, "desktop")):
                with self.assertRaises(server.APIError): manager.start(changed, client)
            adb.assert_not_called()

    def test_authenticated_resource_exports_and_quality(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = run_fixture()
            run["created_at"] = "2026-11-07T00:00:00Z"
            folder = root / run["id"]; folder.mkdir()
            (folder / "metadata.json").write_text(json.dumps(run))
            resources.save(folder, run, [sample_fixture(150), sample_fixture(300)], 301, True)
            with server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler) as http:
                http.token = "test"; http.runs = server.Runs(root)
                worker = threading.Thread(target=http.serve_forever, daemon=True); worker.start()
                try:
                    base = f"http://127.0.0.1:{http.server_port}/api/runs/{run['id']}"
                    for file in ("resources.json", "resources.csv", "resources_summary.json", "quality"):
                        with urlopen(Request(base + "/" + file, headers={"Authorization": "Bearer test"})) as response:
                            self.assertEqual(response.status, 200)
                    with self.assertRaises(HTTPError) as err:
                        urlopen(base + "/resources.json")
                    self.assertEqual(err.exception.code, 401); err.exception.close()
                finally:
                    http.shutdown(); worker.join()
