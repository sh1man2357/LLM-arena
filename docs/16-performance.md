# v0.2 观赛性能与后台作业验收

本轮测量使用发行构建、实际本机服务及真实浏览器，不使用模拟帧或伪造比赛。完整交付仍以 [交付清单](../DELIVERY_v0.2.md) 为准；本页覆盖 C04 / E03，不替代完整可访问性、异常状态或最终人工审美。

## 机器、样例与测量范围

机器配置见 [配置记录](../artifacts/acceptance/v0.2-development/checks/performance-machine.json)：Windows 11，构建 26200；Intel Core Ultra 9 386H，16 核 / 16 逻辑处理器；物理内存 33,776,709,632 字节；显卡与驱动、120Hz 显示信息均记录。Chrome 154.0.8037.93 以 headless 模式运行，视口高 1000px、DPR 1；没有 CPU / 网络限速。Python 3.12.14、Node 24.19.0，服务使用生产前端资源。显卡清单不代表已证明独显参与渲染。

从原验收中 94 份已验证的 500 Tick 对局选取成功移动最多的一局：501 帧、561 次成功移动、原始文件 506,463 字节、磁盘投影 1,721,563 字节。另制作精确 16 MiB 的文件边界样例：仅在原 JSONL 行尾增加 JSON 空白，逐条解析后与原记录完全一致，再通过实际上传 API 重算世界验证。原文件、动作、世界哈希与结果均未修改；边界样例作为独立历史回放导入，不加入原批次成绩。来源、哈希、构造和大小见 [样例记录](../artifacts/acceptance/v0.2-development/checks/performance-fixture.json)。

两个样例各测 390 / 768 / 1280 / 1440px，每个尺寸三次独立浏览器上下文，共 24 次首帧和 288 次原生键盘定位；每个尺寸另测正常 1 倍播放。每次上下文均无 HTTP 缓存或已加载 Replay；服务与操作系统的文件缓存可以已热。后台检查另使用实际冻结的 C++ 源码、编译器 / 资格检查和 500 Tick 单局。

## 测量方法

| 指标 | 起点和终点 | 说明 |
| --- | --- | --- |
| 首帧 | 页面导航的时间原点 → 首次真实 Canvas 绘制后的两次浏览器动画帧回调 | 为呈现留出一轮绘制机会，作为保守的显示时间界限；不声称测得显示器扫描输出 |
| 已加载定位 | 原生 range 键盘输入 → 目标帧实际绘制后的两次动画帧回调 | 核对画面 Tick、控件位置和请求帧一致；不能把旧帧重绘当作完成 |
| 正常播放 FPS | 整段 1 倍播放墙钟时间内，实际绘制棋盘的不同浏览器动画帧数 | 包含插值结束后的空闲时段；剔除同步 effect / resize 重绘、同帧重复调用和无关 RAF |
| 活跃插值 | 按同一 Tick 的真实绘制时间分别计算 | 辅助解释动画平滑度，不替代整段正常播放 FPS |
| 后台可操作 | 查询作业 running → 原生定位及 API 读取 → 再查同一作业 running | 只有前后都在运行的样本计入后台窗口；播放也须在完整 running 窗口内推进 |

本版渲染器在插值结束后保留静止图像、不持续空绘。报告中的 FPS 是真实 Canvas 动画绘制率，不是另开一个空 RAF 循环，也不推断 GPU 合成器或显示器的最终呈现帧率。正常播放默认每秒四次 Tick；动画帧率和模拟 Tick 速率分别计算，均不进入世界哈希。

## 最终结果

| 样例 | 首帧中位 / 最慢 | 定位中位 / 最慢 | 四尺寸正常播放 FPS |
| --- | --- | --- | --- |
| 原始真实 500 Tick | 255.6 / 400.1ms | 7.6 / 15.7ms | 80.8～81.1 |
| 精确 16 MiB、记录等价 | 231.3 / 248.7ms | 8.2 / 15.2ms | 80.7～81.1 |

全部首帧低于 1.5s，全部已加载定位低于 100ms，全部正常播放高于 55 FPS；最终记录逐项保存采样和阈值断言，见 [普通回放](../artifacts/acceptance/v0.2-development/checks/performance-final.json) 与 [大小边界](../artifacts/acceptance/v0.2-development/checks/performance-boundary.json)。16 MiB 上传、重算验证与注册另测约 292.6ms；首帧指标从导入完成后导航计算，不将上传时间隐去或合并成同一指标。浏览器请求的是服务生成的约 1.7 MiB 公共投影，原始 16 MiB 文件不会原样传进播放器。

后台编译使用真实 C++ 标准库头文件和 WAIT Bot，未增加睡眠包装或假作业。单局使用该冻结 Bot 与 Safe，按支持的 50ms 运行节奏真实执行 500 Tick。定位、播放和 HTTP 读取与运行独立；同幂等键重复编译 / 开赛返回同一作业，最终资格与世界验证通过。每个采样窗口、操作时间、终态、源码 / WASM / Replay 哈希见 [后台证明](../artifacts/acceptance/v0.2-development/checks/performance-background-final.json)。后台播放不以正常播放 FPS 的验收数字替代实际操作证据。

| 正在运行的作业 | 前后均 running 的定位样本 | 最慢定位 | 最慢 API 读取 |
| --- | --- | --- | --- |
| 编译 / 资格 | 6 | 11.6ms | 73.3ms |
| 单局计算 | 12 | 15.2ms | 80.7ms |

