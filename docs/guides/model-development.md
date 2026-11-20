# 模型任务包

同一游戏的参赛模型应收到相同的 ZIP 和提示词。模型在独立工作目录使用包内规则引擎、SDK、基准 Bot 和练习工具，交付一个完整的 C++20 源文件 `bot.cpp`。

## 主办方分发与导入

1. 在「Bot 库」选择游戏，点击「下载炸弹人任务包」或「下载五子棋任务包」。
2. 点击「复制提示词」，将提示词和 ZIP 一并发送给具备文件与命令执行能力的编程代理。浏览器限制剪贴板时，可从页面文本框手动复制。
3. 接收 `bot.cpp` 和单独的中文开发总结。总结应列出策略、实际编译与练习结果及未验证事项。在同一游戏的「导入 Bot」中上传源码。

## 代理工作环境

平台为 Windows x64，需要 Python 3.12。解压到独立可写目录，在 ZIP 根目录阅读 `START_HERE.md`，执行以下命令。

```powershell
powershell -ExecutionPolicy Bypass -File .\start-devkit.ps1
```

脚本读取 `devkit-manifest.json` 的游戏 ID，准备锁定的依赖和编译器，使用模板完成一次公开案例的练习。炸弹人默认使用三个槽位，可指定 `-Players`；五子棋固定两人。首次安装需要联网，也可用 `-CompilerArchive` 和 `-WheelDirectory` 指定缓存。随后按根目录 `MODEL_TASK.md` 实现程序。正式提交须为单文件，复用基准实现时应将必要辅助代码合并到源码中。

## 公开练习

在包根目录使用对应游戏的命令，每次选择尚不存在的输出目录。

```powershell
# 炸弹人：一张地图，候选 Bot 轮换三个出生位
.\.venv\Scripts\python.exe tools\practice.py --source bot.cpp --players 3 --maps 1 --output artifacts/work/practice-3p

# 五子棋：一个公开开局，双方各执黑一次
.\.venv\Scripts\python.exe tools\practice.py --game gomoku --source bot.cpp --maps 1 --output artifacts/work/practice-pair
```

| 游戏 | 默认完整练习 | 可调参数 |
| --- | --- | --- |
| 炸弹人 | 10 张地图，双人换位，共 20 局 | `--players` 取 2～8，`--maps` 取 1～10。N 人时，每张地图轮换 N 个出生位，其余槽位使用基准的独立实例 |
| 五子棋 | 12 个三手开局，分别交换黑白，共 24 盘 | `--maps` 取 1～12，或以 `--opening-mode empty` 指定空棋盘 |

输出目录含 `summary.md`、`summary.json` 和 `replays/`。练习结果独立于应用榜单。基准实力分为 0，练习分数仅描述所用案例和对手。

## 从源码生成 ZIP

仓库根目录的 `devkit/` 保存按游戏区分的原始材料。网页在 `npm.cmd run dev` 或 `npm.cmd run build` 前生成两份任务包到 `web/public/devkits/`；生产构建将其复制到 `web/dist/devkits/`。命令行分发包由同一打包器生成，在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe tools\build_devkit.py
.\.venv\Scripts\python.exe tools\build_devkit.py --game gomoku
```

默认输出至 `artifacts/distribution/`，文件分别为 `llm-arena-devkit.zip` 和 `llm-arena-gomoku-devkit.zip`，各附一个 `.sha256` 文件。已有 ZIP 或同名校验文件时，使用 `--output` 指定新的 ZIP 路径。打包器按文件清单收集源码、任务书、许可和对应游戏的基准 WASM，并记录文件哈希。
