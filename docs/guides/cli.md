# 命令行使用

所有命令在项目根目录执行。先按[安装与启动](./getting-started.md)准备环境；图形工作台操作见[组织比赛与观赛](./organizing-matches.md)。

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
