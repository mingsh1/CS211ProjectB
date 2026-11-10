"""Best-effort foreground browser evidence sampled after a task marker.

This does not inspect page contents or prove that the requested page loaded.
"""
import re
from .collector import adb

COMPONENT = re.compile(r"\b([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)/[A-Za-z0-9_.$]+")


def foreground_package(dump):
    lines = dump.splitlines()
    top = [line for line in lines if "topResumedActivity=" in line]
    resumed = top or [line for line in lines if "mResumedActivity" in line or "ResumedActivity:" in line]
    names = {match.group(1) for line in resumed for match in COMPONENT.finditer(line)}
    return next(iter(names)) if len(names) == 1 else None


def detect(serial, target_package):
    first = foreground_package(adb("shell", "dumpsys", "activity", "activities", serial=serial, timeout=3))
    if first is None:
        return {"status": "unavailable", "reason": "Foreground app is unavailable or ambiguous; enter the browser package manually."}
    if first in {target_package, "edu.cs211.projectb"}:
        return {"status": "unavailable", "reason": "Keep the external browser visible and use the browser launched notification action."}
    handlers = adb("shell", "cmd", "package", "query-activities", "--brief", "--components",
                   "--user", "current", "-a", "android.intent.action.VIEW",
                   "-c", "android.intent.category.BROWSABLE", "-d", "https://example.com",
                   serial=serial, timeout=3)
    if first not in {match.group(1) for match in COMPONENT.finditer(handlers)}:
        return {"status": "unavailable", "reason": "Foreground app is not a generic HTTPS handler; enter the browser package manually."}
    second = foreground_package(adb("shell", "dumpsys", "activity", "activities", serial=serial, timeout=3))
    if second != first:
        return {"status": "unavailable", "reason": "Foreground app changed during detection; enter the browser package manually."}
    return {"status": "detected", "package": first,
            "evidence": "Same foreground app before/after generic HTTPS handler query; sampled after browser_launched marker"}
