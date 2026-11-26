"""Build an auditable Metrics 1-3 report from completed run exports.

Usage: python -m backend.build_metrics_report --runs runs --output reports/metrics-1-3
"""
import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from xml.sax.saxutils import escape


BLUE = "#2563eb"
ORANGE = "#ea580c"
GREEN = "#059669"
GRAY = "#64748b"


def agent_label(package):
    return {"com.google.android.googlequicksearchbox": "Gemini",
            "com.openai.chatgpt": "ChatGPT"}.get(package, package)


def load_runs(root, agents=None, exclude_runs=None):
    agents = set(agents) if agents is not None else None
    exclude_runs = set(exclude_runs or ())
    result = []
    for folder in root.iterdir():
        files = [folder / name for name in
                 ("metadata.json", "summary.json", "transactions.json", "path_evidence.json")]
        if not all(path.is_file() for path in files):
            continue
        meta, summary, tx, paths = [json.loads(path.read_text(encoding="utf-8")) for path in files]
        if agents is not None and meta.get("target_package") not in agents:
            continue
        if meta.get("id") in exclude_runs:
            continue
        if meta.get("status") == "complete" and meta.get("mode") == "trace":
            result.append(dict(folder=folder, meta=meta, summary=summary, tx=tx, paths=paths))
    return sorted(result, key=lambda run: (run["meta"]["target_package"],
                                           run["meta"]["workload"], run["meta"]["repetition"]))


def csv_file(path, columns, records):
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def peer_key(endpoint):
    if endpoint.get("upid") is not None:
        return ("upid", endpoint["upid"])
    if endpoint.get("pid") is not None:
        return ("pid", endpoint["pid"])
    return ("unresolved", None)


def endpoint_label(endpoint):
    name = endpoint.get("process") or "Unresolved"
    upid = endpoint.get("upid")
    pid = endpoint.get("pid")
    return f"{name} [upid {upid}]" if upid is not None else f"{name} [pid {pid}]"


def clean_process(label):
    return re.sub(r" \[(?:upid|pid) \d+\]$", "", label)


def named_api(item):
    method = item.get("method") or ""
    return bool(item.get("interface") and method and not method.startswith(("#", "Unknown_Transaction_Code:")))


def md_table(headers, rows):
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    return "\n".join(["| " + " | ".join(map(cell, headers)) + " |",
                      "| " + " | ".join("---" for _ in headers) + " |"] +
                     ["| " + " | ".join(map(cell, row)) + " |" for row in rows])


def paired_rows(rows, formatter):
    by_cell = {(r["agent"], r["workload"], r["repetition"]): r for r in rows}
    return [[f"{workload} / {repetition}",
             formatter(by_cell["Gemini", workload, repetition]),
             formatter(by_cell["ChatGPT", workload, repetition])]
            for workload in ("W0", "W1", "W2") for repetition in (1, 2, 3)]


def side_by_side_ranking(left, right, count, label):
    first, second = left.most_common(count), right.most_common(count)
    return md_table(["Rank", "Gemini", "ChatGPT"], [
        [i + 1,
         f"{label(first[i][0])} · {first[i][1]:,}" if i < len(first) else "—",
         f"{label(second[i][0])} · {second[i][1]:,}" if i < len(second) else "—"]
        for i in range(max(len(first), len(second)))])


def svg_base(width, height, content):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img">'
            '<style>text{font-family:Arial,sans-serif;fill:#172033} .title{font-size:20px;font-weight:bold}'
            '.label{font-size:13px}.small{font-size:11px;fill:#475569}</style>' + content + '</svg>')


