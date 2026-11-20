# 开发与验证

按[安装指南](getting-started.md)准备环境。默认直接在 `main` 工作，改动验证后及时提交。数据、日志、构建产物和依赖缓存置于 Git 忽略目录。仓库约定见 [AGENTS.md](../../AGENTS.md)。

## 按改动范围验证

| 范围 | 工作目录 | 命令 |
| --- | --- | --- |
| Python 核心、服务与工具 | 仓库根目录 | `.\.venv\Scripts\python.exe -m unittest discover -v` |
| 文档 | 仓库根目录 | `.\.venv\Scripts\python.exe tools\check_docs.py` |
| 前端 | `web/` | `npm.cmd run build`、`npm.cmd run test:protocol` |
| 页面交互与真实对局 | 仓库根目录，先构建前端 | `powershell -ExecutionPolicy Bypass -File tools\test-browser.ps1` |
| 公开仓库检查 | 仓库根目录 | `.\.venv\Scripts\python.exe tools\check_repository.py` |

前端开发服务器与构建均先调用 Python 打包工具，需已准备好仓库虚拟环境及 WASI SDK。文档检查涵盖本地链接和代码围栏。任务书或 SDK 有变更时，还应检查实际 ZIP 中的入口和内嵌头文件。

Python 测试覆盖规则、编译与沙箱、对局和录像复现、服务与计分。前端协议测试覆盖帧顺序、重复帧、缺口及完整快照。若系统临时目录不可写，可在当前 PowerShell 会话中指定独立工作目录后运行检查。

```powershell
$taskTemp = (New-Item -ItemType Directory -Force artifacts/work/test-tmp).FullName
$env:TEMP = $taskTemp
$env:TMP = $taskTemp
$env:TMPDIR = $taskTemp
```

## 浏览器测试

`tools/test-browser.ps1` 默认使用端口 8798 和新建的 `artifacts/work/browser-*` 目录，启动测试服务、运行 Playwright 并关闭该实例。脚本拒绝端口 8787 和已有数据目录。运行环境需要 Chrome。测试会创建 Bot 与对局，服务日志保存在测试数据目录，浏览器结果默认写入 `web/test-results/`。

CI 在 Windows 环境安装锁定依赖，执行 Python、文档、仓库、前端协议和浏览器检查，并生成两种命令行分发包。工作流见 [ci.yml](../../.github/workflows/ci.yml)。

## 产物清理

在仓库根目录运行以下命令预览候选路径，停止相关测试实例并核对目标后，才可通过 `-Apply` 执行。

```powershell
powershell -ExecutionPolicy Bypass -File tools\cleanup-test-data.ps1
```

`-IncludeGenerated` 将分发包、前端构建等生成文件纳入范围。`-OldDevkitsOnly` 单独用于整理 `artifacts/distribution/`：按游戏保留最新的已识别 ZIP，校验保留包的 SHA-256 后列出较旧版本。`-ResetLocal` 会将默认主办方数据目录纳入删除范围，仅在明确要求重置时使用。
