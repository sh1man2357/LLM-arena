# 五子棋任务包使用说明

在独立可写目录解压本包。运行环境为 Windows x64 和 Python 3.12。首次安装需要下载锁定的 Python 依赖及 WASI SDK。可通过 `-Python` 指定解释器，或通过 `-CompilerArchive`、`-WheelDirectory` 提供缓存。

1. 在包根目录运行环境准备脚本。脚本读取包清单并使用五子棋模板完成双人换色练习。
2. 阅读根目录 `MODEL_TASK.md`，实现单文件 C++20 源码 `bot.cpp`。
3. 使用包内工具编译并练习。每个公开开局交换黑白各运行一盘。每次练习使用新的输出目录。
4. 交付完整 `bot.cpp`，另附中文开发总结，记录实际执行的检查、结果及未验证事项。交付格式以任务书为准。

```powershell
# 环境准备与模板验证
powershell -ExecutionPolicy Bypass -File .\start-devkit.ps1

# 完成 bot.cpp 后执行
.\.venv\Scripts\python.exe tools\practice.py --game gomoku --source bot.cpp --maps 1 --output artifacts/work/practice-01
```

统计保存在练习目录的 `summary.md` 和 `summary.json`，逐局录像保存在 `replays/`。
