"""Extract observed Binder requests and summarize the evidence."""
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

SECOND = 10**9
TRANSACTIONS = """
INCLUDE PERFETTO MODULE android.binder;
SELECT b.*, c.uid AS client_uid, s.uid AS server_uid,
       EXTRACT_ARG(tx.arg_set_id, 'code') AS code_label
FROM android_binder_txns b
LEFT JOIN process c ON c.upid = b.client_upid
LEFT JOIN process s ON s.upid = b.server_upid
LEFT JOIN slice tx ON tx.id = b.binder_txn_id
ORDER BY b.client_ts, b.binder_txn_id
"""
RAW = """
SELECT s.ts, t.utid, t.tid, p.upid, p.pid, p.name, p.uid, 0 AS reply,
       s.name = 'binder transaction async' AS flags,
       EXTRACT_ARG(s.arg_set_id, 'code') AS code,
       EXTRACT_ARG(s.arg_set_id, 'destination process') AS to_pid
FROM slice s JOIN thread_track tr ON tr.id = s.track_id
JOIN thread t USING (utid) LEFT JOIN process p USING (upid)
WHERE s.name IN ('binder transaction', 'binder transaction async')
"""


def rows(processor, sql):
    return [vars(row) for row in processor.query(sql)]


def target_processes(processes, package, uid, packages):
    # Shared UIDs require name evidence. Colon subprocesses can have isolated UIDs.
    unique_uid = uid is not None and packages.get(uid) == {package}
    return {p["upid"] for p in processes if (
        p["uid"] == uid and unique_uid
        or any(name == package or name.startswith(package + ":")
               for name in (p["name"] or "", (p["cmdline"] or "").split(" ", 1)[0]))
    )}


def endpoint(row, side):
    return {field: row.get(f"{side}_{field}")
            for field in ("process", "upid", "pid", "uid", "thread", "utid", "tid")}


def transaction_code(value):
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.startswith("0x"):
        try:
            return int(value.split()[0], 16)
        except ValueError:
            pass
    return None


def extract(matched, raw, target):
    raw_by_start = defaultdict(list)
    for event in raw:
        if event["reply"] == 0:
            raw_by_start[event["utid"], event["ts"]].append(event)
    seen = set()
    consumed = set()
    for row in matched:
        if row["binder_txn_id"] in seen:
            continue
        seen.add(row["binder_txn_id"])
        key = row["client_utid"], row["client_ts"]
        events = raw_by_start.get(key, [])
        consumed.add(key)
        yield {
            "id": f"slice:{row['binder_txn_id']}", "ts_ns": row["client_ts"],
            "sender": endpoint(row, "client"), "receiver": endpoint(row, "server"),
            "type": {1: "sync", 0: "async"}.get(row["is_sync"], "unknown"),
            "reply_observed": bool(row["is_sync"] and row["binder_reply_id"] is not None
                                   and (row["client_dur"] or 0) > 0),
            "latency_ns": row["client_dur"] if row["is_sync"]
                and row["binder_reply_id"] is not None and (row["client_dur"] or 0) > 0 else None,
            "interface": row.get("interface"), "method": row.get("method_name"),
            "code": transaction_code(row.get("code_label") if row.get("code_label") is not None
                                     else events[0]["code"] if len(events) == 1 else None),
            "server_ts_ns": row["server_ts"], "server_duration_ns": row["server_dur"],
            "evidence": "perfetto_transaction",
        }
    for key, events in raw_by_start.items():
        if key in consumed:
            continue
        for index, event in enumerate(events):
            if event["upid"] not in target:
                continue
            yield {
                "id": f"send:{key[0]}:{key[1]}:{index}", "ts_ns": event["ts"],
                "sender": {"process": event["name"], **{k: event[k] for k in ("upid", "pid", "uid", "tid", "utid")}},
                "receiver": {"pid": event["to_pid"]},
                "type": ("async" if event["flags"] & 1 else "sync")
                    if isinstance(event["flags"], int) else "unknown",
                "reply_observed": False, "latency_ns": None, "interface": None, "method": None,
                "code": transaction_code(event["code"]), "server_ts_ns": None, "server_duration_ns": None,
                "evidence": "binder_send_only",
            }


def label(end):
    if end.get("upid") is None:
        pid = end.get("pid")
        return f"Unresolved PID {pid}" if pid is not None else "Unresolved"
    return f"{end.get('process') or 'Unnamed process'} [upid {end['upid']}]"


def candidate_paths(requests, target):
    by_thread = defaultdict(list)
    for tx in requests:
        if tx["sender"].get("utid") is not None:
            by_thread[tx["sender"]["utid"]].append(tx)
    for tx in requests:
        start, duration = tx["server_ts_ns"], tx["server_duration_ns"]
        mid = tx["receiver"]
        if (tx["sender"].get("upid") not in target or mid.get("upid") in target
                or mid.get("utid") is None or start is None or not duration or duration < 0):
            continue
        for child in by_thread[mid["utid"]]:
            destination = child["receiver"].get("upid")
            if (start <= child["ts_ns"] < start + duration and destination is not None
                    and destination != mid.get("upid") and destination not in target):
                yield {"status": "candidate", "hops": 2,
                       "processes": [label(tx["sender"]), label(mid), label(child["receiver"])],
                       "transaction_ids": [tx["id"], child["id"]],
                       "evidence": "Second request starts on the serving thread inside the first server slice"}