API 读取计时覆盖顺序读取 `/health` 和整份 501 帧响应并解析；不是只测空健康接口。两种作业中的本地正常播放都在前后为 running 的窗口内推进；最终编译和单局均成功。

## 修正与未通过记录

1. 插值原先依赖每次渲染新建的坐标数组及身份数组引用，URL / 后台元数据刷新会重新启动当前 Tick 的移动。实际 Canvas 坐标记录出现同 Tick 向起点倒退；修正后依赖稳定的坐标 / 身份值，起始时间按确认帧保留，暂停后不重新演出已经完成的移动。普通、边界及真实后台两类作业都未再记录倒退，旧观察见 [修正前](../artifacts/acceptance/v0.2-development/checks/performance-background-before-motion-retry.json)。
2. 旧数据实例的新 SSE 连接从事件 0 开始，历史通知反复刷新并取消初始页面读取；完整观赛回归的批次列表未能在五秒内加载。新连接现在从当前事件水位订阅，并在 onopen 读取当前快照；显式 `after=0` 仍可读取历史，`Last-Event-ID` 重连仍有序补齐。没有延长原五秒条件，最终完整观赛及实际断连 / 重启恢复通过。语义见 [恢复契约](./13-live-and-job-recovery.md)。
3. 首次后台计时脚本把旧帧重绘误记为目标帧完成；修正采样条件，旧不完整记录保留。另一次观赛回归已完成操作断言，但新输出目录未建 `checks` 导致结果写出失败；补建目录后完整重验，原失败日志保留。工具错误不计作功能通过或性能样本。
4. 常规流程重复运行时，再次上传同一已发布归档仍保留原发布状态；旧检查错误地期待重新封存。测试改用只增加 ZIP 注释的独立容器，内部证据与原 ZIP 不变，继续完整验证封存 / 发布；并补验同一容器重复上传保留作业与发布 ID。失败结果单独保留，没有将已公开数据重新标成隐藏。

本轮保留修正前测量、最终 API 变更前测量和工具失败记录；最终通过文件由证据索引明确指定。机器、样例与场景是本轮实测范围，不保证其他硬件、电源状态或任意新内容具有相同速度。边界样例验证文件大小处理与相同比赛的播放；它没有额外增加游戏实体或事件复杂度。

## 回归、归档与复现

75 项完整 Python 检查覆盖新连接 / 显式游标 / 重连 / 字段过滤及既有规则、运行和服务，见 [日志](../artifacts/acceptance/v0.2-development/checks/python-performance-final.log)。实际进程和浏览器再次完成断连补帧、去重、活动变速、主进程 / worker 退出、八局恢复且无重复计分，见 [新证明](../artifacts/acceptance/v0.2-development/checks/live-performance-recovery.json)。十四组观赛检查、42 张四尺寸画面与操作录像见 [独立回归](../artifacts/acceptance/v0.2-development/performance-regression-final/checks/viewer-quality.json)。常规流程的完整运行七条通过，归档流程修正测试前提及重发键 / 标题后单独完整重验通过；八个不同流程均有实际通过结果，见 [汇总](../artifacts/acceptance/v0.2-development/checks/browser-performance-summary.json)、[完整运行](../artifacts/acceptance/v0.2-development/checks/browser-performance-regression.json) 与 [归档重验](../artifacts/acceptance/v0.2-development/checks/browser-performance-archive-retry.json)。未把原完整运行的失败改写成全绿。本轮图像证据不替代最终人工审美。

完整采样、命令、退出状态、源码 / 检查 / 媒体哈希与 ZIP 见 [性能证据索引](../artifacts/acceptance/v0.2-development/checks/performance-stage.json)。归档包含测量、回归和图像，不含工作数据库、隐藏输入或私有备份；原 v0.1 / 当前 SDK 参考证据仍保持原哈希。

归档为 `visual/performance-evidence.zip`，83 份文件、15,727,707 字节；SHA-256 为 `b0b5149e143bf7842031d814aafe1963ccefe755b67a0eb930b70bc69d9e6f9f`。索引逐项列出哈希；工具失败与通过记录分开保留。

复现使用新数据和新证据目录，避免覆写本轮记录。先按根目录 README 安装 / 构建，再在根目录执行：

```powershell
.\.venv\Scripts\python.exe tools/prepare_performance_checks.py --data artifacts/work/v0.2-performance-local --proof artifacts/acceptance/v0.2-performance-local/checks/performance-fixture.json
.\.venv\Scripts\python.exe tools/prepare_performance_checks.py --data artifacts/work/v0.2-performance-local --proof artifacts/acceptance/v0.2-performance-local/checks/performance-fixture.json --add-size-boundary
& ./tools/capture_performance_machine.ps1 -Output artifacts/acceptance/v0.2-performance-local/checks/performance-machine.json
.\.venv\Scripts\python.exe -m service --port 8811 --data artifacts/work/v0.2-performance-local
```

保持服务运行，在另一个 PowerShell 的 `web` 目录执行；Node 须已按 README 安装并可调用：

```powershell
node tools/measure-performance.mjs http://127.0.0.1:8811 ../artifacts/acceptance/v0.2-performance-local final
node tools/measure-performance.mjs http://127.0.0.1:8811 ../artifacts/acceptance/v0.2-performance-local boundary
node tools/measure-background-work.mjs http://127.0.0.1:8811 ../artifacts/acceptance/v0.2-performance-local final
```

测量期间不并行启动其他验收计算或录像。完成后停止该实例。完整观赛 / 进程恢复回归另需原观赛案例数据与全新恢复目录，实际命令见证据索引；这些验证与性能采样分开执行。
