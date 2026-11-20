# 安装与启动

以下命令均在项目根目录执行。支持 Windows x64。浏览器应用需要 Python 3.12、Node.js 24.19.0 和 npm 11.17.0。仅使用命令行或任务包时，需要 Python 和 WASI SDK，无需安装 Node.js。

## 浏览器应用

先检查 Node.js 与 npm 的版本。两者必须分别匹配锁定值；使用其他 npm 版本时，先在所选 Node.js 环境中安装 npm 11.17.0。

```powershell
node --version
npm.cmd --version
powershell -ExecutionPolicy Bypass -File tools\setup-ui.ps1
powershell -ExecutionPolicy Bypass -File .\start-arena.ps1
```

安装脚本创建 `.venv/`、按哈希安装 Python 依赖、校验并解压 WASI SDK，随后运行 `npm ci`、生成两个游戏的任务包并构建网页。首次安装需访问 PyPI、GitHub 和 npm。WASI SDK 压缩包约 625 MiB，另需解压空间。

| 参数 | 用途 |
| --- | --- |
| 安装时 `-Python` | 指定 Python 3.12 可执行文件。省略时脚本查找本机已安装的解释器 |
| 安装时 `-NodeDirectory` | 指定同时包含 `node.exe` 和 `npm.cmd` 的目录 |
| 安装时 `-CompilerArchive`、`-WheelDirectory` | 使用本地 SDK 压缩包和 Python wheel 缓存，仍按锁定哈希校验 |
| 启动时 `-Port`、`-Data`、`-NoBrowser` | 指定本机端口、数据目录，或仅启动服务 |

启动后默认打开 `http://127.0.0.1:8787`。服务为每个游戏准备一个基准 Bot。默认数据目录为 `artifacts/local/`，同一目录只能由一个执行器使用。在启动控制台按 Enter 停止服务；未完成的运行在服务恢复时标记为中断。

## 更新已有安装

停止正在运行的服务，更新源码（使用 Git 时可执行 `git pull --ff-only`），重新运行 `tools\setup-ui.ps1`，再运行 `start-arena.ps1`。沿用原数据目录即可读取已有 Bot 和录像。

## 命令行环境

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup.ps1
```

该入口准备 Python 运行时依赖及 WASI SDK，不构建网页。支持 `-Python`、`-CompilerArchive` 和 `-WheelDirectory`。后续操作见 [CLI 指南](cli.md)。模型收到 ZIP 时，使用包根目录的 `start-devkit.ps1`，详见[任务包指南](model-development.md)。
