"use strict";
const $ = (id) => document.getElementById(id);
const native = window.ProjectB;
function floatingStatus() {
  const supported = native && typeof native.floatingMarkersEnabled === "function";
  $("floating-settings").disabled = !supported;
  $("floating-status").textContent = !supported ? "Floating controls require Project B APK 1.3 or newer."
    : native.floatingMarkersEnabled() ? "Floating controls enabled. A draggable dot appears on the right during recording; tap to expand the three task markers."
    : "Allow Display over other apps for Project B, then return here. Until enabled, use notification markers.";
}
$("floating-settings").onclick = () => { if (native) native.floatingMarkerSettings(); };
floatingStatus();
const state = {
  get: (key) => native ? native.loadState(key) : sessionStorage.getItem(key),
  set: (key, value) => native ? native.saveState(key, value) : sessionStorage.setItem(key, value)
};
const terminal = new Set(["complete", "failed"]);
let active = state.get("run") || "";
let renderedRun = "";
let groundRun = "";
let browserPackageEdited = false;
let availableRuns = [];
let polling = false;
let installedApps = [];
let packageGeneration = 0;
let detailGeneration = 0;
let packagesLoaded = false;

function clearPackages() {
  packageGeneration++;
  detailGeneration++;
  installedApps = [];
  packagesLoaded = false;
  $("package").value = "";
  $("package-results").replaceChildren();
  $("package-status").textContent = "Load apps for the selected device.";
  $("package-selection").textContent = "No app selected.";
  $("packages").disabled = false;
}
function renderPackages() {
  const query = $("package-search").value.trim().toLocaleLowerCase();
  const matches = installedApps.filter((app) => ($("all-packages").checked || app.names.length) &&
    [app.package, ...app.names].some((value) => value.toLocaleLowerCase().includes(query)));
  $("package-results").replaceChildren(...matches.map((app) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "package-option";
    button.setAttribute("aria-pressed", String(app.package === $("package").value.trim()));
    const title = document.createElement("strong");
    title.textContent = app.names.join(" / ") || "App name unavailable";
    const name = document.createElement("span");
    name.textContent = app.package;
    button.append(title, name);
    button.onclick = action(async () => {
      $("package").value = app.package;
      renderPackages();
      await checkPackage();
    });
    return button;
  }));
  if (packagesLoaded) $("package-status").textContent = matches.length
    ? `${matches.length} matching apps / ${installedApps.length} installed packages. Tap an app to select it.`
    : "No matching apps. Try another keyword, include unnamed packages, or enter the package manually.";
}
async function checkPackage() {
  const generation = ++detailGeneration;
  const serial = $("device").value;
  const name = $("package").value.trim();
  if (!serial || !name) {
    $("package-selection").textContent = "Select a device and enter a package first.";
    return;
  }
  $("package-selection").textContent = "Checking installation and version…";
  try {
    const details = await api("devices/package-details", {serial, package: name});
    if (generation !== detailGeneration || serial !== $("device").value || name !== $("package").value.trim()) return;
    const app = installedApps.find((a) => a.package === name);
    $("package-selection").textContent = `Selected: ${app?.names.join(" / ") || "App name unavailable"}\nPackage: ${details.package}\nVersion: ${details.version || "unavailable"}\nVersion code: ${details.version_code ?? "unavailable"}\nUID: ${details.uid}`;
  } catch (error) {
    if (generation === detailGeneration) $("package-selection").textContent = "Could not verify package: " + error.message;
  }
}

