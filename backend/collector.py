"""Wireless ADB and on-device Perfetto session lifecycle."""
import re
import subprocess
import time
from pathlib import Path

CONFIG = Path(__file__).with_name("trace.pbtx")


def adb(*args, serial=None, data=None, timeout=20):
    command = ["adb", *(["-s", serial] if serial else []), *args]
    result = subprocess.run(command, input=data, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace").strip()
                           or result.stdout.decode(errors="replace").strip()
                           or f"ADB exited with code {result.returncode}")
    return result.stdout.decode(errors="replace").strip()


def devices():
    return [line.split()[0] for line in adb("devices", "-l").splitlines()
            if len(line.split()) >= 2 and line.split()[1] == "device"]


def packages(serial):
    listing = adb("shell", "pm", "list", "packages", "-U", "--user", "current", serial=serial)
    return {name: int(uid) for name, uid in re.findall(r"^package:(\S+)\s+uid:(\d+)", listing, re.M)}


def package_details(serial, package):
    if not re.fullmatch(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+", package):
        raise ValueError("Invalid package name")
    installed = packages(serial)
    if package not in installed:
        raise ValueError("Package is not installed for the current Android user")
    dump = adb("shell", "dumpsys", "package", package, serial=serial)
    version = re.search(r"^\s*versionName=(.+)$", dump, re.M)
    code = re.search(r"\bversionCode=(\d+)", dump)
    return {"package": package, "uid": installed[package],
            "version": version.group(1).strip() if version else None,
            "version_code": int(code.group(1)) if code else None}


class Recording:
    def __init__(self, run, folder):
        self.serial = run["serial"]
        self.remote = f"/data/misc/perfetto-traces/cs211-{run['id']}.pftrace"
        self.local = folder / "capture.pftrace"
        self.duration = run["duration_seconds"]
        self.pid = None

    def shell(self, *args, **kwargs):
        return adb("shell", *args, serial=self.serial, **kwargs)

    def start(self):
        config = CONFIG.read_text() + f"\nduration_ms: {self.duration * 1000}\n"
        output = self.shell("perfetto", "--background-wait", "--txt", "-c", "-",
                            "-o", self.remote, data=config.encode(), timeout=45)
        pid = output.splitlines()[-1].strip() if output else ""
        if not pid.isdecimal():
            raise RuntimeError(f"Perfetto did not return a recorder PID: {output}")
        self.pid = pid

    def running(self):
        # Check the command line before signaling to avoid killing a reused PID.
        command_line = self.shell("cat", f"/proc/{self.pid}/cmdline", "2>/dev/null", "||", "true")
        return self.remote in command_line

    def mark(self):
        started = time.monotonic_ns()
        uptime = self.shell("cat", "/proc/uptime").split()[0]
        whole, _, fraction = uptime.partition(".")
        precision = 10 ** (9 - len(fraction))
        return {"boottime_ns": int(whole) * 10**9 + int(fraction or "0") * precision,
                "sample_roundtrip_ns": time.monotonic_ns() - started,
                "clock_resolution_ns": precision}

    def collect(self, stop):
        if stop and self.running():
            self.shell("kill", "-TERM", self.pid, "2>/dev/null", "||", "true")
        deadline = time.monotonic() + 15
        while self.running():
            if time.monotonic() >= deadline:
                raise RuntimeError("Perfetto did not finish writing the trace.")
            time.sleep(.25)
        adb("pull", self.remote, str(self.local), serial=self.serial, timeout=120)
        if not self.local.stat().st_size:
            raise RuntimeError("Perfetto returned an empty trace.")
        try:
            self.shell("rm", "-f", self.remote)
        except (RuntimeError, subprocess.TimeoutExpired):
            pass  # The local trace is already available for analysis.
        return self.local
