"""Rebuild path evidence from retained raw traces without changing other exports."""
import argparse
import json
from pathlib import Path
from . import analyzer

def rebuild(root):
    results = []
    for folder in sorted(root.iterdir()):
        trace, meta = folder / "capture.pftrace", folder / "metadata.json"
        if not trace.is_file() or not meta.is_file():
            continue
        run = json.loads(meta.read_text(encoding="utf-8"))
        if run.get("mode", "trace") != "trace":
            continue
        _, summary = analyzer.analyze(trace, run)
        evidence = summary.pop("path_evidence")
        analyzer.save_json(folder / "path_evidence.json", evidence)
        results.append({"run_id": run["id"], "candidates": len(evidence),
                        "complete": sum(all(e["hops"]) for e in evidence),
                        "inside_task_window": sum(e["task_window"]["both_hops_inside"] for e in evidence)})
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=Path("runs"))
    args = parser.parse_args()
    print(json.dumps(rebuild(args.runs), indent=2))