def histogram(runs, output):
    # Equal-width 1 s bins only; the potentially partial final bin is omitted.
    edges = [0, 100, 250, 500, 1000, math.inf]
    labels = ["0–99", "100–249", "250–499", "500–999", "1000+"]
    counts = defaultdict(lambda: {direction: [0] * 5 for direction in ("incoming", "outgoing")})
    for run in runs:
        agent = agent_label(run["meta"]["target_package"])
        timeline = run["summary"]["timeline"]
        whole = int(run["summary"]["trace_duration_seconds"])
        for bucket in timeline[:whole]:
            for direction in ("incoming", "outgoing"):
                value = bucket[direction]
                index = next(i for i in range(5) if edges[i] <= value < edges[i + 1])
                counts[agent][direction][index] += 1
    agents = sorted(counts, key=lambda name: (name != "Gemini", name))
    width, height = 60 + 600 * len(agents), 460
    bottom, plot_h = 370, 270
    maximum = max(max(series) for by_direction in counts.values() for series in by_direction.values()) or 1
    parts = [f'<rect width="{width}" height="{height}" fill="white"/>',
             '<text x="28" y="34" class="title">Binder requests per 1-second interval</text>',
             f'<text x="28" y="53" class="small">All {len(runs)} selected traces; last partial second excluded</text>']
    for panel, agent in enumerate(agents):
        left = 70 + panel * 600
        parts.append(f'<text x="{left+260}" y="82" text-anchor="middle" class="title">{escape(agent)}</text>')
        for tick in range(5):
            value = round(maximum * tick / 4)
            y = bottom - plot_h * tick / 4
            parts += [f'<line x1="{left}" y1="{y:.1f}" x2="{left+520}" y2="{y:.1f}" stroke="#e2e8f0"/>',
                      f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end" class="small">{value}</text>']
        for i, label in enumerate(labels):
            x = left + i * 104 + 8
            for j, (direction, color) in enumerate((("incoming", BLUE), ("outgoing", ORANGE))):
                value = counts[agent][direction][i]
                bar_h = plot_h * value / maximum
                bx = x + j * 39
                parts += [f'<rect x="{bx}" y="{bottom-bar_h:.1f}" width="31" height="{bar_h:.1f}" fill="{color}"/>',
                          f'<text x="{bx+15.5}" y="{bottom-bar_h-5:.1f}" text-anchor="middle" class="small">{value}</text>']
            parts.append(f'<text x="{x+35}" y="{bottom+23}" text-anchor="middle" class="small">{label}</text>')
    legend_x = width - 260
    parts += [f'<rect x="{legend_x}" y="26" width="13" height="13" fill="{BLUE}"/><text x="{legend_x+19}" y="37" class="small">Incoming</text>',
              f'<rect x="{legend_x+105}" y="26" width="13" height="13" fill="{ORANGE}"/><text x="{legend_x+124}" y="37" class="small">Outgoing</text>',
              f'<text x="{width/2}" y="435" text-anchor="middle" class="small">Requests in one full second; shared vertical scale</text>']
    output.write_text(svg_base(width, height, "".join(parts)), encoding="utf-8")
    return dict(counts)


def pie_chart(by_agent, output, run_count):
    agents = sorted(by_agent, key=lambda name: (name != "Gemini", name))
    width, height = 60 + 600 * len(agents), 430
    parts = [f'<rect width="{width}" height="{height}" fill="white"/>',
             '<text x="28" y="34" class="title">Named Binder interface and method coverage</text>',
             f'<text x="28" y="53" class="small">All observed target-related requests in {run_count} selected traces</text>']
    for panel, agent in enumerate(agents):
        named, unnamed = by_agent[agent]["named"], by_agent[agent]["unidentified"]
        total = named + unnamed
        fraction = named / total if total else 0
        cx, cy, radius = 190 + panel * 600, 235, 120
        start, end = -math.pi / 2, -math.pi / 2 + 2 * math.pi * fraction
        x1, y1 = cx + radius * math.cos(start), cy + radius * math.sin(start)
        x2, y2 = cx + radius * math.cos(end), cy + radius * math.sin(end)
        if 0 < fraction < 1:
            wedge = (f'<path d="M {cx} {cy} L {x1:.2f} {y1:.2f} '
                     f'A {radius} {radius} 0 {int(fraction > .5)} 1 {x2:.2f} {y2:.2f} Z" fill="{GREEN}"/>')
        else:
            wedge = f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="{GREEN if fraction else GRAY}"/>'
        label_x = 335 + panel * 600
        parts += [f'<text x="{cx}" y="89" text-anchor="middle" class="title">{escape(agent)}</text>',
                  f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="{GRAY}"/>', wedge,
                  f'<rect x="{label_x}" y="174" width="15" height="15" fill="{GREEN}"/>',
                  f'<text x="{label_x+20}" y="187" class="small">Named {named:,} ({fraction:.1%})</text>',
                  f'<rect x="{label_x}" y="207" width="15" height="15" fill="{GRAY}"/>',
                  f'<text x="{label_x+20}" y="220" class="small">Unknown {unnamed:,} ({1-fraction:.1%})</text>']
    parts.append('<text x="28" y="408" class="small">Unknown includes numeric-only and missing interface/method labels.</text>')
    output.write_text(svg_base(width, height, "".join(parts)), encoding="utf-8")


def activity_chart(runs, output):
    # Rows are workloads; columns are Agents. Each row shares both axes.
    agents = sorted({agent_label(r["meta"]["target_package"]) for r in runs},
                    key=lambda name: (name != "Gemini", name))
    by_cell = {(agent_label(r["meta"]["target_package"]), r["meta"]["workload"], r["meta"]["repetition"]): r
               for r in runs}
    width, height = 70 + 625 * len(agents), 885
    parts = [f'<rect width="{width}" height="{height}" fill="white"/>',
             '<text x="28" y="34" class="title">Binder activity and task markers</text>',
             '<text x="28" y="53" class="small">Repetition 1; each workload row uses the same x/y scale for both Agents</text>']
    for column, agent in enumerate(agents):
        parts.append(f'<text x="{350 + column*625}" y="82" text-anchor="middle" class="title">{escape(agent)}</text>')
    for row, workload in enumerate(("W0", "W1", "W2")):
        pair = [by_cell.get((agent, workload, 1)) for agent in agents]
        available = [run for run in pair if run]
        if not available:
            continue
        duration = max(len(run["summary"]["timeline"]) for run in available)
        peak = max(t[direction] for run in available for t in run["summary"]["timeline"]
                   for direction in ("incoming", "outgoing")) or 1
        y0, y1 = 125 + row * 245, 290 + row * 245
        for column, run in enumerate(pair):
            if run is None:
                continue
            meta, summary = run["meta"], run["summary"]
            x0, x1 = 75 + column * 625, 620 + column * 625
            parts += [f'<text x="{x0}" y="{y0-18}" class="label">{workload} / run {meta["repetition"]} / {meta["id"][:8]}</text>',
                      f'<line x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}" stroke="#94a3b8"/>',
                      f'<text x="{x0-7}" y="{y0+4}" text-anchor="end" class="small">{peak}</text>',
                      f'<text x="{x0-7}" y="{y1+4}" text-anchor="end" class="small">0</text>']
            for direction, color in (("incoming", BLUE), ("outgoing", ORANGE)):
                points = " ".join(f'{x0+(i+.5)*(x1-x0)/duration:.1f},{y1-t[direction]*(y1-y0)/peak:.1f}'
                                  for i, t in enumerate(summary["timeline"]))
                parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>')
            for marker in summary["markers"]:
                offset = marker.get("offset_seconds")
                if offset is None or not 0 <= offset <= duration:
                    continue
                x = x0 + offset * (x1-x0) / duration
                label = escape(marker["label"].replace("_", " "))
                parts += [f'<line x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y1}" stroke="{GREEN}" stroke-dasharray="4 3"/>',
                          f'<text x="{x+2:.1f}" y="{y0+12}" class="small" transform="rotate(35 {x+2:.1f} {y0+12})">{label}</text>']
            parts += [f'<text x="{x0}" y="{y1+20}" class="small">0 s</text>',
                      f'<text x="{x1}" y="{y1+20}" text-anchor="end" class="small">{duration} s</text>']
    legend_x = width - 315
    parts += [f'<rect x="{legend_x}" y="26" width="12" height="12" fill="{BLUE}"/><text x="{legend_x+16}" y="37" class="small">Incoming</text>',
              f'<rect x="{legend_x+95}" y="26" width="12" height="12" fill="{ORANGE}"/><text x="{legend_x+111}" y="37" class="small">Outgoing</text>',
              f'<line x1="{legend_x+195}" y1="32" x2="{legend_x+209}" y2="32" stroke="{GREEN}" stroke-dasharray="4 3"/><text x="{legend_x+216}" y="37" class="small">Marker</text>']
    output.write_text(svg_base(width, height, "".join(parts)), encoding="utf-8")


def comparison_chart(rows, output):
    groups = defaultdict(list)
    for row in rows:
        groups[row["agent"], row["workload"]].append(row)
    keys = [(agent, workload) for agent in sorted({key[0] for key in groups},
                                                  key=lambda name: (name != "Gemini", name))
            for workload in ("W0", "W1", "W2") if (agent, workload) in groups]
    medians = {key: {direction: statistics.median(r[f"{direction}_per_s"] for r in groups[key])
                     for direction in ("incoming", "outgoing")} for key in keys}
    maximum = max(value for pair in medians.values() for value in pair.values()) or 1
    width, height = 1010, 460
    left, bottom, plot_h = 75, 370, 270
    parts = [f'<rect width="{width}" height="{height}" fill="white"/>',
             '<text x="28" y="34" class="title">Median Binder request rates by Agent and workload</text>',
             '<text x="28" y="54" class="small">Median of per-run full-trace rates; 3 repetitions per cell</text>']
    for tick in range(5):
        value = maximum * tick / 4
        y = bottom - plot_h * tick / 4
        parts += [f'<line x1="{left}" y1="{y:.1f}" x2="970" y2="{y:.1f}" stroke="#e2e8f0"/>',
                  f'<text x="{left-9}" y="{y+4:.1f}" text-anchor="end" class="small">{value:.0f}</text>']
    spacing = (895 / len(keys))
    for i, key in enumerate(keys):
        center = left + (i + .5) * spacing
        for offset, direction, color in ((-30, "incoming", BLUE), (5, "outgoing", ORANGE)):
            value = medians[key][direction]
            bar_h = plot_h * value / maximum
            parts += [f'<rect x="{center+offset:.1f}" y="{bottom-bar_h:.1f}" width="25" height="{bar_h:.1f}" fill="{color}"/>',
                      f'<text x="{center+offset+12.5:.1f}" y="{bottom-bar_h-5:.1f}" text-anchor="middle" class="small">{value:.1f}</text>']
        parts.append(f'<text x="{center:.1f}" y="{bottom+21}" text-anchor="middle" class="small">{escape(key[0])} {key[1]}</text>')
    parts += [f'<rect x="720" y="27" width="13" height="13" fill="{BLUE}"/><text x="738" y="38" class="small">Incoming/s</text>',
              f'<rect x="835" y="27" width="13" height="13" fill="{ORANGE}"/><text x="853" y="38" class="small">Outgoing/s</text>',
              '<text x="510" y="438" text-anchor="middle" class="small">Agent and workload</text>']
    output.write_text(svg_base(width, height, "".join(parts)), encoding="utf-8")
    return medians


def build(runs_root, output, agents=None, exclude_runs=None):
    runs = load_runs(runs_root, agents, exclude_runs)
    if not runs:
        raise ValueError("No complete trace runs with path evidence found")
    output.mkdir(parents=True, exist_ok=True)
    peers, edges, apis, timeline, run_rows = [], [], [], [], []
    named_total = unnamed_total = 0
    api_totals_by_agent = defaultdict(Counter)
    api_aggregate, edge_aggregate = Counter(), Counter()
    api_by_agent, edge_by_agent = defaultdict(Counter), defaultdict(Counter)
    for run in runs:
        meta, summary, tx, paths = (run[k] for k in ("meta", "summary", "tx", "paths"))
        run_id = meta["id"]
        counts = Counter()
        endpoints = {}
        unknown_directions = Counter()
        named_by_key = Counter()
        placeholder_labels = 0
        for item in tx:
            direction = item["direction"]
            if direction in ("incoming", "outgoing"):
                peer = item["sender"] if direction == "incoming" else item["receiver"]
                key = peer_key(peer)
                counts[key] += 1
                endpoints[key] = peer
            if named_api(item):
                named_by_key[item["interface"], item["method"], direction] += 1
            else:
                unknown_directions[direction] += 1
            if (item.get("method") or "").startswith(("#", "Unknown_Transaction_Code:")):
                placeholder_labels += 1
        for key, count in counts.most_common():
            peer = endpoints[key]
            peers.append(dict(run_id=run_id, agent=agent_label(meta["target_package"]),
                              workload=meta["workload"], repetition=meta["repetition"],
                              process=peer.get("process") or "", upid=peer.get("upid"),
                              pid=peer.get("pid"), uid=peer.get("uid"),
                              packages=";".join(peer.get("packages") or []),
                              identity_status=peer.get("identity_status", "unresolved"),
                              transaction_count=count))
        for edge in summary["edges"]:
            edges.append(dict(run_id=run_id, agent=agent_label(meta["target_package"]),
                              workload=meta["workload"], repetition=meta["repetition"], **edge))
            edge_aggregate[clean_process(edge["sender"]), clean_process(edge["receiver"])] += edge["count"]
            edge_by_agent[agent_label(meta["target_package"])][
                clean_process(edge["sender"]), clean_process(edge["receiver"])] += edge["count"]
        for (interface, method, direction), count in named_by_key.items():
            apis.append(dict(run_id=run_id, agent=agent_label(meta["target_package"]),
                             workload=meta["workload"], repetition=meta["repetition"],
                             interface=interface, method=method, direction=direction, count=count))
            api_aggregate[interface, method, direction] += count
            api_by_agent[agent_label(meta["target_package"])][interface, method, direction] += count
        for direction, count in unknown_directions.items():
            apis.append(dict(run_id=run_id, agent=agent_label(meta["target_package"]),
                             workload=meta["workload"], repetition=meta["repetition"],
                             interface="UNIDENTIFIED", method="UNIDENTIFIED", direction=direction, count=count))
        for bucket in summary["timeline"]:
            timeline.append(dict(run_id=run_id, agent=agent_label(meta["target_package"]),
                                 workload=meta["workload"], repetition=meta["repetition"], **bucket))
        named = sum(named_by_key.values())
        unnamed = sum(unknown_directions.values())
        assert named + unnamed == summary["transaction_count"] == len(tx)
        assert len(paths) == len(summary["candidate_paths"])
        assert all(len(p["hops"]) == 2 and all(p["hops"]) and p["same_serving_thread_nested"] for p in paths)
        named_total += named
        unnamed_total += unnamed
        api_totals_by_agent[agent_label(meta["target_package"])].update(
            named=named, unidentified=unnamed)
        directions = summary["direction_counts"]
        run_rows.append(dict(run_id=run_id, agent=agent_label(meta["target_package"]),
                             workload=meta["workload"], repetition=meta["repetition"],
                             duration_s=summary["trace_duration_seconds"],
                             peer_count=summary["peer_process_count"], directed_edges=len(summary["edges"]),
                             incoming=directions.get("incoming", 0), outgoing=directions.get("outgoing", 0),
                             internal=directions.get("internal", 0),
                             incoming_per_s=summary["rates_per_second"]["incoming"],
                             outgoing_per_s=summary["rates_per_second"]["outgoing"],
                             matched_sync_calls=summary["matched_sync_calls"],
                             median_ms=summary["sync_latency_ms"]["median"],
                             p95_ms=summary["sync_latency_ms"]["p95"],
                             named_api_requests=named, unidentified_api_requests=unnamed,
                             numeric_method_labels=placeholder_labels,
                             path_candidates=len(paths),
                             path_candidates_in_task_window=sum(p["task_window"]["both_hops_inside"] for p in paths),
                             unknown_incoming=unknown_directions["incoming"],
                             unknown_outgoing=unknown_directions["outgoing"],
                             unknown_internal=unknown_directions["internal"]))
    csv_file(output / "runs.csv", list(run_rows[0]), run_rows)
    csv_file(output / "peers.csv", list(peers[0]), peers)
    csv_file(output / "directed_edges.csv", list(edges[0]), edges)
    csv_file(output / "api_counts.csv", list(apis[0]), apis)
    csv_file(output / "timeline_1s.csv", list(timeline[0]), timeline)
    bins = histogram(runs, output / "transaction_histogram.svg")
    pie_chart(api_totals_by_agent, output / "api_coverage_pie.svg", len(runs))
    activity_chart(runs, output / "activity_timeline.svg")
    medians = comparison_chart(run_rows, output / "agent_rate_comparison.svg")

    m1 = [[r["agent"], r["workload"], r["repetition"], r["run_id"][:8], r["peer_count"], r["directed_edges"],
           r["incoming"], r["outgoing"], r["internal"]] for r in run_rows]
    m2 = [[r["agent"], r["workload"], r["repetition"], r["run_id"][:8], f'{r["duration_s"]:.1f}',
           f'{r["incoming_per_s"]:.1f}', f'{r["outgoing_per_s"]:.1f}', r["matched_sync_calls"],
           f'{r["median_ms"]:.3f}' if r["median_ms"] is not None else "—",
           f'{r["p95_ms"]:.3f}' if r["p95_ms"] is not None else "—"] for r in run_rows]
    m3 = [[r["agent"], r["workload"], r["repetition"], r["run_id"][:8], r["named_api_requests"],
           r["unidentified_api_requests"], r["numeric_method_labels"],
           r["path_candidates"], r["path_candidates_in_task_window"]] for r in run_rows]
    top_api = [[interface, method, direction, count]
               for (interface, method, direction), count in api_aggregate.most_common(12)]
    top_edges = [[sender, receiver, count] for (sender, receiver), count in edge_aggregate.most_common(10)]
    peer_by_name = Counter()
    peer_by_agent = defaultdict(Counter)
    for item in peers:
        peer_by_name[item["process"] or "Unresolved"] += item["transaction_count"]
        peer_by_agent[item["agent"]][item["process"] or "Unresolved"] += item["transaction_count"]
    top_peers = [[name, count] for name, count in peer_by_name.most_common(5)]
    total_paths = sum(r["path_candidates"] for r in run_rows)
    window_paths = sum(r["path_candidates_in_task_window"] for r in run_rows)
    total_requests = sum(r["incoming"] + r["outgoing"] + r["internal"] for r in run_rows)
    comparison = [[agent, workload, len([r for r in run_rows if (r["agent"], r["workload"]) == key]),
                   f'{rates["incoming"]:.2f}', f'{rates["outgoing"]:.2f}']
                  for key, rates in medians.items() for agent, workload in (key,)]
    selected_agents = sorted({r["meta"]["target_package"] for r in runs})
    paired = {agent_label(package) for package in selected_agents} == {"Gemini", "ChatGPT"}
    if paired:
        by_agent = {agent: [r for r in run_rows if r["agent"] == agent]
                    for agent in ("Gemini", "ChatGPT")}
        overview_rows = [["Runs", len(by_agent["Gemini"]), len(by_agent["ChatGPT"])]]
        overview_rows += [
            [label, f"{sum(r[field] for r in by_agent['Gemini']):,}",
             f"{sum(r[field] for r in by_agent['ChatGPT']):,}"]
            for label, field in (("Incoming requests", "incoming"),
                                 ("Outgoing requests", "outgoing"), ("Internal requests", "internal"),
                                 ("Named API requests", "named_api_requests"),
                                 ("Unidentified API requests", "unidentified_api_requests"),
                                 ("Two-hop candidates", "path_candidates"),
                                 ("Both hops in task window", "path_candidates_in_task_window"))]
        overview = md_table(["Observed quantity", "Gemini (left)", "ChatGPT (right)"], overview_rows)
        m1_table = md_table(["Workload / rep", "Gemini (left)", "ChatGPT (right)"], paired_rows(run_rows, lambda r:
            f'`{r["run_id"][:8]}`<br>Peers {r["peer_count"]} · edges {r["directed_edges"]}<br>'
            f'In {r["incoming"]:,} · out {r["outgoing"]:,} · internal {r["internal"]:,}'))
        m2_table = md_table(["Workload / rep", "Gemini (left)", "ChatGPT (right)"], paired_rows(run_rows, lambda r:
            f'`{r["run_id"][:8]}`<br>Trace {r["duration_s"]:.1f}s · in {r["incoming_per_s"]:.1f}/s · out {r["outgoing_per_s"]:.1f}/s<br>'
            f'Matched sync {r["matched_sync_calls"]:,} · median {r["median_ms"]:.3f}ms · p95 {r["p95_ms"]:.3f}ms'))
        m3_table = md_table(["Workload / rep", "Gemini (left)", "ChatGPT (right)"], paired_rows(run_rows, lambda r:
            f'`{r["run_id"][:8]}`<br>Named API {r["named_api_requests"]:,} · unidentified {r["unidentified_api_requests"]:,}'
            f'<br>Code/placeholder {r["numeric_method_labels"]:,} · two-hop {r["path_candidates"]:,}'
            f' · in window {r["path_candidates_in_task_window"]:,}'))
        median_table = md_table(["Workload", "Gemini (left)", "ChatGPT (right)"], [
            [w, f'In {medians["Gemini", w]["incoming"]:.2f}/s · out {medians["Gemini", w]["outgoing"]:.2f}/s',
             f'In {medians["ChatGPT", w]["incoming"]:.2f}/s · out {medians["ChatGPT", w]["outgoing"]:.2f}/s']
            for w in ("W0", "W1", "W2")])
        peer_table = side_by_side_ranking(peer_by_agent["Gemini"], peer_by_agent["ChatGPT"], 5, str)
        edge_table = side_by_side_ranking(edge_by_agent["Gemini"], edge_by_agent["ChatGPT"], 10,
                                          lambda edge: f"{edge[0]} → {edge[1]}")
        api_table = side_by_side_ranking(api_by_agent["Gemini"], api_by_agent["ChatGPT"], 12,
                                         lambda api: f"{api[0]}.{api[1]} ({api[2]})")
    else:
        overview = ""
        m1_table = md_table(["Agent", "Workload", "Rep", "Run", "Peers", "Directed edges", "Incoming", "Outgoing", "Internal"], m1)
        m2_table = md_table(["Agent", "Workload", "Rep", "Run", "Trace s", "In/s", "Out/s", "Matched sync", "Median ms", "P95 ms"], m2)
        m3_table = md_table(["Agent", "Workload", "Rep", "Run", "Named API", "Unidentified", "Code/placeholder label", "Two-hop candidates", "Both in task window"], m3)
        median_table = md_table(["Agent", "Workload", "Runs", "Median incoming/s", "Median outgoing/s"], comparison)
        peer_table = md_table(["Peer process name", "Observed requests"], top_peers)
        edge_table = md_table(["Sender", "Receiver", "Requests"], top_edges)
        api_table = md_table(["Interface", "Method", "Direction", "Requests"], top_api)
    agent_names = ", ".join(agent_label(package) for package in selected_agents)
    selection = (f"Selected packages: {', '.join(selected_agents)}. "
                 f"Excluded run IDs: {', '.join(sorted(exclude_runs or ())) or 'none'}. ")
    conditions_note = ("The user confirmed no app updates during collection and comparable W2 voice input modes. "
                       if set(selected_agents) == {"com.google.android.googlequicksearchbox", "com.openai.chatgpt"}
                       else "")
    lines = [
        f"# Metrics 1–3: observed Binder communication ({agent_names})",
        "",
        f"Source: {len(runs)} completed Perfetto traces in `runs/`. {selection}{conditions_note}All figures are observed requests involving each selected target Agent. Run IDs in the tables are shortened for display; the CSV files contain full IDs.",
        "",
        "Reading order for the formal comparison: **Gemini is on the left; ChatGPT is on the right** in the paired tables and charts. Each paired row matches the same workload and repetition number, not identical trace duration or identical internal implementation.",
        "",
        f"Across these traces: **{total_requests:,} target-related requests**, **{named_total:,} named interface/method requests**, **{unnamed_total:,} unidentified API requests**, and **{total_paths:,} structural two-hop candidates** ({window_paths:,} with both hops in the task window). Counts across runs are observations, not distinct user actions.",
        "",
        overview,
        "",
        "## Metric 1 — Communication structure",
        "",
        "Peer count is the number of distinct resolved peer processes within each trace. The full [peer identity table](peers.csv) keeps trace-specific UPID/PID, UID, available package mappings and unresolved labels. [Directed edges](directed_edges.csv) preserve sender → receiver and the request count for every run. Incoming and outgoing count requests from the target's perspective; internal requests between target processes are separate. Replies are not counted as new requests.",
        "",
        m1_table,
        "",
        "Most frequent peer process names within each Agent (a name can represent different trace-specific processes):",
        "",
        peer_table,
        "",
        "Most frequent directed process-name pairs within each Agent (full per-run identifiers and weights are in `directed_edges.csv`):",
        "",
        edge_table,
        "",
        "## Metric 2 — Communication timing",
        "",
        "Rates divide each run's incoming/outgoing request counts by its full trace duration. Latency uses only synchronous calls with a matched reply; the median and p95 are calculated per run and are not pooled. The [one-second timeline](timeline_1s.csv) contains incoming, outgoing and internal counts. Task marker times remain in each run's `summary.json`.",
        "",
        m2_table,
        "",
        "Median rates across selected repetitions (these use the full trace, including setup and completion margins):",
        "",
        median_table,
        "",
        "![Median incoming and outgoing Binder rates by Agent and workload](agent_rate_comparison.svg)",
        "",
        "![Histogram of one-second incoming and outgoing Binder request counts](transaction_histogram.svg)",
        "",
        f"The histogram shows Gemini on the left and ChatGPT on the right for this selected cohort. It counts full one-second intervals from {len(runs)} traces; the last partial interval of each trace is omitted. Both panels share a vertical scale. Bars show how often a one-second interval falls in each request-count range, not total requests.",
        "",
        "![One-second Binder activity and task markers for repetition 1 of each Agent and workload](activity_timeline.svg)",
        "",
        "The timeline shows repetition 1 for each Agent/workload, chosen in advance. Gemini is left and ChatGPT right. The two panels in each workload row share both time and count scales; scales may differ across W0/W1/W2 rows. Green dashed lines are operator task markers. Inspect `timeline_1s.csv` and `summary.json` for exact values and marker timestamps. The five top peers for every run are in its `summary.json`; the full ranking is in `peers.csv`.",
        "",
        "## Metric 3 — Interfaces and mediated paths",
        "",
        "A request is counted as a named API only when both a Binder interface and a nonplaceholder method name are identified. Numeric-only (`#...`), `Unknown_Transaction_Code:...`, and missing method labels are grouped as unidentified. The complete [interface/API table](api_counts.csv) includes direction and separate unidentified counts. A transaction code alone does not uniquely identify an API; raw codes and endpoints remain in each run's `transactions.json` and `path_evidence.json`.",
        "",
        m3_table,
        "",
        "![Side-by-side pie charts of named and unidentified API requests for Gemini and ChatGPT](api_coverage_pie.svg)",
        "",
        "Most frequent identified interface/method/direction groups:",
        "",
        api_table,
        "",
        "A structural two-hop candidate means the intermediary's serving thread started a second Binder request before the first server slice ended. All exported pairs have both transaction records and satisfy this timing condition. They remain **candidates**, including those inside task windows: the trace cannot establish user-task causality, payload contents, or an intermediary service's semantic role by timing alone. The [Gemini path audit](../2026-11-23-path-review.md) and [formal matrix review](../2026-11-24-formal-matrix.md) check examples against raw `.pftrace`. There is currently no verified instruction-specific agent → other-app path/hop count to report as a completed task path.",
        "",
        "### Example candidate paths",
        "",
        md_table(["Workload", "Gemini (left)", "ChatGPT (right)"], [
            ["W1 browser", "`e7366222`: Gemini → system_server `activityPaused` → browser `scheduleTransaction`; TID 2583",
             "`bc99d552`: ChatGPT → system_server `activityPaused` → browser `scheduleTransaction`; TID 4360"],
            ["W2 audio", "`44b901eb`: Gemini → audioserver `getParameters` → MediaTek audio HAL; TID 8693",
             "`80abb11e`: ChatGPT → audioserver `createRecord` → MediaTek audio HAL; TID 12574"],
        ]),
        "",
        "Each example contains two observed requests on the same serving thread inside its task window. None proves that the task caused the pair or reveals a message payload. The W2 paths show different audio API calls and should not be treated as equivalent operations.",
        "",
        "### Data quality and scope",
        "",
        f"- All {len(runs)} included runs are marked complete and success in metadata. The plots are descriptive; three trials per Agent/workload are too few to infer population-level effects.",
        "- UPIDs are trace-specific. Aggregate name tables can merge separate process instances; use `peers.csv` and `directed_edges.csv` for per-run identities.",
        "- A shared UID can map to many packages, especially system services. The package list is an available mapping, not proof that every listed package was the active Binder endpoint.",
        "- Binder replies are excluded from request counts. Synchronous latency is unavailable when the reply cannot be matched; absent values must stay empty.",
        "- The operator confirmed that ChatGPT W1 used the phone app's Remote/Codex computer session. Thus `com.openai.chatgpt` represents the remote UI, not necessarily the action executor. A separate desktop Codex session at 13:48 Pacific on November 24 used `adb shell am start -a android.intent.action.VIEW -d https://www.wikipedia.org` to open the URL on the phone, but that session occurred after the three formal W1 captures (13:28, 13:36 and 13:37) and does not establish their exact execution commands. W1 Binder comparisons remain descriptive process observations; do not interpret them as equivalent direct mobile-agent action traces.",
        "- Current Perfetto data do not include Intent extras, URL, spoken content or Parcel payload. New authorized instrumentation or content capture is required for those fields.",
        "",
        "Regenerate with the `--agent` and `--exclude-run` options shown in the project README.",
        "",
    ]
    (output / "metrics.md").write_text("\n".join(lines), encoding="utf-8")
    return {"runs": len(runs), "requests": total_requests, "named": named_total,
            "unidentified": unnamed_total, "paths": total_paths,
            "paths_in_task_window": window_paths, "histogram": bins}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=Path("runs"))
    parser.add_argument("--output", type=Path, default=Path("reports/2026-11-23-metrics-1-3"))
    parser.add_argument("--agent", action="append", dest="agents",
                        help="Include only this target package; repeat for multiple Agents")
    parser.add_argument("--exclude-run", action="append", dest="excluded_runs",
                        help="Retain but omit this run ID from the report")
    args = parser.parse_args()
    print(json.dumps(build(args.runs, args.output, args.agents, args.excluded_runs), indent=2))