def summarize(requests, target, start, end, markers, warnings):
    selected, peers, edges, interfaces = [], Counter(), Counter(), Counter()
    directions, types, latencies = Counter(), Counter(), []
    bins = [{"second": i, "incoming": 0, "outgoing": 0, "internal": 0}
            for i in range(max(1, math.ceil((end - start) / SECOND)))]
    for tx in requests:
        sender, receiver = tx["sender"], tx["receiver"]
        outgoing, incoming = sender.get("upid") in target, receiver.get("upid") in target
        if not (outgoing or incoming):
            continue
        direction = "internal" if outgoing and incoming else "outgoing" if outgoing else "incoming"
        selected.append({**tx, "direction": direction})
        directions[direction] += 1
        types[tx["type"]] += 1
        edges[label(sender), label(receiver)] += 1
        peer = receiver if outgoing else sender
        if direction != "internal" and peer.get("upid") is not None:
            peers[label(peer)] += 1
        if tx["interface"] and tx["method"]:
            interfaces[tx["interface"], tx["method"], direction] += 1
        if tx["latency_ns"] is not None:
            latencies.append(tx["latency_ns"] / 10**6)
        bucket = min((tx["ts_ns"] - start) // SECOND, len(bins) - 1)
        if 0 <= bucket < len(bins):
            bins[bucket][direction] += 1
    for marker in markers:
        marker["offset_seconds"] = (marker["boottime_ns"] - start) / SECOND
        marker["inside_trace"] = start <= marker["boottime_ns"] <= end
        if not marker["inside_trace"]:
            warnings.append(f"Task marker outside trace: {marker['label']}")
    duration = (end - start) / SECOND
    if not selected:
        warnings.append("No Binder requests attributed to the target. Check the app, trace and UID.")
    latencies.sort()
    return selected, {
        "trace_duration_seconds": duration, "transaction_count": len(selected),
        "direction_counts": dict(directions), "transaction_types": dict(types),
        "rates_per_second": {d: directions[d] / duration if duration else None
                             for d in ("incoming", "outgoing")},
        "peer_process_count": len(peers), "top_peers": peers.most_common(5),
        "edges": [{"sender": a, "receiver": b, "count": count} for (a, b), count in edges.most_common()],
        "interfaces": [{"interface": i, "method": m, "direction": d, "count": count}
                       for (i, m, d), count in interfaces.most_common()],
        "unidentified_interface_count": len(selected) - sum(interfaces.values()),
        "unresolved_endpoint_requests": sum(any(tx[end].get("upid") is None for end in ("sender", "receiver"))
                                            for tx in selected),
        "matched_sync_calls": len(latencies),
        "sync_latency_ms": {"median": statistics.median(latencies) if latencies else None,
                            "p95": latencies[math.ceil(.95 * len(latencies)) - 1] if latencies else None},
        "timeline": bins, "markers": markers, "warnings": warnings,
        "candidate_paths": list(candidate_paths(requests, target)),
    }


def analyze(trace, run):
    from perfetto.trace_processor import TraceProcessor
    warnings = []
    with TraceProcessor(trace=str(trace)) as processor:
        bounds = rows(processor, "SELECT start_ts, end_ts FROM trace_bounds")[0]
        if bounds["end_ts"] - bounds["start_ts"] > 600 * SECOND:
            raise ValueError("Expected a single experiment trace of ten minutes or less.")
        processes = rows(processor, "SELECT upid, pid, name, cmdline, uid FROM process")
        packages = defaultdict(set)
        for name, uid in run.get("packages", {}).items():
            packages[uid].add(name)
        for p in rows(processor, "SELECT package_name, uid FROM package_list"):
            packages[p["uid"]].add(p["package_name"])
        target = target_processes(processes, run["target_package"], run.get("target_uid"), packages)
        matched = rows(processor, TRANSACTIONS)
        raw = rows(processor, RAW)
        stats = rows(processor, "SELECT name, value FROM stats WHERE value > 0 AND "
                    "(severity = 'data_loss' OR name LIKE 'ftrace_setup_errors%')")
        warnings.extend(f"{stat['name']}: {stat['value']}" for stat in stats)
        if not raw and not matched:
            warnings.append("The trace contains no recognizable Binder events.")
        if not raw and matched:
            warnings.append("Binder request slices unavailable. Unmatched sends may be missing.")
    requests = list(extract(matched, raw, target))
    for request in requests:
        request["run_id"] = run.get("id")
        for side in ("sender", "receiver"):
            endpoint_data = request[side]
            endpoint_data["packages"] = sorted(packages.get(endpoint_data.get("uid"), ()))
            endpoint_data["identity_status"] = "resolved" if endpoint_data.get("upid") is not None else "unresolved"
    selected, summary = summarize(requests, target, bounds["start_ts"], bounds["end_ts"],
                                  run.get("markers", []), warnings)
    summary["target_processes"] = [p for p in processes if p["upid"] in target]
    return selected, summary


def save_json(path, payload):
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    pending.replace(path)


def export(folder, transactions, summary):
    save_json(folder / "transactions.json", transactions)
    save_json(folder / "summary.json", summary)
    for name, data, fields in (
        ("transactions", transactions, ["run_id", "id", "ts_ns", "sender", "receiver", "direction", "type",
                                        "reply_observed", "latency_ns", "interface", "method", "code", "evidence"]),
        ("timeline", summary["timeline"], ["second", "incoming", "outgoing", "internal"]),
        ("edges", summary["edges"], ["sender", "receiver", "count"]),
    ):
        with (folder / f"{name}.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fields, extrasaction="ignore")
            writer.writeheader()
            for row in data:
                writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v
                                 for k, v in row.items()})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Analyze a previously captured trace.")
    parser.add_argument("trace", type=Path)
    parser.add_argument("target_package")
    parser.add_argument("output", type=Path)
    parser.add_argument("--uid", type=int)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    metadata = {"target_package": args.target_package, "target_uid": args.uid, "markers": []}
    export(args.output, *analyze(args.trace, metadata))
    save_json(args.output / "metadata.json", metadata)
