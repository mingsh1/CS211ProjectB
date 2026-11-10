# Project B experimental report

This is a report outline, not a completed experimental result. Replace pending sections with measured evidence and retain limitations.

## Research question and setup

Which Agent activities can be distinguished using directly observed Binder communication metadata? Record phone model/Android build, Agent names and versions, open/closed-source status, backend versions, wireless ADB setup, prompt, voice mode and network conditions. Explain any departure from the recommended PalmClaw/commercial pairing.

## Workloads and dataset

Describe W0/W1/W2 exactly, repetitions, task duration limits, capture margins, baseline order, conditions string and stable device label. Link run IDs to metadata and traces. Include the complete matrix, actual success/failure/timeout counts, invalid captures and reruns. Separate task failure from capture failure. Do not substitute the system_server reference fixture for Agent data.

## Direct observations

Compare peer counts/identities, weighted directed edges, incoming/outgoing request counts/rates, one-second timelines, top peers, matched sync-call count and median/p95 latency. Show representative graphs and marker-aligned timelines with run IDs. Explain which interfaces/methods were identifiable and how many requests were unidentified.

## Intermediary evidence

For each investigated path record run ID, ordered process/UPID sequence, hop count, trace transaction IDs/timestamps, observed interface/method if any, intermediary role, candidate or verified status, and the corroborating evidence. Time proximity alone does not verify causality. If no path can be verified, report that result and the limitations explicitly.

## Exploratory behavior inference

Use evaluation.json for held-out Agent predictions, confusion, abstention/coverage and conditional accuracy. Explain features, training-only standardization and uncertainty threshold. Discuss excluded runs and the success-only classifier population. Compare predictions with actual tasks and explain ambiguous cases; do not claim generalization from the small dataset alone.

## Overhead

For resource overhead, report the A/B/C controller profile, fixed scenario, interval and duration, device capability evidence and counterbalanced trial order. Link each triplet to resource raw data and metadata. Report CPU normalization and accepted windows, app/controller PSS and system memory, battery charge decrease and estimated whole-device energy/power. Include B−A (controller), C−B (tracing) and C−A (total tested profile), valid counts and median signed deltas. Explain unavailable metrics, observer costs, screen/network/thermal effects and charge-counter resolution. Do not claim direct hardware energy measurement or universal controller overhead. State whether each metric actually passed phone acceptance.

For the separate supplemental task-time comparison:

List paired baseline/traced run IDs and order. Report native-marker task times, per-pair changes and medians for each Agent/workload; include negative changes and missing pairs. Report trace sizes and host analysis times separately. State that the controller is active in both modes, and that this protocol does not measure CPU/memory/battery or total controller overhead. Discuss operator delay and network variability.

## Limitations and reproducibility

Discuss missing/unresolved processes, shared UIDs and isolated workers, trace loss, available API instrumentation, candidate path limitations, sockets/shared memory/cloud activity outside Binder observation, timing uncertainty and sampling bias. Include install/run/export commands and steps for reproducing one result.

## Final deliverables

APK, source and dependency instructions, raw experimental dataset, JSON/CSV exports, evaluation.json, completed report, presentation and live-demo procedure. All results and figures must be traceable to real run IDs.
