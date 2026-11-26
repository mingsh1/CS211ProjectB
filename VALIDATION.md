# Validation — 2026-11-20

- Python: 30 tests passed, including rejection of retired modes and numeric Binder-name regression.
- Frontend: JavaScript syntax check and Simpleperf UI wiring passed.
- Android: offline assembleDebug passed; APK version 1.6 / code 7 copied to artifacts/apk/app-debug.apk. Existing deprecated API/Gradle warnings remain.
- Three existing real W0/W1/W2 traces reopened with Trace Processor; examples verified by slice ID and timestamp. See PERFETTO_GRANULARITY.md and reports/2026-11-20-perfetto/evidence.json.
- Nine active Binder runs and two archived Binder runs preserved. Twenty-five active resource runs removed. Eleven derived Binder summaries corrected to exclude numeric method placeholders; raw traces, metadata and transaction exports preserved.
- ABC collectors, UI, API, exports, tests and dedicated plan removed. Independent Simpleperf and optional task-time baseline remain.
- Per user instruction, mixed historical reports and deployment backups are retained. Separable resource sections/JSON fields/images and dedicated backup resource code/data removed; frozen mixed code/APK backups and narrative references may still describe the retired feature. These are not current executable sources. Git history is unchanged.
- New APK has not been installed on the phone. Existing traces establish observed fields, not new-APK real-device acceptance or a completed two-Agent matrix.
- Existing backend restarted only after confirming no active run; authenticated run list contains nine Binder runs and retired resource-capabilities endpoint returns HTTP 404.
