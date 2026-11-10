import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend import browser_detection, server


class BrowserDetectionTests(unittest.TestCase):
    def test_foreground_parser_does_not_use_old_task_history(self):
        dump = "Hist #0: org.old.browser/.Main\n topResumedActivity=ActivityRecord{abc u0 org.actual.browser/.Main t1}\n"
        self.assertEqual(browser_detection.foreground_package(dump), "org.actual.browser")
        self.assertIsNone(browser_detection.foreground_package("Hist #0: org.old.browser/.Main"))
        self.assertIsNone(browser_detection.foreground_package(
            "mResumedActivity: org.one/.Main\nmResumedActivity: org.two/.Main"))

    def test_actual_foreground_handler_is_detected(self):
        activity = "topResumedActivity=ActivityRecord{abc u0 org.actual.browser/.Main t1}"
        with patch.object(browser_detection, "adb", side_effect=[activity,
                "org.default.browser/.Main\norg.actual.browser/.Main", activity]):
            self.assertEqual(browser_detection.detect("phone", "org.agent")["package"], "org.actual.browser")

    def test_controller_nonbrowser_and_switched_app_are_not_guessed(self):
        for output in [
            ["topResumedActivity=edu.cs211.projectb/.Main"],
            ["topResumedActivity=org.agent/.Main"],
            ["topResumedActivity=org.chat/.Main", "org.browser/.Main"],
            ["topResumedActivity=org.browser/.Main", "org.browser/.Main", "topResumedActivity=org.other/.Main"],
        ]:
            with patch.object(browser_detection, "adb", side_effect=output):
                self.assertEqual(browser_detection.detect("phone", "org.agent")["status"], "unavailable")

    def test_marker_saved_before_detection_and_manual_value_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            runs = server.Runs(Path(folder))
            run_id = "a" * 32
            runs.folder(run_id).mkdir()
            runs.runs[run_id] = {"id": run_id, "status": "recording", "serial": "phone",
                                "target_package": "org.agent", "markers": [], "browser_package": ""}
            with patch.object(server.threading, "Thread"):
                marker = runs.marker(run_id, {"label": "browser_launched", "boottime_ns": 123})
            self.assertEqual(runs.get(run_id)["markers"][0]["boottime_ns"], 123)
            with patch.object(browser_detection, "detect", return_value={"status": "detected", "package": "org.browser"}):
                runs.detect_browser(run_id, marker)
            self.assertEqual(runs.get(run_id)["browser_package"], "org.browser")
            runs.outcome(run_id, {"outcome": "success", "browser_package": "org.manual.browser"})
            with patch.object(browser_detection, "detect", return_value={"status": "detected", "package": "org.browser"}):
                runs.detect_browser(run_id, marker)
            self.assertEqual(runs.get(run_id)["browser_package"], "org.manual.browser")
            with patch.object(browser_detection, "detect", side_effect=RuntimeError("offline")):
                runs.detect_browser(run_id, marker)
            self.assertEqual(runs.get(run_id)["browser_detection"]["status"], "unavailable")
            self.assertEqual(len(runs.get(run_id)["markers"]), 1)
