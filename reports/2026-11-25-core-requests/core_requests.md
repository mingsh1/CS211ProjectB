# Gemini 与 ChatGPT：W0–W2 核心 Binder 请求与原始 trace 证据

2026-11-25 · OPPO Find X7 / Android 16 · 正式 `binder-formal-v1` 组，共 18 次（每个 Agent × 任务各 3 次）。仅使用 [`evaluation-formal-gemini-chatgpt.json`](../../runs/evaluation-formal-gemini-chatgpt.json) 指定的运行；ChatGPT 较早的 W0 试跑 `e8fb2ec7` 不计入。逐条可筛选记录见 [`core_requests.csv`](core_requests.csv)。

这里的 **request 是 Android Binder 进程间事务，不是 HTTP 请求**。Perfetto 可给出事务发生的设备运行时间、发送与接收进程／线程、接口／方法（可识别时）、事务 code、同步调用时延和部分嵌套关系；这些 trace 没有保存用户提示词、语音、URL、Intent extras、网络请求正文或 Parcel 内容。`slice:...` 是各自 trace 内的 ID，不能跨运行比较。下文相对时间以相应任务标记为 0 秒；设备 `boottime` 与日历时间不同，标记本身也会有人工操作延迟。

## 最核心的观察

| 任务 | Gemini | ChatGPT | 证据含义 |
| --- | --- | --- | --- |
| W0 · 打开 Agent 后保持空闲 | `requestNextVsync` 在三个 35–40 秒窗口内分别出现 **93 / 172 / 26** 次；`unbindService` 为 **7 / 7 / 2** 次。 | `getActiveNetworkInfo` 和 `getAllPendingJobsInNamespace` 各在每次窗口出现 **2 / 2 / 2** 次。 | 这是空闲基线中的 UI／服务维护活动，不代表用户发出了任务。W0 三次内部也有明显波动。 |
| W1 · 文本要求打开维基百科 | Gemini `:search → system_server` 的 `IActivityTaskManager.startActivity` **每次 1 条**，均落在提交提示词后的 0.26–2.16 秒。 | 三次都出现 ChatGPT → `system_server` 的 `IActivityClientController.activityPaused` **各 1 条**；随后在同一系统服务线程上可见面向浏览器的事务。目标进程导出中 **没有直接 `startActivity`**。 | Gemini 有直接发起 Activity 的 Binder 证据；ChatGPT 有浏览器切换链的结构性证据，但不能从这组目标事务证明它通过哪个 API 触发浏览器。两者实际浏览器结果均由运行元数据记录为成功。 |
| W2 · 语音输入同一提示词 | `:interactor → audioserver` 的 `createRecord`、`IAudioRecord.start`、`stop` 各 **每次 1 条**；`:search → :interactor` 的匿名 `Binder` **code 1001** 在任务窗口为 **639 / 646 / 666** 条。 | ChatGPT → audioserver 的 `createRecord`、`IAudioRecord.start`、`stop` 也各 **每次 1 条**。 | 两个 Agent 均有明确的录音生命周期 Binder 证据。Gemini 内部 code 1001 很密集，但只能称为匿名内部事务，不能由 code 推出识别内容或 API 名称。 |

筛选原则：优先使用三次重复均出现、与任务步骤时间接近、接口语义明确的请求；与 W0 对照，并在可能时核对中介线程的第二跳。`requestNextVsync`、网络状态查询等高频活动只作为环境上下文，不作为“Agent 完成任务”的证明。

## W0：可重复的空闲基线

| 重复 | Gemini `requestNextVsync`：窗口计数、示例 slice | ChatGPT `getActiveNetworkInfo`：窗口计数、示例 slice |
| --- | --- | --- |
| 1 | `8bd870fe` · 93 · `slice:67908`（idle_start +1.643s） | `1584983a` · 2 · `slice:31371`（+0.603s） |
| 2 | `db3b4a43` · 172 · `slice:53701`（+0.026s） | `65f27b9a` · 2 · `slice:28154`（+1.620s） |
| 3 | `5bf78800` · 26 · `slice:61876`（+33.292s） | `684c04da` · 2 · `slice:28213`（+1.856s） |

Gemini 的 vsync 是 `:search → SurfaceFlinger` 异步请求，可反映显示活动；第 3 次首个示例接近窗口末端，说明不能把它解释成整个空闲期间持续刷新。ChatGPT 的网络信息和 JobScheduler 查询是向 `system_server` 的状态查询，**不是实际发出的互联网请求**。原始 trace 抽查了 Gemini W0 第 1 次 `slice:67908` 和 ChatGPT W0 第 1 次 `slice:31371`、`slice:31374`。

