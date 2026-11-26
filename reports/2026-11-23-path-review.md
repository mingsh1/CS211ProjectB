# Binder two-hop path review (2026-11-23)

## Scope and method

The nine retained Gemini runs were reprocessed from their `capture.pftrace` files. Each run now has `path_evidence.json` with both full Binder requests behind every `summary.json` candidate path. A candidate requires the second request to start on the first request's serving thread while that server slice is active. The export includes transaction IDs, timestamps, process and thread identifiers, interface/method or numeric code, and whether both requests fall inside the recorded task window.

This establishes an observed two-request structure. It does not by itself establish which user instruction caused it, the payload, the intermediary's semantic role, or the destination of a user-visible action. All exported rows therefore retain `status: candidate`, `task_causality: unverified`, and `intermediary_role: unverified`.

## Export totals

| Workload | Runs | Complete two-hop candidates | Both hops in task window |
| --- | ---: | ---: | ---: |
| W0 idle | 3 | 624 | 67 |
| W1 browser | 3 | 371 | 91 |
| W2 voice | 3 | 1,286 | 504 |
| **Total** | **9** | **2,281** | **662** |

The complete counts mean both transaction records were recovered; they are not counts of verified agent-to-app paths. One parent request can produce several child requests, so these counts must not be interpreted as distinct tasks or independent causes.

## Raw-trace checks

In W1 run `e7366222cf4e45aaaeaa1164cfbaff81`, the exported pair `slice:67707` → `slice:67723` is inside `prompt_submitted` → `browser_launched`. The first request is Gemini's `IActivityClientController.activityPaused` to `system_server`; the second is `system_server`'s `IApplicationThread.scheduleTransaction` to `com.heytap.browser`. The first server thread and second sender thread are both TID 2583. An independent query of `capture.pftrace` found slice 67707 at 7,137,629,874,959 ns (client TID 24475) and slice 67723 at 7,137,632,419,959 ns (sender TID 2583). The second request began during the first request's serving interval. This supports the process path and timing, but `activityPaused` does not prove that this pair launched the browser or conveyed the prompt/URL.

In W1 run `08f1dc71ab324ddeb7a3f36d3c0e4c3e`, `slice:66192` → `slice:66487` is a task-window candidate: Gemini `IActivityTaskManager.startActivity` → `system_server` → SurfaceFlinger `ISurfaceComposerClient.createSurface`, at trace offsets 11.589079077 s and 11.634204923 s on serving/sender TID 3384. The recorded run outcome is success and its browser package is `com.heytap.browser`. The trace supports the system-service and surface-creation chain; it does not show the Intent extras, URL, or the browser as the second endpoint in this particular pair.

In W2 run `44b901eb9b4f4b57831c9838693e723b`, `slice:96799` → `slice:96802` is an in-window candidate: Gemini `IAudioFlingerService.getParameters` → `audioserver` → the MediaTek audio HAL service. The second request starts on the first serving thread, TID 8693. An independent raw-trace query confirmed the slice IDs, sender threads and timestamps 6,523,049,874,615 ns and 6,523,050,355,307 ns. This supports an audio-service interaction during the voice task, but not the spoken content or whether it produced the final answer.

## Conclusion and next collection step

Metrics 1 and 2 and the interface/count parts of Metric 3 remain supported by the retained Binder trace data. The new export makes candidate two-hop process paths auditable. The W1 examples support observed system-mediated paths, including a Gemini → `system_server` → browser request pair, but there is no trace-level proof of a complete instruction-specific Gemini → other-app operation with payload or URL. Keep the distinction between structural verification and task causality in the final report.

For a stronger task-specific claim, run a controlled prompt with a unique destination or event marker, record the visible app outcome and exact window, and collect a permitted source of Intent/Parcel contents or app-side instrumentation if payload is required. A Perfetto trace cannot reconstruct missing payload after capture. A comparison with Muse requires the app to be installed, package/version verified over ADB, and pilot W1/W2 capability checks before formal repetitions.
