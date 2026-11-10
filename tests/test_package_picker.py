import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from backend import collector, server


class PackagePickerTests(unittest.TestCase):
    def test_details_parse_and_preserve_missing_version(self):
        with patch.object(collector, "packages", return_value={"com.example.agent": 123}), \
                patch.object(collector, "adb", return_value="  versionCode=42 minSdk=30\n  versionName=2.4 beta\n"):
            details = collector.package_details("phone", "com.example.agent")
            self.assertEqual(details, {"package": "com.example.agent", "uid": 123,
                                      "version": "2.4 beta", "version_code": 42})
        with patch.object(collector, "packages", return_value={"com.example.agent": 123}), \
                patch.object(collector, "adb", return_value=""):
            self.assertIsNone(collector.package_details("phone", "com.example.agent")["version"])

    def test_reject_invalid_or_uninstalled_package_before_dumpsys(self):
        with patch.object(collector, "packages", return_value={}), patch.object(collector, "adb") as adb:
            for package in ("com.example;reboot", "com.missing.agent"):
                with self.assertRaises(ValueError):
                    collector.package_details("phone", package)
            adb.assert_not_called()

    def test_authenticated_details_api(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(collector, "devices", return_value=["phone"]), \
                patch.object(collector, "package_details", return_value={"package": "com.agent", "version": "1.2", "uid": 123}) as lookup:
            with server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler) as http:
                http.token = "test"
                http.runs = server.Runs(Path(folder))
                worker = threading.Thread(target=http.serve_forever, daemon=True)
                worker.start()
                def request(package, token="test", serial="phone"):
                    req = Request(f"http://127.0.0.1:{http.server_port}/api/devices/package-details",
                                  data=json.dumps({"serial": serial, "package": package}).encode(),
                                  headers={"Authorization": "Bearer " + token})
                    return urlopen(req, timeout=3)
                try:
                    with request("com.agent") as response:
                        self.assertEqual(json.load(response)["version"], "1.2")
                    lookup.assert_called_once_with("phone", "com.agent")
                    for kwargs, code in [({"token": "wrong"}, 401), ({"serial": "missing"}, 400)]:
                        with self.assertRaises(HTTPError) as error:
                            request("com.agent", **kwargs)
                        self.assertEqual(error.exception.code, code)
                        error.exception.close()
                    with self.assertRaises(HTTPError) as error:
                        request("com.agent;bad")
                    self.assertEqual(error.exception.code, 400)
                    error.exception.close()
                finally:
                    http.shutdown()
                    worker.join()