## W1：打开浏览器的直接请求与候选路径

**执行模式补充核查：**操作者确认三次 ChatGPT W1 使用手机 App 的 Remote/Codex 电脑会话。由此，手机上的 `com.openai.chatgpt` 是远程界面，不一定是 action 执行者。另查到 11 月 24 日 13:48（太平洋时间）的一条电脑端 Codex 会话明确执行 `adb shell am start -a android.intent.action.VIEW -d https://www.wikipedia.org`，由电脑向手机发起打开网页；这条会话晚于三次正式 W1（13:28、13:36、13:37），不能直接证明正式三次都用同一命令。手机 Perfetto 不能观察电脑端命令，因此 ChatGPT W1 的目标进程 Binder 数量不能解释为完整的端到端 action 路径。

**核心请求判定：Gemini 有强候选；ChatGPT 尚未定位到发起浏览器启动的核心请求。** Gemini 三次的 `IActivityTaskManager.startActivity` 均由 Agent 进程发出，紧接着出现浏览器进程的启动／调度事务，因此可以将其列为该操作最强的 Binder 候选，但 trace 不含 Intent/URL，无法证明目标就是维基百科。对 ChatGPT 的三份完整 `.pftrace`，再次检查了任务窗口及提示词标记前 5 秒：没有 ChatGPT → `system_server` 的 `startActivity`。窗口内可见的 `startActivity` 分别是浏览器自身发出的 `slice:74515`、`slice:67768`、`slice:51194`，发生在浏览器已收到系统调度之后。ChatGPT 的 `activityPaused` 是前台切换的后续事件，**不能称为发起该 action 的核心请求**。标记前的 `queryIntentActivities`／`getIntentSenderWithFeature` 也反复出现于非任务时段，现有数据不足以将其归因于打开维基百科。

| 重复 | Gemini 直接请求 `startActivity` | ChatGPT 活动切换 `activityPaused` | 同线程浏览器第二跳 |
| --- | --- | --- | --- |
| 1 | `4a40cd19` · `slice:52360` · prompt +0.258s · 44.487ms | `f28af18d` · `slice:73203` · +6.908s | `slice:73277` · `system_server → com.heytap.browser`，`scheduleTransaction` |
| 2 | `08f1dc71` · `slice:66192` · +0.741s · 52.422ms | `51b898e5` · `slice:67024` · +6.921s | `slice:67035` · `system_server → com.heytap.browser`，接口／方法未识别 |
| 3 | `e7366222` · `slice:67143` · +2.163s · 23.089ms | `bc99d552` · `slice:50773` · +2.605s | `slice:50801` · `system_server → com.heytap.browser`，`scheduleTransaction` |

所有时间均在 `prompt_submitted → browser_launched` 标记窗口内。Gemini 的 `startActivity` 三次发送方都是 `com.google.android.googlequicksearchbox:search`，接收方都是 `system_server`，code 1。它证明发起了 Activity 请求；**trace 无法确认传入的是哪个 URL 或 Intent 参数**。第 3 次另有 `slice:67707` (`activityPaused`) → `slice:67723` (`system_server → com.heytap.browser.scheduleTransaction`)；系统服务的接收线程与第二跳发送线程同为 TID **2583**。这说明有结构性中介链，但并非 `startActivity` 的那条事务本身直接嵌套到了浏览器。

ChatGPT 三次都在浏览器出现前产生 `activityPaused`，随后同一 `system_server` 服务线程发向 `com.heytap.browser`：第 1 次 TID **3079**，第 2、3 次 TID **4360**。第 3 次 `slice:50773 → slice:50801` 的两条事务相隔约 **2.24ms**，第二跳嵌套在第一跳的服务期间。第 2 次第二跳没有可识别接口名，应保留为未知。三次的目标进程事务中均未见 `IActivityTaskManager.startActivity`；可能存在其他发起路径，但现有证据不足以定论。浏览器包名与完成结果来自实验元数据，不能替代 Binder payload 证据。

## W2：录音启动、内部通信与关闭

`voice_start` 是操作员标记，不是音频设备的精确起点。下表的负数说明录音 API 已在标记前发生；这些事件仍在完整 `.pftrace` 内。若只按 `voice_start → response_complete` 统计，会把五次录音启动误判为缺失。

