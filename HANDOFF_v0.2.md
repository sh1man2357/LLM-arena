# LLM Arena v0.2 交接

更新：2026-10-06。**v0.2 全部 29 / 29 项验收完成并封存；负责人已确认 A06 视觉验收通过。** 逐项状态以 [交付清单](./DELIVERY_v0.2.md) 为准。

## 启动与完整使用路径

Windows x64 使用 Python 3.12、Node 24.19.0 / npm 11.17.0；具体补丁版本、哈希锁和工具链见 `tools/runtime-lock.json`、`requirements.lock`、`web/package-lock.json`。依赖安装及独立目录验证见 [README](./README.md) 与 [安装证据](./artifacts/acceptance/v0.2-development/checks/clean-room-ui.json)。

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup-ui.ps1
powershell -ExecutionPolicy Bypass -File .\start-arena.ps1
```

默认仅在本机提供页面。先在大厅看已导入的真实工程回放；首次空实例进入主办方工作台导入参考赛。正式操作：记录收到任务 → 60 分钟内粘贴 / 上传单份源码并冻结 → 编译与资格 → 选择资格通过的程序 → 单局直播或全配对换边 → 查看报告 → 正式收卷关闭并确认披露 → 校验发布与导出。模型收到的协议直接分发 [MODEL_TASK.md](./MODEL_TASK.md)，不另加 token / 轮数表。

播放 / 暂停、逐帧、变速、事件、格子与玩家检查、换边、全屏和精确帧链接只改变观众位置。停止调度在当前局结束后生效；恢复 / 重试保留旧尝试。资格失败 / 未交卷 / 逾期有私有档案，正式源码不可覆盖；未完成批次没有正式排名。

完整私有备份仅交给主办方，含源码、隐藏 Seed 和诊断。通过工作台下载后，按 [恢复说明](./docs/12-data-recovery.md) 在新目录恢复，校验 SHA-256；不覆盖已有数据。公开观众只分发允许发布的报告 / Replay，seed-free Replay 不能重跑 Bot，也不能证明缺失的原始来源。

## 验收证据与复用范围

[统一验收索引](./artifacts/acceptance/v0.2-development/final/acceptance-index.json) 列出全部 29 项要求、状态、证据、当前源码 / 构建哈希、命令与退出状态。最终媒体与 API 样例封存在 `artifacts/acceptance/v0.2-development/final/evidence.zip`，ZIP 和逐文件 SHA-256 在索引中；解压到一个新目录后可查看画面和实际录像。

最新为 81 项 Python、4 项帧协议、34 项完整 Chrome、瞬时编译状态补验、24 组可访问性及 14 组原生观赛；真实 500 Tick 首帧 / 定位 / 播放复测通过。当前 SDK 的 300 局、旧固定输入兼容、690 个轨迹报告核对、实际进程退出 / 断连恢复、16 MiB 边界和独立安装复用各自冻结证据，不声称此次全部重新运行。比赛核心 27 个源文件与 Baseline 清单逐个哈希核对；界面实际构建另封存。

具体边界与状态覆盖见 [工程验收](./docs/19-final-engineering-acceptance.md)，人工审美的可审查结果见 [视觉走查](./docs/20-final-visual-review.md)。

## 复现本轮检查

使用新的隔离数据目录。先准备常规实例，再准备独立规则画面实例；不要把生成器指向已有目录。以下服务分别在不同终端运行，检查顺序执行，不让已有计算作业占用 FIFO 窗口。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools\prepare_performance_checks.py --data artifacts/work/final-repro --proof artifacts/acceptance/v0.2-development/final/checks/performance-fixture.json
.\.venv\Scripts\python.exe tools\prepare_viewer_cases.py --data artifacts/work/final-viewer-repro --proof artifacts/acceptance/v0.2-development/final/checks/viewer-cases.json
.\.venv\Scripts\python.exe -m service --port 8861 --data artifacts/work/final-repro
# 其他终端分别启动：
.\.venv\Scripts\python.exe -m service --port 8862 --data artifacts/work/final-empty-repro
.\.venv\Scripts\python.exe -m service --port 8863 --data artifacts/work/final-viewer-repro
```

在 `web` 目录构建后执行，原始链式 Replay 样例从既有 v0.1 ZIP 的 `examples/chain/replay.jsonl` 解出为 `artifacts/acceptance/v0.2-development/checks/final-chain.jsonl`。性能机器记录用 `tools/capture_performance_machine.ps1` 更新到 `final/checks/performance-machine.json`。

```powershell
npm.cmd run build
npm.cmd run test:protocol
node tools/verify-viewer-quality.mjs http://127.0.0.1:8863 ../artifacts/acceptance/v0.2-development/final
node tools/measure-performance.mjs http://127.0.0.1:8861 ../artifacts/acceptance/v0.2-development/final final
node tools/audit-accessibility.mjs http://127.0.0.1:8861 ../artifacts/acceptance/v0.2-development/final
node tools/capture-final-review.mjs http://127.0.0.1:8863 ../artifacts/acceptance/v0.2-development/final
$env:ARENA_BASE_URL = 'http://127.0.0.1:8861'
$env:ARENA_EMPTY_URL = 'http://127.0.0.1:8862'
$env:ARENA_BROWSER_RESULTS = '../artifacts/work/final-browser-repro.json'
$env:ARENA_FINAL_EVIDENCE = '../artifacts/acceptance/v0.2-development/final'
npm.cmd test
```

报告路径每次独立命名。完整文件顺序会建立上传工程程序；单独运行排队用例之前必须已有该资格通过的程序。冻结原始输入核对工具默认读取本次工程目录 `v0.2-final-01`；新目录复现时要同步工具中的目录与 API 样例位置。

## 已知限制

本版只交付 Windows x64 本地应用，不是云端账号平台。工程 Baseline 和规则样例不代表外部真实模型参赛成绩，展示赛须实际取得模型提交后记录。外部收卷时间与收卷关闭为主办方确认，不能伪装成远端自动取证。公开地图一旦展示即视为已披露，后续须使用新的隐藏集。

审美是设计追求，不由测试数量证明。Codex 完成工程视觉检查和修正后，负责人在本对话直接回复“通过视觉验收”；原回复、范围和记录时间见 [人工确认](./docs/20-final-visual-review.md)。工程证明和人工意见分别留存，整版为 29 / 29 项通过。
