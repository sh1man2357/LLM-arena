# 模型开发竞技场

每个参赛模型获得相同版本的任务书、SDK、公开地图、三个基准 Bot 和运行工具。主办方先准备环境，确认能运行，再记录模型收到任务的时间并开始 60 分钟计时。

## 提供哪些材料

| 材料 | 用途 |
| --- | --- |
| [MODEL_TASK.md](../../MODEL_TASK.md) | 完整规则、目标、资源限制与交卷协议 |
| [SDK](../../sdk/arena.hpp)、[模板](../../sdk/template.cpp) | 编写单文件 `bot.cpp` |
| [公开地图](../../configs/public-dev.json) | 固定 10 个开发案例及 Bot Seed |
| [Random](../../bots/baselines/random.cpp) | 固定种子的随机动作 |
| [Safe](../../bots/baselines/safe.cpp) | 预测爆炸与避险，偏重生存 |
| [Heuristic](../../bots/baselines/heuristic.cpp) | 避险、寻路与安全放弹 |
| [基准辅助实现](../../bots/baselines/planner.hpp) | Safe / Heuristic 的共享预测和寻路逻辑 |
| [练习工具](../../tools/practice.py) | 编译、资格检查、对战、报告与回放 |

开发 ZIP 还包含真实规则引擎、地图生成器、WASM 执行器、CLI、报告与回放校验器，以及已资格检查的三份基准 WASM。`devkit-manifest.json` 记录全部文件哈希和工具链版本，ZIP 旁另有 SHA-256 文件。

包内不包含隐藏案例、其他模型源码、主办方数据、历史比赛结果、访问凭据或完整项目 Git 历史。模型可以研究基准源码和改进其策略；若复用辅助代码，最终将其合并到单个 `bot.cpp`，不要让提交依赖 `planner.hpp`。

## 主办方准备 Windows 环境

将同一个 ZIP 解压到独立的开发目录。Python 3.12 已安装后，在解压目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup.ps1 -Python 'C:\Python312\python.exe'
.\.venv\Scripts\python.exe tools\practice.py --source sdk/template.cpp --maps 1 --output artifacts/work/preflight
```

安装锁定的 Wasmtime 与 WASI SDK，不修改系统 PATH。编译器下载约 625 MiB；有官方缓存时给安装命令加 `-CompilerArchive 'C:\cache\wasi-sdk-33.0-x86_64-windows.tar.gz'`，仍校验哈希。准备工作在模型计时前完成；开发中的编译、测试和等待仍计入 60 分钟。

每个模型使用独立源码 / 输出目录。不同开发实例可以使用相同公开输入，但不得查看其他模型的文件或开发过程。正式隐藏比赛由主办方在全部提交冻结后组织。

## 模型练习命令

所有命令在开发包根目录执行。完整练习：

```powershell
.\.venv\Scripts\python.exe tools\practice.py --source bot.cpp --output artifacts/work/practice-01
```

默认对 Random、Safe、Heuristic 分别运行 10 张公开地图，每张交换出生位，共 60 局；不会额外运行基准之间的比赛。每轮使用新的输出目录，原有结果不覆盖。

快速检查及已有 WASM 的测试方式：

```powershell
.\.venv\Scripts\python.exe tools\practice.py --source bot.cpp --opponent random --maps 1 --output artifacts/work/smoke-01
.\.venv\Scripts\python.exe tools\practice.py --wasm artifacts/work/practice-01/candidate.wasm --opponent heuristic --output artifacts/work/heuristic-01
```

统一编译器、SDK、fuel、内存和资格检查与比赛使用相同实现。包内基准 WASM 在使用前核对冻结哈希；源码模式使用当前模型的 `bot.cpp` 生成候选程序。

## 查看反馈

输出目录的 `summary.md` / `summary.json` 给出各基准的胜负平和平均名次分。每个 `vs-<基准>/report.json` 包含出生位表现、fuel 和故障统计；`replays/` 保存逐 Tick 的真实轨迹。

查看某个 Replay 的文本棋盘或校验轨迹：

```powershell
.\.venv\Scripts\python.exe arena.py view <某局的replay.jsonl>
.\.venv\Scripts\python.exe arena.py verify <某局的replay.jsonl>
```

公开练习成绩只用于开发反馈。正式评测仍使用新的隐藏地图；不要按公开 Seed 或基准实现硬编码答案。

## 更新开发包（项目维护者）

在完整项目根目录执行：

```powershell
.\.venv\Scripts\python.exe tools/build_devkit.py --output artifacts/distribution/llm-arena-devkit.zip
```

工具按白名单打包公开文件，编译并检查基准资格，生成清单与 ZIP 校验和；不打包 `.tools/` 或 `.venv/`。生成文件放在 Git 忽略目录，源码工具、指南与任务书进入版本记录。首次使用前安装环境；所有参赛者拿到同一份已生成的包。