| Agent／重复 | `createRecord` | `IAudioRecord.start` | `IAudioRecord.stop` |
| --- | --- | --- | --- |
| Gemini 1 · `eb3111d4` | `slice:70275` · −0.966s | `slice:71086` · −0.943s | `slice:134098` · +12.828s |
| Gemini 2 · `44b901eb` | `slice:31017` · −1.519s | `slice:32058` · −1.484s | `slice:96581` · +12.864s |
| Gemini 3 · `abe56051` | `slice:44499` · −1.680s | `slice:45019` · −1.666s | `slice:111192` · +13.305s |
| ChatGPT 1 · `80abb11e` | `slice:31231` · +0.642s | `slice:31531` · +0.657s | `slice:63748` · +10.589s |
| ChatGPT 2 · `1aca5372` | `slice:35639` · −1.373s | `slice:35941` · −1.357s | `slice:84641` · +12.596s |
| ChatGPT 3 · `c3823f8c` | `slice:43290` · −1.586s | `slice:43632` · −1.568s | `slice:89047` · +11.620s |

Gemini 的录音调用来自 `com.google.android.googlequicksearchbox:interactor`；ChatGPT 的调用来自 `com.openai.chatgpt`。`createRecord` 是面向 `/system/bin/audioserver` 的 `IAudioFlingerService` 同步事务，`start/stop` 是 `IAudioRecord` 事务。以 Gemini 第 2 次 `slice:31017` 为例，同步时延 **7.082ms**；ChatGPT 第 1 次 `slice:31231` 为 **13.612ms**。它们是 Binder 调用时延，**不是录音时长或识别延迟**。

Gemini 的匿名 code 1001 发生于 `:search → :interactor`，三次窗口分别为 **639、646、666** 条异步请求，W0 窗口中没有相同的稳定高频模式。该 code 只能与接口标识和端点一起使用；目前不能把它命名为“音频块”“转写文本”或某个具体 API。其示例为第 2 次 `slice:43632`（voice_start +0.004s）。

音频服务的中介第二跳也可见：Gemini 第 2 次 `slice:96799` (`:search → audioserver.getParameters`) → `slice:96802` (`audioserver → MediaTek audio HAL`) 共用 audioserver TID **8693**；ChatGPT 第 1 次 `slice:31231` (`createRecord`) → `slice:31236` (`audioserver → MediaTek audio HAL`) 共用 TID **12574**。后一条 HAL 接口／方法未识别。它们是**结构性两跳候选**，不足以证明 HAL 收到了什么参数或音频内容。

## 原始 trace 核查与局限

用本地 Perfetto Trace Processor 重新打开了以下六份 `.pftrace`，以 `slice.id` 查验共 **19 个**代表性 slice 的时间、持续时间及嵌套顺序；这些 ID 与事务导出一致：

- [Gemini W0 第 1 次](../../runs/8bd870fe8fb34a3a8c4f663f9477832c/capture.pftrace)、[ChatGPT W0 第 1 次](../../runs/1584983ad23446af87d83fa8e32888f3/capture.pftrace)
- [Gemini W1 第 3 次](../../runs/e7366222cf4e45aaaeaa1164cfbaff81/capture.pftrace)、[ChatGPT W1 第 3 次](../../runs/bc99d55227f74dd286e90baeebb603b2/capture.pftrace)
- [Gemini W2 第 2 次](../../runs/44b901eb9b4f4b57831c9838693e723b/capture.pftrace)、[ChatGPT W2 第 1 次](../../runs/80abb11ec0d5483eaae1b58087fa3d99/capture.pftrace)

Trace Processor 的原始 `slice.name` 通常只是 `binder transaction`；接口／方法名是通过 trace 的其他 Binder 元数据由分析器关联后得到，见每次运行的 `transactions.json`。CSV 保留 18 次代表事务的完整 run ID、原始 trace 路径、设备时间戳、PID/TID、方向、code、时延及是否在任务窗口；路径行保留两跳的各自 ID。完整频次和所有请求仍以各运行的 `transactions.json`、`path_evidence.json` 及 [Metrics 1–3 总报告](../2026-11-24-metrics-1-3-gemini-chatgpt/metrics.md) 为准。

**结论边界：** W1 的浏览器路径和 W2 的 audioserver/HAL 路径已确认存在相邻且同线程嵌套的 Binder 请求，仍属候选路径；不能从时间相邻自动推出用户任务因果链。若要证实具体 URL、语音文字、Intent 或 Parcel 参数，需要新的、经授权的内容级采集；这些字段无法从现有 Perfetto trace 事后恢复。
