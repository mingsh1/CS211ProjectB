# Gemini–ChatGPT formal matrix readiness (2026-11-24)

## Selection and quality

The selected formal cohort is `OPPO-FindX7-Android16` / `binder-formal-v1`. It contains three distinct, completed, successful, protocol-valid repetitions of each W0/W1/W2 workload for both Gemini (`com.google.android.googlequicksearchbox`) and ChatGPT (`com.openai.chatgpt`): **18 runs** in total. Every selected run has a raw `.pftrace`, summary, marker alignment, no analyzer warnings, and a two-hop candidate export. W1 has the detected external browser package; W2 has an actual response recorded. W0 idle windows exceed 30 seconds.

| Workload | Gemini (left), run IDs reps 1–3 | ChatGPT (right), run IDs reps 1–3 |
| --- | --- | --- |
| W0 | `8bd870fe`, `db3b4a43`, `5bf78800` | `1584983a`, `65f27b9a`, `684c04da` |
| W1 | `4a40cd19`, `08f1dc71`, `e7366222` | `f28af18d`, `51b898e5`, `bc99d552` |
| W2 | `eb3111d4`, `44b901eb`, `abe56051` | `80abb11e`, `1aca5372`, `c3823f8c` |

The earlier successful ChatGPT W0 repetition 1, `e8fb2ec7`, is retained as an extra pilot by the user's explicit selection, not deleted. The user confirmed that W0 repetitions 2 and 3 stayed in the foreground without touch interaction or unexpected activity; their outcomes and notes were saved through the running backend API. The other ChatGPT W0 repetition 1 was saved by the user. The canonical selection is recorded in [`evaluation-formal-gemini-chatgpt.json`](../runs/evaluation-formal-gemini-chatgpt.json); the file contains full run IDs and the excluded pilot ID.

Three Muse (`com.facebook.aura`) W0 trials are also retained. The user confirmed Muse will not be used in this project comparison; no Muse W1/W2 collection is planned. The unfiltered [`evaluation.json`](../runs/evaluation.json) includes all Agents and is not the canonical result for Gemini–ChatGPT.

## Initial two-Agent comparison

The medians below are per-run metrics from the three selected trials in each cell. Rates use full trace duration rather than only the marked task window; peer counts are trace-specific process counts.

| Workload | Gemini (left): in/s · out/s · peers · async fraction | ChatGPT (right): in/s · out/s · peers · async fraction |
| --- | --- | --- |
| W0 | 13.18 · 51.54 · 12 · 0.34 | 1.20 · 14.75 · 6 · 0.50 |
| W1 | 26.56 · 72.74 · 10 · 0.55 | 28.14 · 94.35 · 6 · 0.83 |
| W2 | 48.10 · 133.09 · 21 · 0.73 | 36.73 · 89.77 · 9 · 0.93 |

The exploratory leave-one-Agent-out classifier classified only **4 of 18** held-out runs (22.2% coverage). Three of those four classifications were correct (75% accuracy conditional on classification); the fourth was W1 classified as W2. It abstained on 14 runs. These figures are descriptive for this small dataset and should not be presented as general Agent recognition accuracy. Keeping the extra W0 pilot in the two-Agent evaluation changes the conditional result to 5/5 classified; that sensitivity is why the selected 18-run manifest matters.

## Path evidence and remaining interpretation

All selected traces now have `path_evidence.json`. In ChatGPT W1 run `bc99d552`, candidate `slice:50773` → `slice:50801` is a ChatGPT → `system_server` → browser Binder sequence on the system serving thread (TID 4360) during the marked task. The original trace independently confirms those slice IDs and timestamps. It is structural evidence only: `activityPaused` and `scheduleTransaction` do not reveal the URL or prove that this pair caused the browser launch. The same causal limit applies to the earlier Gemini path audit.

The installed versions observed on the connected phone on November 24 were Gemini package `17.76.14.ve.arm64` and ChatGPT `1.2026.300`. The run metadata records UID and Android SDK, but not capture-time app version. The user confirmed that neither app was updated during the experiment. The user also confirmed that W2 used comparable voice input modes across the two Agents. These are operator-reported conditions, not facts independently encoded in every trace.

## Next work

1. The selected 18-run Metrics 1–3 comparison is available as [HTML](2026-11-24-metrics-1-3-gemini-chatgpt/metrics.html) and [Markdown](2026-11-24-metrics-1-3-gemini-chatgpt/metrics.md), with detailed CSV tables and four SVG figures. Trace-specific identifiers remain available in CSV/JSON.
2. Manually review representative task-window intermediary candidates from each Agent against `.pftrace` and observed outcomes. Mark structural paths and task causality separately; do not infer Intent/Parcel payloads.
3. Finish the course report, uncertainty analysis, APK/source/dataset packaging, presentation and a reproducible live demo. Document the mentor-directed removal of resource A/B/C experiments and the remaining overhead limitation.
4. Keep Muse's existing W0 captures as historical data outside the formal selection. No further Muse collection is planned.

Reproduce the selected evaluation from the repository root:

```powershell
.\.venv\Scripts\python.exe -m backend.experiments --runs runs --output runs/evaluation-formal-gemini-chatgpt.json --agent com.google.android.googlequicksearchbox --agent com.openai.chatgpt --exclude-run e8fb2ec79c6d4a99b80a041f813801b8
```
