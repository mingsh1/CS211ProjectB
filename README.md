# CS 211 Project B · Mobile Agent Communication Analyzer

An Android controller and Windows-friendly Python backend for observing Binder requests involving a selected Agent on an unrooted phone. The Agent itself is a separate app. The laptop records with ADB and Perfetto, then serves results to the controller over the lab network.

The primary local checkout is `C:\CS211ProjectB`. Clone this repository with `git clone https://github.com/mingsh1/CS211ProjectB.git`, then run setup commands from its root. Local experiment data, access codes, virtual environments and caches are intentionally excluded from Git. A prebuilt debug APK is available at [artifacts/apk/app-debug.apk](artifacts/apk/app-debug.apk); rebuild from source after Android code changes. See [PLAN.md](PLAN.md) for the original-course-requirement mapping and remaining acceptance gates, and [REPORT_TEMPLATE.md](REPORT_TEMPLATE.md) for the final report outline. Code and fixture tests do not replace real-phone acceptance or the required experimental dataset.

## Optional Simpleperf diagnostics

See [SIMPLEPERF.md](SIMPLEPERF.md) for the OPPO Find X7 / Android 16 / Gemini procedure. Enable the optional checkbox for additional Binder trace diagnostic runs. These runs are excluded from the formal workload matrix and standard overhead comparisons. Permission failures save evidence without stopping Binder collection. Actual Gemini profiling support still requires a phone test.

After this update, restart this repository's backend and install `artifacts/apk/app-debug.apk` (1.6). Updating only the APK does not update the laptop collector or web UI.

## Code outline

| Source | Responsibility |
| --- | --- |
| `backend/collector.py` and `backend/trace.pbtx` | Select an ADB device, look up installed packages and UIDs, start and stop Perfetto, collect Binder and process data, and retrieve the trace. |
| `backend/server.py` | Authenticate requests, coordinate one active experiment, persist state and ground truth, and serve the UI and exports. |
| `backend/analyzer.py` | Attribute process lifetimes, extract Binder requests, summarize peer identities, direction, rates, timing and API evidence, and export JSON and CSV. |
| `backend/web/` | Device and Agent selection, experiment controls, run history, ground truth forms, process graph, marker-aligned timeline, and downloads. |
| `android/app/src/main/` | Native Android controller, backend connection, notification actions for marking tasks from the Agent, and Android document picker exports. |
| `backend/experiments.py` | Compare workloads and evaluate a nearest-centroid classifier on held-out agents, with abstention. |
| `backend/protocol.py` | Validate workload ground truth, marker order and trace alignment independently of capture success. |
| `tests/test_project.py` | Request accounting, shared UID attribution, classifier abstention, and API integration with a substitute recorder. |

## Set up the laptop and phone

Use Python 3.10 or newer, Android Platform Tools on PATH, and an Android 11 or newer phone. Enable Developer options and Wireless debugging, and put the phone and laptop on the same trusted Wi-Fi network. The first analysis may download a Trace Processor binary.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
adb pair PHONE_IP:PAIRING_PORT
adb connect PHONE_IP:DEBUG_PORT
adb devices -l
.\.venv\Scripts\python.exe -m backend.server --host 0.0.0.0
```

Use the pairing port displayed on the pairing-code dialog and the debugging port on the Wireless debugging screen. In the APK, enter the laptop's LAN address such as `http://192.168.1.10:8765`, then enter the access token printed by the backend. The API uses cleartext HTTP on the lab network by default. Keep it on a trusted LAN and restrict firewall access to that network. For a laptop-only session, omit `--host 0.0.0.0` and open `http://127.0.0.1:8765`.

Install the included debug build from `artifacts/apk/app-debug.apk`, or build it with JDK 17 and Android SDK platform 35.

```powershell
Push-Location android
.\gradlew.bat :app:assembleDebug
Pop-Location
adb -s PHONE_IP:DEBUG_PORT install -r android/app/build/outputs/apk/debug/app-debug.apk
```

Open the controller on the same phone selected in the ADB menu. Grant notification permission if you want to mark events while the Agent is in the foreground. Wait for Recording and the notification before beginning the task. The controller timestamps native markers on the phone using elapsed realtime. The desktop browser falls back to a device uptime sample and includes the sampling round trip and clock resolution. Confirm the marker order and whether each marker falls inside the trace.

## ChatGPT Android app with Codex

On the connected OPPO phone, the installed ChatGPT app resolves to `com.openai.chatgpt` (observed UID 10363, version 1.2026.300); its running process uses the same name. The UI offers **Select ChatGPT (Codex)** and checks that package on the selected ADB device. Binder attribution, task markers and exports then use the same package-targeted pipeline as Gemini. Package UID and version must be rechecked for each phone or app update.

Pilot W0, W1 and W2 before the formal comparison. Verify that the phone app actually performs each task and record the mode used. If laptop Codex issues ADB commands directly, those requests can originate from Android shell/system processes or the affected app rather than `com.openai.chatgpt`; do not claim that its package-targeted trace represents all Codex actions. Codex running on the laptop has no Android package or UID. Preserve this distinction in the report and revise the protocol if the phone app is only a remote interface.

For each trace run, `path_evidence.json` now exports both transactions behind every nested two-hop candidate, including endpoints, PID/TID, API/code and task-window status. This makes the second hop reviewable. `task_causality` and `intermediary_role` remain `unverified` until a human checks the raw trace and observed outcome. Existing Gemini traces can be backfilled using `python -m backend.rebuild_path_evidence --runs runs`.

Local analysis artifacts include the earlier Gemini-only snapshot and the selected 18-run Gemini–ChatGPT comparison. These reports are held with the dataset pending public-data approval.

