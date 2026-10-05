# LLM Arena

本地可复现的双人炸弹人竞技场。Bot 用 C++20 编写，编译为无宿主导入的 WASM，在相同 fuel 与内存限制下同时提交动作。源码提交后冻结，比赛期间不调用模型。

交付范围和进度见 [DELIVERY.md](./DELIVERY.md)，精确规则从 [docs/README.md](./docs/README.md) 阅读。当前工程不提供长期 Rating 或多人正式赛制。

v0.1 命令行竞技场已验收。v0.2 已有观赛前端、60 分钟收卷与资格工作台、真实直播、调度、批次分析与基本发布流程；完整故障恢复、发布交接与最终视觉 / 性能验收仍在推进。范围、实际进度与完成标准见 [DELIVERY_v0.2.md](./DELIVERY_v0.2.md)，产品设计从 [v0.2 规划](./docs/08-v0.2-plan.md) 阅读。

v0.2 以“可观赛、可解释、可交接”为主题，观赛前端为主要产品成果。配套开发包括收卷资格、赛事组织与直播、结果解释、故障恢复、证据分发与数据迁移、安装交接；具体取舍与优先级在规划中统一维护。

向不同模型分发开发任务使用 [MODEL_TASK.md](./MODEL_TASK.md)：包含完整规则、SDK 接口和源码提交要求。统一 60 分钟内交卷，可提前提交；没有待填配置，默认在当前对话提交 `bot.cpp` 源码。

## 环境准备

### v0.2 浏览器界面

支持 Windows x64、Python 3.12、Node 24.19.0 与 npm 11.17.0，运行版本见 `tools/runtime-lock.json`。首次准备执行：

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup-ui.ps1
powershell -ExecutionPolicy Bypass -File .\start-arena.ps1
```

安装脚本使用哈希锁定的 Python 依赖、已校验 SDK 和 `npm ci`，随后构建前端。可用 `-Python`、`-NodeDirectory` 明确指定运行环境；`-CompilerArchive`、`-WheelDirectory` 可复用本地缓存。前端首次安装仍需 npm 网络访问。只修改项目目录和安装进程的 PATH，不修改系统设置。

启动后打开本机浏览器，默认 `http://127.0.0.1:8787`；在启动控制台按 Enter 停止该实例及自有 worker。若停止时正在计算，下一次启动将作业标为中断，由工作台恢复；当前单局从冻结输入重新运行。可用 `-Port 8791` 避开端口冲突，`-NoBrowser` 仅启动服务。同一数据目录只允许一个 worker 实例。

首启异步导入原有 v0.1 工程参考赛。管理入口可收卷、编译并资格检查、选择冻结参赛者、创建单局 / 全配对批次和查看日志。单局可选择运行节奏；观众的播放、变速与回看不影响计算。正式隐藏批次关闭收卷后才开放地图。

管理入口也支持上传旧批次 ZIP（最大 16 MiB，根目录含 manifest、schedule、cases、results 和 replays；build/WASM 可选）。服务逐文件验证后统一注册，保留原始文件；带 WASM 的参赛者须通过哈希与资格检查。上传批次默认封存，主办方确认原参赛池收卷结束后开放观看。完整批次发布时固定公开报告、Replay 与哈希清单；重复发布保留首次记录，可下载清单核对原始证据关联。

公开 Replay `.json` 可上传再导入，服务重新验证世界轨迹；没有 Seed 的副本仅用于观赛，不能重跑 Bot。工作台可创建并下载完整私有备份，包含源码、隐藏 Seed、收卷与发布记录；恢复命令校验后创建新目录，更新凭据，未完成作业等待手动恢复。具体步骤、限制与阶段证据见 [数据恢复说明](./docs/12-data-recovery.md)。

开发服务仍可直接运行 `python -m service --demo`；前端在 `web/` 执行 `npm run dev`。发行使用上述同源静态构建。浏览器检查使用 `npm test`，需要本机 Chrome；`ARENA_BASE_URL` 可指向另一端口的本地验收实例。

### v0.1 命令行环境

首个支持和验收平台是 Windows x64、PowerShell、Python 3.12。需要 Git 才能使用源码版本记录；运行程序本身不需要 Git。依赖锁定 Wasmtime 49.0.0 和 WASI SDK 33.0 / Clang 22.1.0，安装包校验 SHA-256。

在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup.ps1
```

脚本优先检测本地 Codex 自带 Python，再查找 python.exe；也可明确指定已安装的 Python 3.12：

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup.ps1 -Python 'C:\Python312\python.exe'
```

下载需要访问 PyPI 和 GitHub；编译器官方压缩包约 625 MiB，解压还需额外磁盘空间。只写入项目内 .venv 和 .tools，不修改系统 PATH。如果已经缓存同一官方包，可加 `-CompilerArchive 'C:\cache\wasi-sdk-33.0-x86_64-windows.tar.gz'`，仍会校验哈希。

## 编译与参赛资格

```powershell
.\.venv\Scripts\python.exe arena.py build sdk\template.cpp --output artifacts\work\template.wasm
.\.venv\Scripts\python.exe arena.py qualify artifacts\work\template.wasm
.\.venv\Scripts\python.exe arena.py baselines --output artifacts\work\baselines
```

