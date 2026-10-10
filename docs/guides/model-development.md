# 模型 Bot 开发包

开发材料统一维护在 devkit。对外 ZIP 的根目录含 README、START_HERE、MODEL_TASK 和 start-devkit.ps1，模型可直接执行。应用只负责导入生成的 .cpp 与运行，不管理开发倒计时或收卷。

## 生成

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe tools\build_devkit.py
```

输出到 artifacts/distribution/llm-arena-devkit.zip，旁边有 SHA-256。已有包不覆盖；需要新包时用 --output 指定新文件。打包按白名单，不包含本机数据、旧归档、.venv 或 .tools。

| 材料 | 用途 |
| --- | --- |
| [执行入口](../../devkit/START_HERE.md) | 准备独立工作区、安装和运行检查 |
| [任务书](../../devkit/MODEL_TASK.md) | 规则、完整 SDK、单文件 Bot 要求 |
| [SDK](../../sdk/arena.hpp) / [模板](../../sdk/template.cpp) | C++20 接口 |
| [公开地图](../../configs/public-dev.json) | 十张可复现练习地图 |
| [练习工具](../../tools/practice.py) | 逐局基准对战、简要统计与轨迹 |

包还包含当前引擎、沙箱、单局 CLI、Replay 校验器和三个已检查的基准 WASM。清单版本为 2，记录文件哈希、工具链、2～8 人各自为战及地图生成器版本 2。每个基准同时通过双人资格检查和八人世界校验。SDK / 二进制协议仍为版本 1。

## 模型执行

模型在独立可写目录解压，在包根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-devkit.ps1
```

脚本检测 Python 3.12、准备锁定依赖 / 编译器，并用模板完成三人公开练习；可用 `-Players 2` 或 `-Players 8` 指定环境检查人数。安装需要网络；可使用 -CompilerArchive、-WheelDirectory 复用已校验缓存。不修改系统 PATH。

模型阅读任务书，生成根目录 bot.cpp；没有本地工具时按内嵌 SDK 写出完整源码，不声称已运行检查。开发时间由使用者自行安排，应用和默认任务书不提供限时评测协议。

## 练习

```powershell
.\.venv\Scripts\python.exe tools\practice.py --source bot.cpp --output artifacts/work/practice-01
.\.venv\Scripts\python.exe tools\practice.py --source bot.cpp --opponent random --maps 1 --output artifacts/work/practice-02
.\.venv\Scripts\python.exe tools\practice.py --source bot.cpp --players 3 --maps 1 --output artifacts/work/practice-3p
.\.venv\Scripts\python.exe tools\practice.py --source bot.cpp --players 8 --opponent heuristic --maps 1 --output artifacts/work/practice-8p
```

`--players N` 支持 2～8，默认 2。每局一个候选 Bot 与所选基准的 N−1 个独立实例各自为战，每张地图依次轮换全部 N 个出生位，种子随实例移动。十个公开地图 Seed 各提供八个独立 Bot Seed，双人的前两个种子保持原值；地图地形随人数生成。默认三个基准、每个十张公开地图、每图双人换边，共 60 局；三人一张地图对三个基准共 9 局，八人一张地图对一个基准共 8 局。

练习直接调用单局执行器，不创建批次。summary.md / summary.json 提供人数、各对手的胜 / 平 / 负和平均名次分，replays/ 保存每局记录。独占第一记胜，并列第一记平，其余记负；多人平均分直接累计名次分，不用 `(胜 + 0.5 × 平) / 局数` 推算。

每轮使用新输出目录，基准 WASM 核对包清单哈希。练习遵守与应用相同的规则和资源限制，但独立于应用榜单。复用基准辅助代码时合并进单个 bot.cpp，不让最终文件依赖 planner.hpp。

模型完成后将 bot.cpp 交给使用者，在应用首页导入即可。
