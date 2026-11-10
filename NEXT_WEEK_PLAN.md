# Next week plan and resource overhead procedure

Updated 2026-11-07. Primary project: `C:\CS211ProjectB`. This plan implements the user's decision to include CPU, memory, battery/energy and controller overhead. The course document requires overhead evaluation but does not prescribe these exact metrics or repetition counts.

## Where we are

The Android app, companion backend, Binder analyzer, exports, marker handling and task-duration baseline are implemented. The current primary checkout also includes app-name/package search, browser package detection and floating marker controls added after the initial review; this update preserves them.

At the November 7 review, the original private runs directory contained 10 completed W1 capture records (excluded from this repository), three with outcome `success`. There are nonzero Binder results, including 3,578 requests for one Google app target and 137 for two bard target records. These are capture records, not proof that all traces satisfy the formal protocol or that two distinct Agents have been evaluated. Different package names may belong to the same Agent experience. W0/W2, a second distinct Agent, the complete experiment matrix and resource measurements still need acceptance. No ADB device was connected during this code update.

## Required next-week milestones

| Sequence | Must finish | Acceptance evidence | Owner |
| --- | --- | --- | --- |
| 1 | Confirm resource visibility on the stock phone | Save one capability result; CPU and PSS samples readable; battery counter supported or a documented device limitation | User connects phone; assistant checks data |
| 2 | Implement three-arm collection and UI | Desktop starts A/B/C, explicit controller-stop acknowledgment for A, preparation delay, fixed window, cancellation, resource JSON/CSV and APK exports | Code delivered in this update; real-phone check pending |
| 3 | Validate readings and boundaries | Check raw CPU time windows, PSS units, process presence, unplugged battery state, nulls and command failures; do not replace unavailable values with zero | Automated tests plus manual phone sample review |
| 4 | Complete one pilot scenario with 3 repetitions per arm | One Agent, sustained idle scenario, A/B/C × 3 = 9 runs, counterbalanced order, identical conditions, 300 seconds per run initially | User operates phone; backend collects |
| 5 | Obtain CPU/memory and resolvable discharge comparisons | Three complete triplets; report controller B−A, tracing C−B and full-profile C−A; keep signed differences and missing metrics | Backend report plus review |
| 6 | Document results and limitations | Per-run evidence, per-triplet deltas, median deltas, battery uncertainty, observer cost and next experimental scope in weekly report | Team |

Battery measurement is not accepted merely because the code exists. If the device cannot expose a usable charge counter, record that blocker and arrange a supported phone or a hardware power measurement method; do not present zeros or claim the requirement has been measured. If changes are below counter resolution, extend the fixed window up to 540 seconds and repeat. Longer externally measured trials require a separate agreed protocol.

## Three experimental arms

| Mode | Phone state | Perfetto | Meaning |
| --- | --- | --- | --- |
| Resources A (`resource_agent`) | Agent running; Project B controller force-stopped | Off | Agent baseline under the common ADB observer |
| Resources B (`resource_controller`) | Agent foreground; connected Project B controller in background, no marker overlay | Off | Controller-enabled profile |
| Resources C (`resource_trace`) | Same controller profile as B | On | Full tested profiling profile |

All arms are started from the **laptop browser**. The APK must not start A because it would stop itself. The A form explicitly asks permission to stop `edu.cs211.projectb`; no target Agent is force-stopped. Open and connect the controller again before B/C, then switch to the Agent during the preparation delay. Do not reopen the controller during A. Process presence is checked at each resource snapshot, and contamination invalidates comparison.

The controller profile here is deliberately fixed to background UI without floating/notification task markers. It does not characterize every possible controller feature state. A future overlay-on profile must be separately labeled and measured. These resource runs use a fixed-duration scenario and are excluded from the original 18-run Binder matrix and the native-marker task-time classifier.

## First phone session

