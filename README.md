# CS 211 Project B · Mobile Agent Communication Analyzer

An Android controller and Windows-friendly Python backend for observing Binder requests involving a selected Agent on an unrooted phone. The Agent itself is a separate app. The laptop records with ADB and Perfetto, then serves results to the controller over the lab network.

The primary local checkout is `C:\CS211ProjectB`. Clone this repository with `git clone https://github.com/mingsh1/CS211ProjectB.git`, then run setup commands from its root. Local experiment data, access codes, virtual environments and caches are intentionally excluded from Git. A prebuilt debug APK is available at [artifacts/apk/app-debug.apk](artifacts/apk/app-debug.apk); rebuild from source after Android code changes. See [PLAN.md](PLAN.md) for the original-course-requirement mapping and remaining acceptance gates, and [REPORT_TEMPLATE.md](REPORT_TEMPLATE.md) for the final report outline. Code and fixture tests do not replace real-phone acceptance or the required experimental dataset.

For the current CPU, memory, battery/energy and controller-overhead extension, start with [NEXT_WEEK_PLAN.md](NEXT_WEEK_PLAN.md). APK 1.4 adds resource-file exports; start all three resource arms from the laptop browser. Restart the backend after updating source, then install the new APK with `adb -s YOUR_DEVICE install -r artifacts/apk/app-debug.apk`. The original local traces and saved access code remain in `C:\CS211_Project_B`; they are not bundled with this repository. A fresh checkout creates its own local run directory and access code.

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
| `backend/resources.py` | Probe stock-phone CPU/PSS/battery diagnostics, collect fixed-window A/B/C experiments, preserve raw evidence and compare controller/tracing/total resource differences. |
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

## Run the experiment

Choose two Agents that support both text and voice. Use the same phone and the same prompt across Agents. Record three repetitions for each Agent/workload pair, for at least 18 runs. Minimize unrelated foreground activity. A run with warnings, an unsuccessful outcome, or no completed capture remains available for review.

The course document ideally suggests PalmClaw and a closed-source Agent such as Gemini or Meta Muse where available. Verify workload support before selection. Enter a stable phone label and a shared experiment-conditions string (fixed prompt, voice mode, versions and network); use the same values across the workload matrix. The evaluation separates different phone/condition groups and needs documented conditions before declaring a complete matrix.

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

## Measure tracing overhead

### Resource experiment (current required extension)

Use the laptop UI's Resources A/B/C modes. A explicitly stops only our controller; B keeps it connected in the background; C adds Perfetto. All use the same observer. First check measurement support, then run one sustained-idle scenario for 300 seconds per arm, 15-second sampling and a 30-second preparation delay. Start from the laptop, switch to the Agent during the delay and keep it foreground. The resource profile disables task-marker overlays. Reopen/connect the controller before B/C, not during A. Unplug charging and keep brightness/network/temperature comparable.

Use the same phone label, conditions and repetition for each triplet. Counterbalance A/B/C, B/C/A, C/A/B across three repetitions. Record the scenario outcome after every run. Resource scenarios are separate from the formal 30-second idle and single text/voice tasks; repeated-task schedules must be documented explicitly.

The UI displays CPU and PSS medians, missing-value reasons, charge decrease and estimated whole-device energy/power when supported. Exports include `resources.json` (raw evidence and timings), `resources.csv` (raw snapshots), `resources_summary.json` and the arm-C trace. Evaluation adds `resource_overhead` with triplets, B−A/C−B/C−A differences, grouped medians and exclusions. CPU process values are normalized to one core; system CPU includes I/O wait. Energy is a charge-times-voltage estimate and not a per-app or hardware-meter measurement. The observer is present in every arm, so deltas refer to an instrumented baseline.

If battery readings are unsupported, charging, shorter than 120 seconds, increasing, simulated, or too coarse to resolve a decrease, energy remains unavailable. Extend the duration (maximum 540 seconds) for low-resolution counters; unsupported counters require a supported phone or external measurement. Do not claim energy evaluation complete from CPU/memory results alone.

### Task-time experiment (previous supplemental method)

Select `Overhead baseline (no Perfetto)` to run the same task and marker workflow without starting a trace. For W1 and W2, pair each baseline with one `Binder trace` trial using the same stable phone label, conditions, Agent, workload and repetition number. Use native APK notification markers for both. Repeat each pair three times per Agent and alternate trial order. The traced trials can be part of the 18 formal runs; this adds 12 baseline trials for two Agents. Duplicate pairs, missing ground truth, invalid traces and browser-sampled timestamps are excluded with reasons.

Evaluation reports each pair's task duration change in seconds and percent, and medians by Agent/workload. This measures incremental tracing impact while the controller is enabled. It does not measure total APK, CPU, memory or energy overhead. Operator delay, cloud/network variation and ordering effects can dominate the measurement; retain negative differences and discuss those limitations. W0 is not used for completion-time overhead because its duration is fixed by the operator. Traced runs also save trace bytes and host analysis wall time as separate storage and processing costs.

## Course deliverables

The remaining device-dependent work includes the full 18-run formal matrix, the resource-overhead pilot and validated measurements, manual transaction/path verification, and the completed report and presentation. Some W1 captures already exist; evaluate their ground truth before including them formally. The PPT requests weekly progress emails and a meeting every two weeks; the team handles those communications. The five benchmark sources in the materials are workload-design references, not five additional required implementations.

## Verify and interpret

```powershell
python -m unittest discover -s tests -v
node --check backend/web/app.js
.\.venv\Scripts\python.exe -m backend.analyzer INPUT.pftrace com.example.agent runs/offline --uid 10234
```

For a live run, open the capture in Perfetto UI and compare an exported sender, receiver and timestamp with the Binder slice. Request rows count once, including matched synchronous calls. Incoming and outgoing rates use the whole trace duration. Sync latency uses the matched caller slice duration, with median and nearest-rank p95. Timeline bars use trace-relative one-second bins.

Target attribution uses trace-local UPIDs. It combines package-shaped process names with UID evidence when only the selected package owns that UID. Isolated processes with no identifying name or UID evidence can remain unresolved. A send-only event preserves an observed destination PID where available, and unresolved endpoints do not contribute to the distinct resolved peer count. Interface names depend on trace instrumentation and transaction codes alone cannot resolve them. Candidate two-hop paths rely on a nested request on the serving thread and need manual corroboration before claiming an operation was mediated. Binder traces describe observable on-device IPC metadata.