模板只需实现 `bot::init(uint64_t)` 和 `bot::tick(const GameState&)`。支持持久状态和常用 STL 容器；禁异常、RTTI、线程和宿主 I/O。源码上限 1 MiB，WASM 上限 8 MiB，线性内存上限 64 MiB。普通 new 失败直接 trap，nothrow new 返回 null。

编译生成 .wasm、.metadata.json、.compile.json 和 .deps，记录源码、SDK、引用头文件、编译器及 WASM 哈希。资格检查包括 ABI、禁止特性、初始化和公开状态 smoke check。编译或资格失败返回非零退出码，不进入普通比赛排名。

## 单局、回放与复现

```powershell
.\.venv\Scripts\python.exe arena.py match --bot heuristic=artifacts/work/baselines/heuristic.wasm --bot random=artifacts/work/baselines/random.wasm --map-seed 1 --bot-seed 0000000000000001 --bot-seed 0000000000000002 --output artifacts/work/example
.\.venv\Scripts\python.exe arena.py view artifacts/work/example/replay.jsonl --output artifacts/work/example/replay.txt
.\.venv\Scripts\python.exe arena.py verify artifacts/work/example/replay.jsonl
.\.venv\Scripts\python.exe arena.py verify artifacts/work/example/replay.jsonl --wasm artifacts/work/baselines/heuristic.wasm --wasm artifacts/work/baselines/random.wasm
```

`--bot`、`--bot-seed` 和 `--wasm` 的顺序都对应出生槽位 0、1。单局输出 result.json 和 replay.jsonl；无 `--output` 的 view 在终端显示整场。文本符号：`#` 硬墙、`+` 软墙、`.` 道路、`*` 炸弹、数字是玩家槽位。

不带 `--wasm` 的 verify 只重建世界；带 WASM 则重新执行 Bot，校验动作、故障、状态和结果。Bot 重跑要求代码、工具链和配置与 Replay 一致；世界回放不执行 Bot。

## 批量换边与报告

```powershell
.\.venv\Scripts\python.exe arena.py tournament --entrants artifacts/work/baselines/entrants.json --cases configs/acceptance-cases.json --output artifacts/acceptance/v0.1
.\.venv\Scripts\python.exe arena.py report artifacts/acceptance/v0.1
.\.venv\Scripts\python.exe arena.py verify-all artifacts/acceptance/v0.1 --entrants artifacts/work/baselines/entrants.json
.\.venv\Scripts\python.exe arena.py verify-all artifacts/acceptance/v0.1 --entrants artifacts/work/baselines/entrants.json --rerun
```

50 张工程验收地图 × 每对换边 2 局 × 三个 Baseline 的 3 个配对，共 300 局。生成 manifest.json、schedule.json、cases.json、qualification.json、matches、results.jsonl、replays、report.json 和 report.md。每次完整验收使用新输出目录。

中断后用相同命令加 `--resume` 恢复。源码、组件或清单变化会拒绝恢复，需开新批次；缓存结果会再次核对 Replay。基础设施失败不计入分数，修复后加 `--resume --retry-failures`，旧失败结果及 Replay 保存至 failed_attempts。

报告提供胜负平、平均名次分、出生位表现、地图换边组合、辅助统计和固定 Seed 的 2,000 次 bootstrap 区间。缺失局或基础设施失败标为 incomplete，不生成正式汇总成绩；重复 match_id、被修改结果或错误 Replay 返回失败。

configs/public-dev.json 是 10 张公开开发地图；configs/acceptance-cases.json 是 50 张公开工程验收地图。正式模型评测应使用新的隐藏集：

```powershell
.\.venv\Scripts\python.exe arena.py seeds --count 50 --output configs/private/season-cases.json
.\.venv\Scripts\python.exe arena.py map 1 --output artifacts/work/map-1.json
```

Seed 清单以 secrets 随机生成并落盘，比赛依赖文件中的固定种子，不在运行期间抽新种子。private 目录被 Git 忽略。正式提交前冻结任务包和完整开发协议，参见评测文档。

## 检查与版本记录

已完成的工程验收证据见 [交接说明](./artifacts/acceptance/v0.1-release/handoff.md) 和 [逐项审计](./artifacts/acceptance/v0.1-release/audit.md)：39 项检查、300 局有效比赛、全部世界回放与 Bot 重跑，以及独立目录的另一个 300 局批次均通过。完整原始证据归档为 evidence.zip，恢复方式和 SHA-256 见交接说明。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
git log --oneline
```

检查包含规则、地图向量、真实 C++ 编译、STL/构造/堆状态、ABI、fuel trap 恢复、内存上限、watchdog、调度恢复和结果防篡改。运行时和链接决策见 [实现决策](./docs/07-decisions.md)。

编译器和虚拟环境不进入 Git；原始批量 Replay 不以散文件提交，完整证据通过带 SHA-256 的 ZIP 归档保存，清单和摘要单独提交。文本回放已提供；v0.2 图形观赛开发进度见独立交付文档，自动模型提供方集成留待后续。
