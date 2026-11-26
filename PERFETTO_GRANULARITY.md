# Perfetto 实际可见粒度（2026-11-20）

基于 OPPO Find X7 / Android 16 的三个真实 W0/W1/W2 原始 trace，重新用 Trace Processor 查询并用 slice ID 与时间戳核对。目标包为 `com.google.android.googlequicksearchbox`，包含其进程组活动，不能将每条调用都归因于 Gemini 的当前任务。

## 当前配置能看到什么

| 层级 | 实际能力与边界 |
| --- | --- |
| 进程/线程 | 单次请求的 client/server PID、TID、UPID/UTID、进程名；UID 与包名需元数据映射，共享 UID 不等于唯一应用；线程名可能为空。 |
| Binder 事务 | 请求时间、方向、同步/异步、transaction code、可匹配的接收/回复；原始 slice 中还可检查 debug ID、flags。缺失接收端或回复时保留未知。 |
| 接口/方法 | 有可用 AIDL trace 名称时可识别接口及方法；`Binder.#46` 只是数字标签，不能视为已识别 API。 |
| 时间 | 原始时间戳以 ns 存储，单次调用耗时可显示到微秒/毫秒；这不是校准过的 ns 测量准确度。网页每秒一柱仅为聚合。同步 client duration 是墙钟等待区间，非 CPU 执行时间。 |
| 内存计数 | 当前 process_stats 配置约每 1 秒轮询，原始 trace 中有 RSS/虚拟内存等计数；不等于逐对象分配、完整 PSS 或 ABC 资源开销实验。 |
| 调度/函数/堆 | 当前未开启 sched_switch/sched_waking、CPU 栈采样、堆分配采样。三个样本的 sched_slice、perf_sample、stack_profile_callsite、heap_profile_allocation 都为 0；thread_state 非零不代表存在完整调度记录。 |
| 语义与内容 | 当前 trace 不含 Binder 参数内容、URL、prompt、语音音频、服务返回内容、云端模型推理或完整函数调用栈。观察到 startActivity 本身不证明浏览器成功打开指定页面。 |

## 实际调用例子

下表 offset 从各自 trace 起点算起，不代表从用户提交任务起点算起。部分示例在准备窗口，不能直接作为任务因果证据。完整字段、markers 与原始 slice 信息见 `reports/2026-11-20-perfetto/evidence.json`。

| Workload / run | slice | 调用 | 发送 TID → 接收 TID | offset (s) | 同步延迟 (ms) |
| --- | --- | --- | --- | --- | --- |
| W0 / `5bf78800d09843689b07fd22c485f85b` | slice:12297 | `IConnectivityManager.getActiveNetwork` | 24475 → 3384 | 2.548577231 | 0.162847 |
| W1 / `08f1dc71ab324ddeb7a3f36d3c0e4c3e` | slice:66192 | `IActivityTaskManager.startActivity` | 25693 → 3384 | 11.589079077 | 52.421846 |
| W1 / `08f1dc71ab324ddeb7a3f36d3c0e4c3e` | slice:22416 | `IDisplayEventConnection.requestNextVsync` | 24475 → 4126 | 5.124745846 | 不适用：异步单向 |
| W2 / `44b901eb9b4f4b57831c9838693e723b` | slice:13805 | `Binder.#46` | 25654 → 7875 | 3.662231385 | 1.491461 |

- `getActiveNetwork`：证明发生了网络状态查询，不能由此推导访问了哪个域名。
- `startActivity`：该 W1 示例由 Google 搜索进程组调用 system_server，延迟约 52.42 ms；这不是整个开网页任务的耗时。
- `requestNextVsync`：异步请求 SurfaceFlinger 下一次 VSync，无同步返回耗时；不能把空值当 0 ms。
- `Binder.#46`：该 W2 示例从 Google 搜索进程组到 Google Play services，code=46；不能据此命名为语音识别或大模型推理。
- 抽查的 raw slice 中 data_size/offsets_size 查询结果为空；本次不报告请求字节数，更不报告消息内容。

## 方法名覆盖率

以下为整个 trace 的目标进程组请求，不是仅任务 marker 窗口；只代表这三个样本。

| 样本 | 请求数 | 真正具名接口/方法 | 数字占位标签 | 其他无名请求 |
| --- | --- | --- | --- | --- |
| W0 | 1513 | 923 | 215 | 375 |
| W1 | 3795 | 2245 | 311 | 1239 |
| W2 | 8069 | 2846 | 2570 | 2653 |

已修正分析器，将 `#数字` 标签从具名 API 统计中剔除；原始 transaction 字段保留，11 份现有 Binder summary 已同步更正。历史报告其他统计仍属当时快照。

## 后续怎样提高粒度

1. 首先利用现有单次事务，按 markers 缩小窗口、核查方向/线程/延迟、对照屏幕观察。当前同线程嵌套路径仅是候选，不是完整任务因果图。
2. 如果需要区分运行与等待，可另设诊断配置加入 sched_switch、sched_waking，设备支持情况需实测；现有数据无法事后补出这些事件。
3. 如果需要应用内部函数/业务阶段，需目标应用的埋点或权限允许的 profiling，并可能需要符号。不能仅打开 Perfetto 就获得闭源 Gemini 每个函数、prompt 或云端链路。
4. 正式比较应保持配置一致；本次未改变正式 Binder 采集配置，也未恢复 ABC 实验。

## 官方依据与复核 SQL

- [Perfetto android.binder 模块源码](https://github.com/google/perfetto/blob/main/src/trace_processor/perfetto_sql/stdlib/android/binder.sql)：端点、AIDL 名称及 client/server wall duration。
- [CPU scheduling](https://perfetto.dev/docs/data-sources/cpu-scheduling)：开启相应 ftrace 事件后才有线程调度信息。
- [ATrace](https://perfetto.dev/docs/data-sources/atrace)：系统/应用埋点机制，不是自动反编译或记录全部函数。

在 Perfetto UI 打开上述 run 的 capture.pftrace，进入 Query，运行：

```sql
INCLUDE PERFETTO MODULE android.binder;
SELECT binder_txn_id, client_process, client_pid, client_tid,
       server_process, server_pid, server_tid, interface, method_name,
       client_ts, client_dur / 1e6 AS client_wall_ms, is_sync
FROM android_binder_txns
WHERE client_process GLOB 'com.google.android.googlequicksearchbox*'
  AND method_name = 'startActivity'
ORDER BY client_ts;
```

异步事务的 client_dur 不能解释为同步往返时间；核对具体 slice ID 时须使用相同 trace 与兼容 Trace Processor 版本。
