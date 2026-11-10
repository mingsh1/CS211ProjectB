"""Compare repeated workloads and evaluate a transparent centroid classifier."""
import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from .analyzer import save_json
from .protocol import validate
from . import resources

WORKLOADS = ("W0", "W1", "W2")
FEATURES = ("incoming_per_second", "outgoing_per_second", "distinct_peers",
            "async_fraction", "active_second_fraction")


def features(summary):
    count = summary["transaction_count"]
    bins = summary["timeline"]
    return (
        summary["rates_per_second"]["incoming"] or 0,
        summary["rates_per_second"]["outgoing"] or 0,
        summary["peer_process_count"],
        summary["transaction_types"].get("async", 0) / count if count else 0,
        sum(any(b[k] for k in ("incoming", "outgoing", "internal")) for b in bins) / len(bins),
    )


def evaluate(samples):
    predictions = []
    for agent in sorted({s["agent"] for s in samples}):
        training = [s for s in samples if s["agent"] != agent]
        held_out = [s for s in samples if s["agent"] == agent]
        groups = {w: [s["features"] for s in training if s["actual"] == w] for w in WORKLOADS}
        if any(not values for values in groups.values()):
            predictions.extend({**s, "predicted": "uncertain", "reason": "Missing training workloads"}
                               for s in held_out)
            continue
        scales = [statistics.pstdev(column) or 1 for column in zip(*(s["features"] for s in training))]
        centers = {w: [statistics.mean(column) for column in zip(*values)]
                   for w, values in groups.items()}
        for sample in held_out:
            distances = sorted((math.sqrt(sum(((x - center) / scale) ** 2
                               for x, center, scale in zip(sample["features"], centroid, scales))), w)
                               for w, centroid in centers.items())
            best, runner_up = distances[:2]
            margin = (runner_up[0] - best[0]) / max(runner_up[0], 1e-9)
            predictions.append({**sample, "predicted": best[1] if margin >= .20 else "uncertain",
                                "relative_margin": margin, "distances": {w: d for d, w in distances}})
    return predictions


def report(root):
    samples, exclusions, records, comparisons = [], [], [], []
    groups = defaultdict(list)
    observed = defaultdict(list)
    for path in sorted(root.glob("*/metadata.json")):
        run = json.loads(path.read_text(encoding="utf-8"))
        summary_path = path.with_name("summary.json")
        if "id" not in run or "workload" not in run:
            continue  # Offline trace analyses lack experiment ground truth.
        if run.get("mode") in resources.MODES:
            continue  # Resource scenarios do not count as formal Binder workloads.
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else None
        records.append((run, summary))
        if run.get("mode", "trace") == "baseline":
            continue
        cohort = (run.get("device_label") or run.get("serial", "unknown"), run.get("conditions", ""))
        comparisons.append({"id": run["id"], "device": cohort[0], "conditions": cohort[1],
                            "agent": run["target_package"], "workload": run["workload"],
                            "outcome": run.get("outcome"), "capture_status": run.get("status"),
                            "summary_available": summary is not None,
                            "trace_bytes": run.get("trace_bytes"),
                            "analysis_wall_seconds": run.get("analysis_wall_seconds"),
                            "metrics": {k: summary.get(k) for k in (
                                "transaction_count", "peer_process_count", "rates_per_second",
                                "sync_latency_ms", "top_peers", "interfaces", "candidate_paths")}
                            if summary else None})
        if run.get("status") != "complete" or not summary_path.is_file():
            exclusions.append({"id": run["id"], "reason": "Run incomplete"})
            continue
        quality = validate(run, summary)
        if not quality["valid"]:
            exclusions.append({"id": run["id"], "reason": "Ground truth or trace quality",
                               "outcome": run.get("outcome"), "issues": quality["issues"]})
            continue
        agent, workload = run["target_package"], run["workload"]
        observed[cohort, agent, workload].append(run)
        if run.get("outcome") != "success":
            exclusions.append({"id": run["id"], "reason": "Classifier uses successful tasks only",
                               "outcome": run.get("outcome")})
            continue
        sample = {"id": run["id"], "agent": agent, "actual": workload,
                  "device": cohort[0], "conditions": cohort[1],
                  "repetition": run["repetition"], "features": features(summary)}
        groups[cohort, agent, workload].append(sample)
        samples.append(sample)
    # Never train across phones or differing prompts/input modes.
    cohorts = sorted({(r["device"], r["conditions"]) for r in comparisons})
    predictions = [p for cohort in cohorts for p in evaluate(
        [s for s in samples if (s["device"], s["conditions"]) == cohort])]
    confusion = Counter((p["actual"], p["predicted"]) for p in predictions)
    classified = sum(p["predicted"] != "uncertain" for p in predictions)
    correct = sum(p["predicted"] == p["actual"] for p in predictions)
    coverage = []
    complete_cohorts = []
    for cohort in cohorts:
        agents = sorted({r["agent"] for r in comparisons
                         if (r["device"], r["conditions"]) == cohort})
        for a in agents:
            for w in WORKLOADS:
                valid = observed[cohort, a, w]
                successful = groups[cohort, a, w]
                coverage.append({"device": cohort[0], "conditions": cohort[1], "agent": a, "workload": w,
                    "valid_runs": len(valid), "successful_runs": len(successful),
                    "distinct_repetitions": len({r["repetition"] for r in valid}),
                    "outcomes": dict(Counter(r.get("outcome") for r in valid)),
                    "median_features": [statistics.median(c) for c in zip(*(s["features"] for s in successful))]})
        if cohort[1] and sum(all(len({r["repetition"] for r in observed[cohort, a, w]}) >= 3
                   for w in WORKLOADS) for a in agents) >= 2:
            complete_cohorts.append({"device": cohort[0], "conditions": cohort[1]})
    return {
        "feature_names": FEATURES,
        "method": "Leave one agent out, nearest workload centroid, standardized on training data",
        "abstention_margin": .20, "coverage": coverage,
        "protocol_has_at_least_two_agents_with_three_repetitions": bool(complete_cohorts),
        "complete_cohorts": complete_cohorts,
        "run_comparisons": comparisons, "overhead": overhead(records), "resource_overhead": resources.compare(root),
        "excluded_runs": exclusions, "predictions": predictions,
        "confusion": [{"actual": a, "predicted": p, "count": n} for (a, p), n in sorted(confusion.items())],
        "classification_coverage": classified / len(predictions) if predictions else None,
        "accuracy_when_classified": correct / classified if classified else None,
    }


