"""Validate operator ground truth separately from observed Binder evidence."""
from collections import defaultdict

SEQUENCES = {
    "W0": ("idle_start", "idle_end"),
    "W1": ("prompt_submitted", "browser_launched"),
    "W2": ("voice_start", "voice_end", "response_complete"),
}


def validate(run, summary=None):
    issues = []
    workload = run.get("workload")
    sequence = SEQUENCES.get(workload, ())
    if not sequence:
        issues.append("Unknown workload")
    outcome = run.get("outcome")
    if outcome not in {"success", "failure", "timeout", "unexpected_activity"}:
        issues.append("Record the actual task outcome")
    markers = run.get("markers", [])
    by_label = defaultdict(list)
    for marker in markers:
        timestamp = marker.get("boottime_ns")
        if type(timestamp) is not int or timestamp <= 0:
            issues.append("Invalid marker timestamp")
            continue
        by_label[marker.get("label")].append(timestamp)
    # Failed tasks need not have reached the completion event.
    required = sequence if outcome == "success" or workload == "W0" else sequence[:1]
    for label in required:
        if len(by_label[label]) != 1:
            issues.append(f"Expected exactly one {label} marker")
    present = [by_label[label][0] for label in sequence if len(by_label[label]) == 1]
    if any(a >= b for a, b in zip(present, present[1:])):
        issues.append("Task markers are out of order")
    duration = None
    if sequence and all(len(by_label[label]) == 1 for label in sequence):
        duration = (by_label[sequence[-1]][0] - by_label[sequence[0]][0]) / 1e9
        if duration <= 0:
            issues.append("Task duration must be positive")
        elif workload == "W0" and duration < 30:
            issues.append("Idle observation is shorter than 30 seconds")
        elif workload in {"W1", "W2"} and duration > 60 and outcome == "success":
            issues.append("Task exceeded the 60 second workload limit")
    if outcome == "success":
        if workload == "W1" and not run.get("browser_package", "").strip():
            issues.append("Record the browser package")
        if workload == "W2" and not run.get("actual_response", "").strip():
            issues.append("Record the actual voice response")
        if workload == "W0" and by_label["unexpected_activity"]:
            issues.append("Unexpected activity contradicts successful idle ground truth")
    if workload == "W1" and len(by_label["prompt_submitted"]) == 1:
        start = by_label["prompt_submitted"][0]
        end = by_label["browser_launched"][0] if len(by_label["browser_launched"]) == 1 else float("inf")
        if any(not start <= t <= end for t in by_label["confirmation"]):
            issues.append("Confirmation falls outside the browser task")
    if summary is not None:
        aligned = summary.get("markers", [])
        if len(aligned) != len(markers) or any(m.get("inside_trace") is not True for m in aligned):
            issues.append("Task markers are missing from or outside the trace")
        issues.extend(summary.get("warnings", []))
        if summary.get("trace_duration_seconds", 0) <= 0:
            issues.append("Trace duration must be positive")
    return {"valid": not issues, "issues": list(dict.fromkeys(issues)),
            "task_duration_seconds": duration}