The selected 18-run Metrics 1–3 comparison includes CSV identity/edge/API/timeline tables and four SVG figures. Once the local dataset is available, regenerate it with:

```powershell
.\.venv\Scripts\python.exe -m backend.build_metrics_report --runs runs --output reports/2026-11-24-metrics-1-3-gemini-chatgpt --agent com.google.android.googlequicksearchbox --agent com.openai.chatgpt --exclude-run e8fb2ec79c6d4a99b80a041f813801b8
```

The local HTML version contains side-by-side tables and embeds all four figures. After regenerating the Markdown report, refresh the HTML with `./backend/render_metrics_html.ps1` from PowerShell.

For the selected comparison, the user confirmed that Gemini and ChatGPT were not updated during collection and that W2 used comparable voice input modes. Muse is excluded from the formal comparison by the user's decision; its existing W0 captures remain stored as historical data.

The formal 18-run dataset remains local pending explicit approval to publish device metadata and raw traces to this public repository. Large captures and transaction exports are configured for Git LFS. The code-only commit does not contain `runs/`, local access tokens, backend logs, extra pilots, Muse runs, or the incorrect archived run. A privacy-preserving 18-run numeric summary is published in [public_data/formal_metrics_numeric.csv](public_data/formal_metrics_numeric.csv); detailed analysis reports remain local until the data-release scope is confirmed.

## Run the experiment

Choose two Agents that support both text and voice. Use the same phone and the same prompt across Agents. Record three repetitions for each Agent/workload pair, for at least 18 runs. Minimize unrelated foreground activity. A run with warnings, an unsuccessful outcome, or no completed capture remains available for review.

The course document ideally suggests PalmClaw and a closed-source mobile Agent such as Gemini where available. Verify workload support before selection. Enter a stable phone label and a shared experiment-conditions string (fixed prompt, voice mode, versions and network); use the same values across the workload matrix. The evaluation separates different phone/condition groups and needs documented conditions before declaring a complete matrix.

| Workload | Procedure | Ground truth |
| --- | --- | --- |
| W0 · Idle | Open the Agent, allow it to stabilize, then leave it untouched for 30 seconds. | Idle start and end, plus any unexpected activity. Use a short recording margin if adding markers around the full idle window. |
| W1 · Text | Submit “Open https://www.wikipedia.org in my phone's browser.” Confirm if prompted. Stop when the webpage appears or after 60 seconds. | Submission, confirmation, browser launch, browser package, and outcome. |
| W2 · Voice | Activate voice input and speak the W1 prompt. Use comparable input modes and wait up to 60 seconds for a complete response. | Voice start and end, response completion, recognized text if visible, actual response, and outcome. |

Mark observed events from the notification as close to the event as practical. Markers record the user action on the controller, so allow for operator delay. For W0, leave the phone untouched between the idle start and end markers.

The default W1/W2 maximum capture is 90 seconds to include switching-app/setup time. The task itself still ends at completion or after 60 seconds; use Stop promptly. Capture duration and task duration are different quantities. Save the actual outcome after every trial. The page lists missing/invalid ground truth and only offers files that exist, including captured evidence from failed analyses.

Each run stores its trace, metadata, transactions, timeline, and directed edges under `runs/<run-id>/`. The APK exposes JSON and CSV downloads. Compare completed runs with:

```powershell
.\.venv\Scripts\python.exe -m backend.experiments
```

This writes `runs/evaluation.json` with matrix coverage, actual outcomes, per-run communication metrics, feature medians, exclusions, per-run predictions, a confusion table, classification coverage and accuracy on classified examples. You can also refresh and export evaluation from the APK. The evaluation holds out all runs from one Agent at a time within one phone/conditions group. Similar scores produce an uncertain result. Classifier inputs require successful tasks and valid marker/trace evidence. Failed outcomes remain in the comparisons and valid repetition counts; they are not silently presented as successful tasks. Treat performance on the course-sized dataset as exploratory.

## Optional task-time baseline

Pair baseline and trace runs under identical conditions to compare operator-marked completion time. This does not measure CPU, memory or battery overhead. Resource A/B/C experiments were retired after mentor feedback on November 20. See [PERFETTO_GRANULARITY.md](PERFETTO_GRANULARITY.md) for real trace examples and visibility limits.

## Course deliverables

The selected Gemini–ChatGPT 18-run formal matrix is complete. Remaining work includes the combined Metrics 1–3 analysis, manual transaction/path verification, the completed report and presentation. The PPT requests weekly progress emails and a meeting every two weeks; the team handles those communications. The five benchmark sources in the materials are workload-design references, not five additional required implementations.

## Verify and interpret

```powershell
python -m unittest discover -s tests -v
node --check backend/web/app.js
.\.venv\Scripts\python.exe -m backend.analyzer INPUT.pftrace com.example.agent runs/offline --uid 10234
```

For a live run, open the capture in Perfetto UI and compare an exported sender, receiver and timestamp with the Binder slice. Request rows count once, including matched synchronous calls. Incoming and outgoing rates use the whole trace duration. Sync latency uses the matched caller slice duration, with median and nearest-rank p95. Timeline bars use trace-relative one-second bins.

Target attribution uses trace-local UPIDs. It combines package-shaped process names with UID evidence when only the selected package owns that UID. Isolated processes with no identifying name or UID evidence can remain unresolved. A send-only event preserves an observed destination PID where available, and unresolved endpoints do not contribute to the distinct resolved peer count. Interface names depend on trace instrumentation and transaction codes alone cannot resolve them. Candidate two-hop paths rely on a nested request on the serving thread and need manual corroboration before claiming an operation was mediated. Binder traces describe observable on-device IPC metadata.
