# Public numeric summary

formal_metrics_numeric.csv contains one row for each of the 18 selected Gemini/ChatGPT W0-W2 repetitions (three per cell). It includes only workload labels and numeric Binder metrics. Device IDs, IP addresses, UIDs, process/package inventories, trace slices, and raw Perfetto captures are not included.

Rates divide request counts by the full trace duration, including setup and completion margins. Synchronous latency uses calls with matched replies only. Counts are observed Binder requests, not distinct user actions or Internet requests.

The operator confirmed that ChatGPT W1 used the phone app's Remote/Codex computer session. Consequently, those rows describe the Android remote UI process, not the complete execution path of the browser-opening action. They should not be interpreted as equivalent direct mobile-agent action traces to Gemini W1.

The full 18-run raw dataset is published under runs/ through Git LFS following explicit approval to release device metadata and traces to this public repository.