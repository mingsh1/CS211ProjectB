# Project B requirements and acceptance plan

Updated 2026-11-20 after the mentor meeting. Main checkout: `C:/CS211ProjectB`. Resource A/B/C experiments are retired at the user's request. This change does not establish acceptance of the original course overhead requirement. See PERFETTO_GRANULARITY.md.

## Sources and scope

- `C:\Users\xumin\Downloads\Project B_ Mobile Agent Communication Architecture Analyzer.pptx`: slides 2–7 define implementation, workloads and metrics; slides 8–13 define the course roadmap; slide 14 defines mentor communication.
- `C:\Users\xumin\Downloads\CS 211 Course Projects, Fall 2026.docx`: Project B and Shared Workload Guidance for Projects A-B. Requirements of the other projects do not apply to this project.

The APK controls a laptop service over Wi-Fi. The laptop uses wireless ADB and Perfetto on a stock phone. Do not root the phone, modify the target Agent, or inspect message contents. Binder observations do not cover socket traffic, shared-memory contents or cloud requests. Unknown identities, interfaces and latency remain unavailable rather than guessed.

The course document additionally requires profiling-overhead measurement. At least two Agents and three repetitions for each W0/W1/W2 workload are required by the PPT. PalmClaw plus a closed-source Agent is an ideal selection, not a mandatory pair. Confirm both support the text and comparable voice workloads. The five listed benchmarks are task-design references, not five required benchmark implementations.

## Requirement mapping

| Requirement | Implementation | Remaining acceptance evidence |
| --- | --- | --- |
| APK connection, selection, start/stop, markers and summaries (slide 2) | MainActivity, MarkerReceiver, backend/web, server | Install updated APK; run from APK, switch to Agent, return; rotate/recreate Activity and confirm recovery |
| Wireless ADB and Perfetto, target package/UID/processes including new processes (slide 2) | collector, trace.pbtx, analyzer target UPID attribution | Real stock phone trace; verify target main and newly created subprocesses; document unresolved isolated processes |
| Sender/receiver process/thread, direction, timing, transaction type (slides 2, 5) | analyzer, transaction JSON/CSV with trace slice IDs and run ID | Manually cross-check requests, replies, async calls and process lifetimes in Perfetto |
| Peer count and identities, directed weighted edges, incoming/outgoing requests (slide 5) | analyzer summaries and graph; unresolved endpoints retained | Cross-check a real run and request/reply accounting |
| Rates, one-second timeline, markers, top five peers, median/p95 latency and matched count (slide 6) | analyzer and web results | Check marker clock alignment and representative latency matches |
| Interface/method counts, codes when unavailable (slide 7) | analyzer and exports; unidentified count explicit | Establish which interfaces this phone exposes; document unavailable fields |
| Intermediaries and paths/hops; candidates versus verified evidence (slide 7) | Nested same-thread two-hop candidates and original trace retained | Manually investigate representative paths; record transaction IDs, role evidence and candidate/verified status in final report. No automatically verified paths are claimed |
| Graphs and metadata/transactions/summaries in JSON/CSV (slide 2) | Web graph/timeline and native document picker; failure exports | Save each export on phone, including raw trace after analysis failure |
| Transparent exploratory inference and uncertainty (slide 2) | Leave-one-Agent-out centroid classifier, per-phone/conditions grouping and abstention | Real held-out results; report confusion, coverage, accuracy on classified examples, exclusions and ambiguity |
| W0/W1/W2, same phone/prompt/voice mode, two Agents, three repetitions (slides 3, 12) | Run metadata, ground truth validation, matrix coverage, per-run comparisons | At least 18 recorded trials; retain failures and reruns, check valid repetitions in each cell |
| Profiling overhead (course document) | Optional paired task-time baseline only; resource experiment retired after mentor feedback | Explain revised scope and limitations in the final report; do not claim CPU/memory/battery overhead acceptance |
| Dataset, report, code, documentation, presentation (slides 12–13) | README, this plan, analysis and structured exports, REPORT_TEMPLATE.md | Actual dataset, evidence-based report, final presentation and live demo remain pending |
| Weekly progress email, meeting every two weeks (slide 14) | Team responsibility | User/team sends updates and schedules meetings. No emails or messages are sent automatically |

## Revised sequence

The original four-stage plan is retained as an implementation sequence, not a substitute for the PPT's course-week schedule.