1. Finish any running ordinary experiment. Restart the backend with the updated code and install APK 1.4. The saved access code and existing runs remain unchanged.
2. Connect wireless ADB. Disconnect USB charging and any wireless charger. Keep screen brightness, volume, network, temperature and background apps comparable. Set the screen timeout long enough to cover preparation plus the full window before starting; keep the display on without touching it during idle. CPU windows reporting device sleep are rejected.
3. Open the backend in the laptop browser and select the device and Agent package. Open the Agent on the phone.
4. Choose a Resources mode and click **Check resource measurement support** while no experiment is active. It uses read-only ADB commands; capability availability does not guarantee freshness or usable battery resolution.
5. For the first pilot use W0 as **sustained foreground idle**. Set phone label, conditions (for example `resource-idle-v1 screen50 wifi stable-warm`), repetition 1, window 300 seconds, interval 15 seconds and preparation delay 30 seconds.
6. Arm A: check the controller-stop acknowledgment and start from the laptop. The controller stops; leave the Agent foreground throughout the delay and window. Do not use phone markers or touch the phone during idle.
7. Wait for completion and record `success` only if the intended scenario was maintained. Record unexpected activity or interruptions honestly. Download/check resource summary and raw samples.
8. Arm B: open the updated APK, connect, then start B from the laptop. Return to Agent during the delay. Keep the phone idle until complete. Use the same labels, repetition, interval and window.
9. Arm C: repeat B with Perfetto enabled. A raw trace is saved, but resource runs are not passed to the ordinary Binder-workload classifier.
10. Repeat with order A/B/C, then B/C/A, then C/A/B for repetitions 1, 2, 3. Allow comparable stabilization/cooldown between trials. Battery starting level and temperature remain in raw evidence for review.
11. Click **Refresh comparisons and overhead**, or run `.\.venv\Scripts\python.exe -m backend.experiments` in the primary directory. Inspect `resource_overhead` in `runs/evaluation.json`.

Do not rerun a failed triplet using the same repetition number while retaining duplicate valid arms: the pairing logic intentionally rejects ambiguous duplicates. Use a new repetition number for the replacement triplet and preserve the earlier records.

For later W1/W2 resource scenarios, write an exact repeated-task schedule in Conditions and apply the same schedule to all three arms for the entire window. A 300-second resource scenario is not a 300-second single W1/W2 task and does not change the course's single-task time limit. Preserve per-task successes/failures in Notes.

## Measurements and interpretation

| Quantity | Source and output | Acceptance/limitation |
| --- | --- | --- |
| System CPU | `dumpsys cpuinfo` TOTAL percentage, median of accepted snapshots | Android TOTAL includes I/O wait; not integrated CPU time |
| Agent/controller CPU | Sum package-shaped process names in cpuinfo, percentage relative to one core | Can exceed 100%; unknown/omitted worker names are not assigned by guess; missing readings remain null |
| Agent/controller memory | `dumpsys meminfo -s PACKAGE`, summed process PSS in KiB, median and peak | Avoids counting detail and summary twice; sampled, not continuous peak |
| System memory | `/proc/meminfo`: MemTotal minus MemAvailable in KiB | Whole-system estimate, not sum of app PSS |
| Battery charge | `dumpsys battery` charge-counter decrease in µAh | Require unplugged, discharging, real positive counters; no counter reset; at least 120-second observed battery window |
| Energy estimate | Sum successive charge decreases × mean endpoint voltage | Whole-device estimate in mWh; not direct hardware measurement or per-app battery attribution |
| Mean power estimate | Energy divided by actual battery observation time | mW; helps compare small window-length differences; raw window durations remain visible |
| Observer cost | Host wall time spent on each ADB snapshot | Recorded but not subtracted from device cost; an interval shorter than probe time invalidates comparison |

CPU snapshots whose windows predate the experiment, overlap an already accepted window or are stale are rejected. At least two valid samples are required for a metric median. CPU and memory can remain usable when battery energy is unavailable. No measurable charge change means **unresolved**, not zero energy.

All arms use the same six ADB diagnostics in each snapshot. The observer itself consumes resources, so A is an instrumented baseline. A/B/C deltas estimate the effects of enabling the tested controller and tracing under that observer. Interactions, operating-system variation, cloud/network latency, screen state, temperature and caching still matter. Do not claim observer-free causal overhead or use one triplet as conclusive evidence.

## Exports and comparison

Each resource run saves `metadata.json`, `resources.json` (parsed values, raw command text/errors and sampling times), `resources.csv`, and `resources_summary.json`. C also saves `capture.pftrace`. CPU CSV values are raw snapshots; use the summary's freshness-filtered medians for comparisons.

Triplets match device label, conditions, Agent, workload, repetition, duration, interval, settling delay, device build, app versions and trace configuration. Actual outcomes must be successful; interrupted/contaminated runs and duplicate/missing arms remain listed with reasons. Each metric reports signed delta and relative change where the baseline is nonzero. Group summaries report valid-triplet count and median delta. Three triplets do not imply all metrics are available: check each metric's count, especially energy.

Keep the original 18 formal Binder trials and their final report/presentation as separate remaining project deliverables. The nine-run resource pilot is next week's minimum new experimental milestone, not completion of the entire project.

## Technical references

- [Android dumpsys diagnostics and memory](https://developer.android.com/tools/dumpsys)
- [AOSP ProcessCpuTracker CPU windows and normalization](https://android.googlesource.com/platform/frameworks/base/+/master/core/java/com/android/internal/os/ProcessCpuTracker.java)
- [Android BatteryManager charge and energy units](https://developer.android.com/reference/android/os/BatteryManager)
