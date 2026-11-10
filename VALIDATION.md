# Validation record

## Resource extension checked 2026-11-07

- Current-source regression suite: 32 tests passed (19 existing tests and 13 new resource tests). New tests cover CPU normalization and process matching, PSS deduplication, missing readings, battery units and invalid states, stale/overlapping CPU windows, arm contamination, controller-only force-stop, tracing only in arm C, early stop, triplet/version/duplicate rules, signed deltas, resource/legacy isolation, API validation and authenticated resource exports.
- Android APK 1.4 (`versionCode 5`) built successfully with Gradle 8.14, installed SDK and JDK. Deprecation warnings remain.
- JavaScript syntax check passed. Headless Chrome desktop and 390-pixel mobile layouts with mocked API/native bridge passed resource setup, acknowledgment, capability flags, unavailable-value rendering, APK resource-start restriction, resource export and evaluation checks. This is not Android lifecycle/device validation.
- Read-only evaluation of the existing primary dataset still lists 10 ordinary run comparisons and zero resource triplets. Existing raw traces and ground-truth files were not modified by this update.
- No phone was connected during this change. CPU/PSS availability, actual battery counter resolution, force-stop/reopen workflow, resource collector cost, controller background survival, raw trace completeness and usable three-arm differences remain **pending real-device acceptance**. No measured CPU/memory/energy overhead is claimed yet.

## Earlier implementation record

Checked on 2026-11-05 after the original course requirements review.

- `python -m unittest discover -s tests -v`: 9 tests passed. Tests cover request/reply accounting, shared UID attribution, API authentication and experiment lifecycle, baseline without Perfetto, evidence download after analysis failure, marker validation, overhead pairing and ambiguous duplicate rejection, failure retention, and classifier abstention/separated synthetic workloads.
- `node --check backend/web/app.js`: passed.
- Android Gradle 8.14 offline `:app:assembleDebug`: successful with the installed SDK. The updated APK is `android/app/build/outputs/apk/debug/app-debug.apk`. Deprecation warnings remain; no compilation failure.
- Real reference trace reanalysis using installed Perfetto dependencies: 544 selected requests, 528 matched synchronous calls, timeline sum 544. The reference trace reports `ftrace_setup_errors: 4`; it is a regression fixture, not an accepted Agent experiment.
- Headless Chrome, 390 × 844 viewport, mocked backend/native bridge: frontend initialization from saved native state, failed trace download button, baseline selection, 90-second W2 capture margin, and evaluation rendering passed with no JavaScript page errors.

Not validated on a physical phone: wireless tracing permissions, APK Activity recreation, notification marker delivery, document-picker exports, timing accuracy, newly created Agent process attribution, actual workload support, and overhead. Browser mocks do not validate Android lifecycle or Binder collection. No formal Agent results or classification accuracy are claimed.
