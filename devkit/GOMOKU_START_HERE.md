# 五子棋 Bot 开发入口

本包用于模型编写自由五子棋 C++20 Bot。运行时执行 WASM，不调用模型 API。

你的 Bot 将代表你，与其他顶级前沿模型独立开发的 Bot 同台竞技。请交付你能实现的最强参赛程序；算法、策略与开发过程由你自主决定。Baseline 是一个普通的参考 Bot，供本地练习和计分使用，基准成绩仅供参考。

在独立可写目录解压，运行包根目录入口：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-devkit.ps1
```

入口从清单自动识别五子棋，准备 Python 3.12、Wasmtime 49.0.0、WASI SDK 33.0，并用五子棋模板进行双人换色练习。安装支持 `-Python`、`-CompilerArchive` 和 `-WheelDirectory`；只写工作区，不修改系统 PATH。

环境就绪后阅读根目录 `MODEL_TASK.md`，编写单文件 `bot.cpp`。只收到任务书文字时，使用其中完整 SDK 编写源码，不声称完成了编译或测试。

```powershell
.\.venv\Scripts\python.exe arena.py build bot.cpp --game gomoku --output artifacts/work/bot.wasm
.\.venv\Scripts\python.exe arena.py qualify artifacts/work/bot.wasm --game gomoku
.\.venv\Scripts\python.exe tools\practice.py --game gomoku --source bot.cpp --maps 1 --output artifacts/work/practice-01
```

默认完整练习使用一个 Baseline 参考 Bot 及 12 种公开开局，每种开局交换黑白，共 24 盘；基准实力分固定为 0。可用 `--opponent baseline`、`--maps 1` 缩小范围，`--opening-mode empty` 使用空棋盘。每次使用新输出目录。

输出 `summary.md`、`summary.json` 和每盘录像。将完成的 `bot.cpp` 交给使用者，在竞技场选择“五子棋”并导入。参考 Bot 的入口为 `bots/gomoku/baseline.cpp`，辅助实现为同目录下的 `champion.hpp` 和 `patterns.hpp`；复用时必须把所需实现合并到单个源码中。

源码仓库中运行入口可显式使用 `-Game gomoku`；对外 ZIP 从清单自动识别。包不含本机 Bot、比赛数据、录像、旧验收归档或依赖安装目录。
