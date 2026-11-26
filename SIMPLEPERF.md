# Simpleperf 无 root 附加采集（2026-11-15）

主目录：`C:\CS211ProjectB`。用户提供的实验设备为 OPPO Find X7、Android 16，目标 Agent 为 Gemini。该信息是实验准备记录，尚未通过连接手机核验。本次实现不使用 root、不重新打包或修改 Gemini、不调整系统 profiling 属性。

## 本次交付与边界

APK 1.5、后端和页面支持在 Binder trace 模式中勾选 **Also collect Simpleperf CPU samples (diagnostic run)**。默认关闭。采样与该次实验一起启动、停止和保存；失败原因也保存在同一个 run 目录。

Android 允许 shell profiling 的应用才可能成功；Android 16 本身不能保证 Gemini 可采样。预检检查普通 ADB shell、主用户、预装 Simpleperf、app runner 的 debuggable/profileable 判定、所需选项、timeout 和运行进程。实际 perf-event 权限还要录制才能确认。预检不通过或录制被拒会标为 unavailable，Binder 实验继续。不会通过修改目标 APK 来绕过限制。

本适配器目前只支持 Android 主用户（user 0）。Gemini 的界面入口与实际执行进程可能不同；先使用现有应用选择器核对包名、UID 和版本。不要把 Gemini 和 Google app 两个包直接当成两个不同 Agent，也不要把未采到入口包 CPU 解释为 Gemini 没有开销。无法确定实际执行包时，保存包信息和一次 Binder 结果供后续核对。

## 按阶段操作

1. **更新并连接。** 等已有实验结束，关闭旧后端，在主目录重新启动；安装新版 APK。沿用已有 ADB 连接方式和访问码。使用 PATH 中已配置好的 adb，在 PowerShell 中运行：

   ```powershell
   Set-Location C:\CS211ProjectB
   adb devices -l
   # 把下面的 YOUR_DEVICE 替换为上面 device 状态行的完整设备序列号或 IP:端口。
   adb -s YOUR_DEVICE install -r artifacts/apk/app-debug.apk
   .\.venv\Scripts\python.exe -m backend.server --host 0.0.0.0
   ```

2. **先做预检。** 打开 Gemini 一次，保持进程存在。连接控制器，选手机和已核对的目标包，点击 **Check Simpleperf support**。`Ready to attempt` 仅表示可以尝试；`Unavailable` 显示具体原因。预检按钮只显示结果，正式勾选后的 run 会将预检持久化。

3. **做一轮短诊断。** 选择 Binder trace、W0、40 秒，填稳定设备标签 `OPPO Find X7 / Android 16` 和实验条件，勾选 Simpleperf。等状态进入 Recording 后按原 W0 流程切到 Agent、打点并保持 30 秒静置，结束后保存实际 outcome。准备阶段可能因设备命令多花几十秒；不要在 Preparing 时开始计时。

4. **检查采样结果。** 从 Available files 下载 `simpleperf.json`；如果成功采到，还会有 `simpleperf.data` 和 `simpleperf_report.txt`。查看状态、样本数、日志、PID/线程及符号，而不只看整个 run 是否 complete。run complete 表示主实验完成，不能替代 Simpleperf 成功判定。

5. **继续 W1/W2。** 只有短诊断确认支持后，再按相同输入与条件做所需 W1/W2 诊断。无需为每个正式 trial 强行增加一次诊断；先各做一轮确认数据有用。正式 18 次矩阵及任务时间比较均保持关闭该选项。后端会自动把所有请求了 Simpleperf 的运行（包括权限失败的尝试）放进 `evaluation.json` 的 `simpleperf_runs`，排除出原正式统计。

若 Gemini 不允许 profiling，保留一次 unavailable 证据，继续 Binder 采集；重复同一受限配置不会凭空得到 CPU 热点。向导师说明设备/目标包限制后再决定是否换可 profile 的目标。本次不接入未提供确切版本链接的 DroidPerf 或 binderdump。

## 文件和读数

每次数据保存在 `C:\CS211ProjectB\runs\<run-id>\`，网页与 APK 均可导出已存在的文件：

| 文件 | 含义 |
| --- | --- |
| simpleperf.json | 设备和权限预检、状态、命令配置、开始/停止时间、样本数、问题和限制 |
| simpleperf.data | 原始 perf 数据；只有确实拉取到文件才存在 |
| simpleperf_report.txt | 手机端 Simpleperf 生成的进程、PID、线程、共享库、符号热点报告 |
| simpleperf_log.txt | 录制的标准错误日志；预检就失败时不会启动录制，也不会有此文件 |

默认采样事件为 `cpu-clock:u`，100 Hz，DWARF 调用栈，boottime 时钟；采样记录达到 64 MiB 时会提前结束（最终文件含附加元数据，未承诺严格 64 MiB）。设置有限录制时间和外层 timeout，停止时只向经过命令行核验的本次 recorder PID 发 SIGINT，不使用全局 pkill。成功拉取并生成报告后仅清理本次手机临时数据文件。

状态 complete 表示取得可解析且非零的样本报告；empty 是零样本；partial 表示提前退出或非零退出码，需要检查覆盖范围；recorded 表示原始文件已保存但报告或样本数未确认；unavailable/failed 附带原因。任何状态都不代表覆盖所有目标进程或全部工作负载。

Simpleperf 会在主测量开始前就绪，主测量结束时请求停止，包含启动/切换的边缘时间；与任务标记界定的窗口并不精确相等。对齐分析要使用各自时间证据，不直接把整个热点报告当成 W1/W2 单个任务区间。新建的 zygote 子进程、其他包承接的任务、内核工作和云端计算可能不在采样内。缺失符号保持未知。

报告里的 Overhead 百分比是所采样事件的相对热点占比，**不是整机 CPU 使用率或工具开销百分比**。Simpleperf 不直接测内存、电池能耗或 Binder 事务；Binder 事务来自 Perfetto；当前实现不提供 CPU/内存/电池三组对照实验。

## 验证记录与资料

本地 Python 测试覆盖权限限制、采样/导出流程、PID 所有权核验、零样本、报告失败、正式统计隔离及 Binder 降级运行；另有页面开关/预检请求测试。新版 APK 已构建。设备实测仍待连接 OPPO 完成，不能据此声称 Gemini 已成功采样。

- [AOSP Android 应用 profiling 文档](https://android.googlesource.com/platform/system/extras/+/master/simpleperf/doc/android_application_profiling.md)
- [Simpleperf record 实现与选项](https://android.googlesource.com/platform/system/extras/+/master/simpleperf/cmd_record.cpp)

```powershell
python -m unittest discover -s tests -q
node --check backend/web/app.js
node tests/frontend_simpleperf.cjs
```