def overhead(records):
    """Pair baseline and traced task timings, preserving missing/ambiguous pairs."""
    pairs, excluded, buckets = [], [], defaultdict(lambda: defaultdict(list))
    for run, summary in records:
        if run.get("workload") not in {"W1", "W2"}:
            continue  # W0 is fixed by the operator, not a completion-time measurement.
        mode = run.get("mode", "trace")
        quality = validate(run, summary if mode == "trace" else None)
        reason = []
        if run.get("status") != "complete" or run.get("outcome") != "success":
            reason.append("Requires a completed successful task")
        if mode == "trace" and summary is None:
            reason.append("Missing trace summary")
        if not run.get("device_label") or not run.get("conditions"):
            reason.append("Set the same stable device label and conditions for both trials")
        if any(m.get("source") != "android_elapsed_realtime" for m in run.get("markers", [])):
            reason.append("Overhead comparison requires native phone markers")
        reason.extend(quality["issues"])
        if reason:
            excluded.append({"id": run["id"], "issues": reason})
            continue
        key = (run["device_label"], run["conditions"], run["target_package"],
               run["workload"], run["repetition"])
        buckets[key][mode].append((run, quality["task_duration_seconds"]))
    for key, modes in buckets.items():
        if len(modes["trace"]) != 1 or len(modes["baseline"]) != 1:
            excluded.append({"pair": key, "issues": ["Need exactly one baseline and one traced run per pair"]})
            continue
        traced, measured = modes["trace"][0]
        baseline, control = modes["baseline"][0]
        delta = measured - control
        pairs.append({"device": key[0], "conditions": key[1], "agent": key[2],
                      "workload": key[3], "repetition": key[4],
                      "trace_run": traced["id"], "baseline_run": baseline["id"],
                      "baseline_seconds": control, "traced_seconds": measured,
                      "delta_seconds": delta, "relative_change_percent": 100 * delta / control})
    grouped = defaultdict(list)
    for pair in pairs:
        grouped[pair["device"], pair["conditions"], pair["agent"], pair["workload"]].append(pair)
    return {"method": "Paired operator-marked task duration with versus without Perfetto; controller remains enabled",
            "limitations": ["Not total APK, CPU, memory or energy overhead",
                            "Operator delay, network, service variation and trial order confound task duration",
                            "Alternate baseline/trace order and repeat; negative changes are retained"],
            "pairs": pairs, "excluded": excluded,
            "groups": [{"device": k[0], "conditions": k[1], "agent": k[2], "workload": k[3],
                        "pair_count": len(v),
                        "median_delta_seconds": statistics.median(p["delta_seconds"] for p in v),
                        "median_relative_change_percent": statistics.median(p["relative_change_percent"] for p in v)}
                       for k, v in grouped.items()]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=Path("runs"))
    parser.add_argument("--output", type=Path, default=Path("runs/evaluation.json"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_json(args.output, report(args.runs))
    print(args.output)