async function api(path, body, raw = false) {
  const response = await fetch("/api/" + path, {
    method: body === undefined ? "GET" : "POST",
    headers: {Authorization: "Bearer " + $("token").value.trim(), "Content-Type": "application/json",
              "X-ProjectB-Client": native ? "android" : "desktop"},
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  if (!response.ok) throw Error((await response.json()).error);
  return raw ? response : response.json();
}
function action(work) {
  return async (event) => {
    event?.preventDefault();
    try { await work(); }
    catch (error) { $("message").textContent = error.message; }
  };
}
function select(id, values, selected, placeholder) {
  $(id).replaceChildren(new Option(placeholder, ""), ...values.map(([key, title]) => new Option(title, key)));
  $(id).value = selected;
}
function list(id, values, empty) {
  $(id).replaceChildren(...(values.length ? values : [empty]).map((value) => {
    const li = document.createElement("li");
    li.textContent = value;
    return li;
  }));
}
const descriptions = {
  W0: "Open the Agent, wait for it to stabilize, then leave it untouched for 30 seconds.",
  W1: "Submit: Open https://www.wikipedia.org in my phone’s browser. Record confirmations and the outcome.",
  W2: "Use voice input to speak the W1 prompt. Mark voice start/end and response completion."
};
function workloadChanged() {
  $("seconds").value = $("workload").value === "W0" ? 40 : 90;
  $("instructions").textContent = descriptions[$("workload").value];
}
function modeChanged() {
  $("simpleperf_enabled").disabled = $("mode").value !== "trace";
  if ($("simpleperf_enabled").disabled) $("simpleperf_enabled").checked = false;
  workloadChanged();
}
$("mode").onchange = modeChanged;
$("simpleperf-probe").onclick = action(async () => {
  $("simpleperf-capabilities").textContent = "Checking non-root profiling support…";
  try {
    const r = await api("devices/simpleperf-capabilities", {serial: $("device").value, package: $("package").value.trim()});
    $("simpleperf-capabilities").textContent = (r.eligible ? "Ready to attempt: " : "Unavailable: ") + r.reason;
  } catch (error) { $("simpleperf-capabilities").textContent = error.message; }
});
workloadChanged();
$("workload").onchange = workloadChanged;
$("token").value = state.get("token") || "";
for (const key of ["device_label", "conditions"]) $(key).value = state.get(key) || "";
async function connect() {
  state.set("token", $("token").value.trim());
  const old = $("device").value;
  await refresh(true);
  try {
    const devices = await api("devices");
    select("device", devices.map((id) => [id, id]), devices.includes(old) ? old : devices[0] || "", "Select a device");
    if (old !== $("device").value) clearPackages();
    $("message").textContent = devices.length ? "Connected." : "Connected. No authorized ADB devices.";
  } catch (error) {
    $("message").textContent = "Backend connected. ADB: " + error.message;
  }
}
$("connect").onclick = action(connect);
$("packages").onclick = action(async () => {
  const serial = $("device").value;
  if (!serial) { $("package-status").textContent = "Connect and select an ADB device first."; return; }
  clearPackages();
  const generation = packageGeneration;
  $("packages").disabled = true;
  $("package-status").textContent = "Loading installed packages…";
  try {
    const packages = await api("devices/packages", {serial});
    if (generation !== packageGeneration || serial !== $("device").value) return;
    const labels = new Map();
    if (native && typeof native.appLabels === "function") {
      try {
        for (const app of JSON.parse(native.appLabels())) {
          if (!labels.has(app.package)) labels.set(app.package, new Set());
          labels.get(app.package).add(app.name);
        }
      } catch (_) { /* Package-only search remains available. */ }
    }
    installedApps = packages.map((name) => ({package: name, names: [...(labels.get(name) || [])]}));
    installedApps.sort((a, b) => (a.names[0] || a.package).localeCompare(b.names[0] || b.package));
    const hasLabels = installedApps.some((a) => a.names.length);
    $("all-packages").checked = !hasLabels;
    $("package-help").textContent = hasLabels
      ? "Search app names or package names. Names come from this phone: select this same phone in ADB. Versions are checked on the selected ADB device."
      : "Package-name search is available. For app-name search, install the updated Project B APK on the selected phone. Unavailable names are not guessed.";
    packagesLoaded = true;
    renderPackages();
  } catch (error) {
    if (generation === packageGeneration) $("package-status").textContent = "Could not load apps: " + error.message + ". Check the connection and retry.";
  } finally {
    if (generation === packageGeneration) $("packages").disabled = false;
  }
});
$("device").addEventListener("change", clearPackages);
$("package-search").addEventListener("input", renderPackages);
$("all-packages").addEventListener("change", renderPackages);
$("package-check").onclick = action(checkPackage);
$("select-chatgpt").onclick = action(async () => {
  $("package").value = "com.openai.chatgpt";
  $("package-search").value = "com.openai.chatgpt";
  renderPackages();
  await checkPackage();
});
$("package").addEventListener("input", () => {
  detailGeneration++;
  $("package-selection").textContent = "Manual entry: click Check selected package to verify installation and version.";
  renderPackages();
});
function choose(id) {
  active = id;
  state.set("run", id);
  renderedRun = "";
  $("results").hidden = true;
  $("exports").replaceChildren();
  $("quality").textContent = "";
}
$("setup").onsubmit = action(async () => {
  for (const key of ["device_label", "conditions"]) state.set(key, $(key).value.trim());
  const run = await api("runs", {
    serial: $("device").value, target_package: $("package").value.trim(), workload: $("workload").value,
    duration_seconds: Number($("seconds").value), repetition: Number($("repetition").value),
    mode: $("mode").value, device_label: $("device_label").value.trim(), conditions: $("conditions").value.trim(),
    simpleperf_enabled: $("simpleperf_enabled").checked
  });
  choose(run.id);
  await refresh(true);
});
$("history").onchange = action(async () => {
  choose($("history").value);
  await refresh(true);
});
$("marker-form").onsubmit = action(async () => {
  const body = {label: $("marker").value};
  if (native) body.boottime_ns = native.boottimeNs();
  await api("runs/" + active + "/markers", body);
  $("marker").value = "";
  await refresh(true);
});
$("stop").onclick = action(async () => {
  await api("runs/" + active + "/stop", {});
  $("stop").disabled = true;
  await refresh(true);
});
const fields = ["outcome", "notes", "browser_package", "recognized_text", "actual_response"];
$("browser_package").addEventListener("input", () => { browserPackageEdited = true; });
$("ground").onsubmit = action(async () => {
  await api("runs/" + active + "/outcome", Object.fromEntries(fields.map((key) => [key, $(key).value])));
  $("message").textContent = "Ground truth saved.";
  browserPackageEdited = false;
  renderedRun = "";
  await refresh(true);
});
async function refresh(force = false) {
  floatingStatus();
  if (polling && !force) return;
  polling = true;
  try {
    const runs = await api("runs");
    const busy = runs.find((run) => !terminal.has(run.status));
    if (native) native.recording(busy?.status === "recording" ? busy.id : "",
                                 busy?.workload || "", $("token").value.trim(),
                                 busy?.duration_seconds || 0);
    if (!active && busy) choose(busy.id);
    if (JSON.stringify(runs.map((r) => r.id)) !== JSON.stringify(availableRuns)) {
      availableRuns = runs.map((r) => r.id);
      select("history", runs.map((r) => [r.id, (r.mode || "trace") + " · " + r.workload + " · " + r.target_package + " · " +
             new Date(r.created_at).toLocaleString()]), active, "Select a run");
    }
    $("history").value = active;
    const run = runs.find((r) => r.id === active);
    $("start").disabled = Boolean(busy);
    $("stop").disabled = !["preparing", "recording"].includes(run?.status);
    $("add-marker").disabled = run?.status !== "recording";
    $("ground").hidden = !run;
    $("status").textContent = run ? (run.mode === "baseline" ? "Baseline (no Perfetto) · " : "") + run.status + (run.error ? " · " + run.failed_stage + ": " + run.error : "") : "";
    list("markers", run?.markers.map((m) => m.label) || [], "No markers recorded.");
    if (run && groundRun !== run.id) {
      fields.forEach((key) => { $(key).value = run[key] || ""; });
      groundRun = run.id;
      browserPackageEdited = false;
    }
    if (run && !browserPackageEdited && $("browser_package").value !== (run.browser_package || "")) {
      $("browser_package").value = run.browser_package || "";
      renderedRun = "";
    }
    $("simpleperf-status").textContent = run?.simpleperf_requested
      ? "Simpleperf diagnostic · " + (run.simpleperf?.status || "pending") +
        (run.simpleperf?.sample_count != null ? ` · ${run.simpleperf.sample_count} samples` : "") +
        (run.simpleperf?.reason ? " · " + run.simpleperf.reason : "") +
        " · Excluded from formal comparisons. See simpleperf.json and available report files."
      : "";
    const detection = run?.browser_detection;
    $("browser-detection").textContent = detection?.status === "pending" ? "Checking the foreground browser…"
      : detection?.status === "detected" ? "Detected browser: " + detection.package + ". Confirm the webpage actually appeared; any manual entry is preserved."
      : detection?.reason || "Browser detection runs when a browser_launched marker is saved.";
    if (run && terminal.has(run.status) && renderedRun !== run.id) {
      const names = await api("runs/" + run.id + "/artifacts");
      const quality = await api("runs/" + run.id + "/quality");
      const summary = names.includes("summary.json") ? await api("runs/" + run.id + "/summary.json") : null;
      if (active === run.id) {
        if (summary) render(summary, run.id);
        renderExports(names, run.id);
        $("quality").textContent = quality.valid ? "Ground truth and available trace checks passed." : quality.issues.join(" · ");
        renderedRun = run.id;
      }
    }
  } finally {
    polling = false;
  }
}
function svgNode(name, attrs, text) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  if (text !== undefined) node.textContent = text;
  return node;
}
function timeline(summary) {
  const bins = summary.timeline;
  const chart = svgNode("svg", {width: Math.max(330, bins.length * 7 + 30), height: 160,
                                role: "img", "aria-label": "Binder requests per second"});
  const sum = (b) => b.incoming + b.outgoing + b.internal;
  const peak = Math.max(1, ...bins.map(sum));
  chart.append(svgNode("text", {x: 0, y: 14}, "Peak " + peak));
  for (const b of bins) {
    const height = 105 * sum(b) / peak;
    const bar = svgNode("rect", {x: 16 + 7 * b.second, y: 130 - height, width: 6, height, fill: "#126078"});
    bar.append(svgNode("title", {}, b.second + "s: " + sum(b)));
    chart.append(bar);
  }
  for (const m of summary.markers.filter((marker) => marker.inside_trace)) {
    const x = 16 + 7 * m.offset_seconds;
    const line = svgNode("line", {x1: x, x2: x, y1: 24, y2: 135, stroke: "#d05b00", "stroke-width": 2});
    line.append(svgNode("title", {}, m.label + " at " + m.offset_seconds.toFixed(2) + "s"));
    chart.append(line);
  }
  chart.append(svgNode("text", {x: 16, y: 153}, "0s"));
  $("timeline").replaceChildren(chart);
}
function graph(edges) {
  const top = edges.slice(0, 12);
  const sources = [...new Set(top.map((edge) => edge.sender))];
  const sinks = [...new Set(top.map((edge) => edge.receiver))];
  const chart = svgNode("svg", {width: 810, height: Math.max(60, Math.max(sources.length, sinks.length) * 33 + 35),
                                role: "img", "aria-label": "Directed process interaction graph"});
  const defs = svgNode("defs", {});
  const arrow = svgNode("marker", {id: "arrow", markerWidth: 9, markerHeight: 9, refX: 8, refY: 4,
                                    orient: "auto", markerUnits: "userSpaceOnUse"});
  arrow.append(svgNode("path", {d: "M0,0 L8,4 L0,8 Z", fill: "#126078"}));
  defs.append(arrow);
  chart.append(defs);
  const y = (i) => 48 + i * 33;
  for (const edge of top) {
    const line = svgNode("line", {x1: 290, x2: 510, y1: y(sources.indexOf(edge.sender)),
                                  y2: y(sinks.indexOf(edge.receiver)), stroke: "#126078",
                                  "stroke-width": Math.min(7, 1 + Math.log2(edge.count)), "marker-end": "url(#arrow)"});
    line.append(svgNode("title", {}, edge.sender + " → " + edge.receiver + ": " + edge.count));
    chart.append(line);
  }
  for (const [names, x, heading] of [[sources, 4, "Sender"], [sinks, 520, "Receiver"]]) {
    chart.append(svgNode("text", {x, y: 19, "font-weight": "bold"}, heading));
    names.forEach((name, i) => {
      const label = svgNode("text", {x, y: y(i) + 5, "font-size": 13}, name.length > 40 ? name.slice(0, 39) + "…" : name);
      label.append(svgNode("title", {}, name));
      chart.append(label);
    });
  }
  $("graph").replaceChildren(top.length ? chart : "No observed edges.");
}
function render(s, id) {
  $("results").hidden = false;
  const format = (value) => value == null ? "unavailable" : value.toFixed(2);
  $("metrics").textContent = s.transaction_count + " requests · " + s.peer_process_count + " resolved peers · " +
    (s.direction_counts.outgoing || 0) + " outgoing (" + format(s.rates_per_second.outgoing) + "/s) · " +
    (s.direction_counts.incoming || 0) + " incoming (" + format(s.rates_per_second.incoming) + "/s) · " +
    s.matched_sync_calls + " matched synchronous calls · median " + format(s.sync_latency_ms.median) +
    " ms · p95 " + format(s.sync_latency_ms.p95) + " ms";
  list("warnings", s.warnings, "No trace quality warnings detected.");
  list("peers", s.top_peers.map(([peer, count]) => peer + ": " + count), "No resolved peers.");
  list("interfaces", [...s.interfaces.slice(0, 10).map((i) => i.interface + "." + i.method + " · " +
    i.direction + " · " + i.count), s.unidentified_interface_count + " requests with unidentified interfaces."], "");
  list("paths", s.candidate_paths.slice(0, 10).map((p) => p.processes.join(" → ") + " · " +
    p.hops + " hops · " + p.evidence), "No candidate paths found.");
  timeline(s);
  graph(s.edges);
}
async function download(path, name) {
  if (native) {
    native.exportFile(path, $("token").value.trim());
    return;
  }
  const response = await api(path, undefined, true);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function renderExports(names, id) {
  $("exports").replaceChildren(...names.map((name) => {
    const button = document.createElement("button");
    button.textContent = name;
    button.onclick = action(() => download("runs/" + id + "/" + name, name));
    return button;
  }));
}
$("evaluate").onclick = action(async () => {
  const r = await api("evaluation.json");
  const percent = (n) => n == null ? "unavailable" : (100 * n).toFixed(1) + "%";
  const lines = [r.protocol_has_at_least_two_agents_with_three_repetitions ? "Workload matrix complete." : "Workload matrix incomplete.",
    "Classifier coverage: " + percent(r.classification_coverage) + "; accuracy on classified successful tasks: " + percent(r.accuracy_when_classified),
    ...r.coverage.map((g) => `${g.device} / ${g.conditions} / ${g.agent} / ${g.workload}: ${g.distinct_repetitions} valid repetitions, ${g.successful_runs} successes`),
    "Simpleperf diagnostic runs: " + (r.simpleperf_runs || []).length,
    "Excluded classifier runs: " + r.excluded_runs.length,
    "Paired overhead trials: " + r.overhead.pairs.length,
    ...r.overhead.groups.map((g) => `${g.agent} / ${g.workload}: ${g.pair_count} pairs, median task time change ${g.median_delta_seconds.toFixed(2)}s (${g.median_relative_change_percent.toFixed(1)}%)`),
    "Overhead measures incremental tracing impact with the controller enabled; operator and network variation remain.",
    "Download evaluation JSON for per-run evidence, outcomes, uncertain predictions and exclusions."];
  $("evaluation").textContent = lines.join("\n");
});
$("evaluation-export").onclick = action(() => download("evaluation.json", "evaluation.json"));
if ($("token").value) action(connect)();
setInterval(() => {
  if ($("token").value) refresh().catch((error) => { $("message").textContent = error.message; });
}, 1800);
