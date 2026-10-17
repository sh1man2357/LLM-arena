# 安装与启动

所有命令在项目根目录执行。

## 浏览器应用

支持 Windows x64、Python 3.12、Node 24.19.0 与 npm 11.17.0，运行版本见 `tools/runtime-lock.json`。首次准备执行：

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup-ui.ps1
powershell -ExecutionPolicy Bypass -File .\start-arena.ps1
```

安装脚本使用哈希锁定的 Python 依赖、已校验 SDK 和 `npm ci`，随后构建前端。可用 `-Python`、`-NodeDirectory` 明确指定运行环境；`-CompilerArchive`、`-WheelDirectory` 可复用本地缓存。前端首次安装仍需 npm 网络访问。只修改项目目录和安装进程的 PATH，不修改系统设置。

不需要安装 Codex。Python 检测优先使用 PATH 中的 Python 3.12 和 `py -3.12`，再尝试常见安装目录；已有 Codex Python 时仅作为最后的可选兼容来源。使用明确的安装路径：

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup-ui.ps1 -Python 'C:\Python312\python.exe' -NodeDirectory 'C:\tools\node-v24.19.0-win-x64'
```

Node 目录应同时包含 `node.exe` 和 `npm.cmd`。可先执行 `node --version` 与 `npm.cmd --version` 核对版本；脚本会拒绝不匹配的运行环境。网络受限时使用官方 SDK 缓存和已下载的 Python wheel；SDK 哈希不匹配时应重新获取官方文件，不修改配置绕过校验。

启动后打开本机浏览器，默认 `http://127.0.0.1:8787`；在启动控制台按 Enter 停止该实例及自有 worker。若停止时正在计算，下一次启动将作业标为中断，可从记录建立新对局；不提供断点恢复。可用 `-Port 8791` 避开端口冲突，`-NoBrowser` 仅启动服务。同一数据目录只允许一个 worker 实例。

更新代码后，先停止服务，再执行 `git pull --ff-only` 和 `tools\setup-ui.ps1`，最后重新启动，以更新依赖和前端构建。本机数据位于 `artifacts/local/`，更新源码不会自动删除数据。不要把新源码直接覆盖正在使用的依赖或数据目录。

## 仅使用命令行

首个支持和验收平台是 Windows x64、PowerShell、Python 3.12。需要 Git 才能使用源码版本记录；运行程序本身不需要 Git。依赖锁定 Wasmtime 49.0.0 和 WASI SDK 33.0 / Clang 22.1.0，安装包校验 SHA-256。

在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup.ps1
```

脚本使用与浏览器应用相同的 Python 检测；也可明确指定已安装的 Python 3.12：

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup.ps1 -Python 'C:\Python312\python.exe'
```

下载需要访问 PyPI 和 GitHub；编译器官方压缩包约 625 MiB，解压还需额外磁盘空间。只写入项目内 .venv 和 .tools，不修改系统 PATH。如果已经缓存同一官方包，可加 `-CompilerArchive 'C:\cache\wasi-sdk-33.0-x86_64-windows.tar.gz'`，仍会校验哈希。