1. **Feasibility (course week 3):** prepare the phone, select Agents, capture one real trace and record the fields available without root. Stop and resolve collection limitations before calling the implementation accepted.
2. **Collection and frontend (weeks 4–5):** validate the APK-to-backend flow, trace and baseline modes, markers, state restoration, device disconnection errors and exports. Use the APK on the same phone selected by ADB.
3. **Analysis (weeks 5–6):** manually inspect representative transactions and confirm all structure/timing metrics. Keep observations separate from inference. Synthetic tests and the reference trace support regression checks, not Agent evaluation.
4. **Integration/pilot (week 7):** verify graph/timeline and markers, investigate representative mediated paths, pilot all three workloads on both Agents, and finalize conditions.
5. **Data (week 8):** record the 18 formal Binder trials across two Agents and W0/W1/W2. Retain raw traces, outcomes and quality failures. Preserve incomplete traces and rerun when needed.
6. **Analysis and delivery (week 9):** review outcome counts separately from communication features; explain success-only classifier selection. Analyze uncertainty, compare peers/interfaces/candidate paths, report overhead limitations, complete report/presentation and demonstrate the full flow.

## Workload acceptance

- W0: stabilize the foreground Agent, then mark `idle_start`, leave it untouched for 30 seconds, mark `idle_end`; record unexpected activity. The default 40-second capture includes setup margins.
- W1: submit `Open https://www.wikipedia.org in my phone's browser.` Mark `prompt_submitted`, every required `confirmation`, and `browser_launched` if reached. Record browser package and success/failure/timeout. Stop at appearance or 60 seconds after submission.
- W2: speak the W1 sentence using comparable input modes. Mark `voice_start`, `voice_end`, `response_complete` if reached. Record visible recognized text, actual response and outcome. Stop at completion or 60 seconds after starting the task.
- W1/W2 default to a 90-second maximum capture to allow switching apps before the 60-second task window. Stop manually after the task. Do not treat capture length as task duration.
- Quality checks reject missing required markers, incorrect ordering, out-of-trace markers, short idle windows, missing success ground truth, and trace warnings from classifier evaluation. Failed tasks do not require completion markers; outcomes remain in comparisons.
- Use one stable phone label and an identical conditions string across the workload matrix. Document the fixed prompt, voice mode, app versions, network, warm-up and background-activity controls. Different conditions are deliberately evaluated separately.

## Overhead scope and limitations

The mentor-directed scope removes the resource experiment. The following task-time procedure remains optional:

Pair `baseline` and `trace` runs with identical phone label, conditions, Agent, workload and repetition. Baseline starts no Perfetto session. Both modes keep the same controller and notification-marker workflow. Only native phone markers are accepted for paired overhead timing; browser ADB uptime samples are retained for general experiments but excluded here.

The measured quantity is the change in operator-marked task completion time when tracing is enabled. Negative changes remain visible. W0 is excluded because its duration is prescribed by the operator. Trace bytes measure storage cost; analysis wall time measures post-capture host processing cost. Neither is a CPU or energy measurement.

Task-time comparisons alone do not isolate total controller overhead, CPU, memory or battery overhead. Operator latency, network and cloud response variation can dominate small differences. Alternate baseline/trace order and report individual pairs plus medians rather than claiming causality from one pair.

## Current status

As of November 24, the selected Gemini–ChatGPT formal cohort has three valid repetitions of each W0/W1/W2 workload for both Agents: 18 runs on the same phone and conditions group. The user confirmed that neither app was updated during collection and that W2 used comparable voice input modes. The earlier extra ChatGPT W0 repetition 1 is retained as a pilot. Three Muse W0 runs are retained as historical data; the user decided not to use Muse in the comparison. See `reports/2026-11-24-formal-matrix.md` and `runs/evaluation-formal-gemini-chatgpt.json`. Resource A/B/C experiments remain retired at the user's request. Current priorities:

1. The selected 18-run Metrics 1–3 comparison, per-run CSV tables and four SVG figures are complete in `reports/2026-11-24-metrics-1-3-gemini-chatgpt/`.
2. Verify representative task-window intermediary candidates against raw traces and observed outcomes. A nested two-hop sequence is structural evidence, not proof of task causality or message content.
3. Explain the low held-out classifier coverage and the duplicate-run sensitivity. Do not claim generalization from this small exploratory dataset.
4. Complete the evidence-based final report, dataset/source/APK packaging, presentation and live demonstration. Document the mentor-directed removal of resource experiments and the remaining overhead limitation.
5. Retain Muse W0 captures for provenance, but exclude Muse from formal figures, inference and delivery claims.

The current trace configuration remains focused on Binder/AIDL and process metadata. CPU scheduling, stack sampling and heap allocation profiling are not enabled. Independent Simpleperf diagnostics remain optional.
