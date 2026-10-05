# 安装与启动

所有命令在项目根目录执行。

## 浏览器应用

支持 Windows x64、Python 3.12、Node 24.19.0 与 npm 11.17.0，运行版本见 `tools/runtime-lock.json`。首次准备执行：

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup-ui.ps1
powershell -ExecutionPolicy Bypass -File .\start-arena.ps1
```

安装脚本使用哈希锁定的 Python 依赖、已校验 SDK 和 `npm ci`，随后构建前端。可用 `-Python`、`-NodeDirectory` 明确指定运行环境；`-CompilerArchive`、`-WheelDirectory` 可复用本地缓存。前端首次安装仍需 npm 网络访问。只修改项目目录和安装进程的 PATH，不修改系统设置。

启动后打开本机浏览器，默认 `http://127.0.0.1:8787`；在启动控制台按 Enter 停止该实例及自有 worker。若停止时正在计算，下一次启动将作业标为中断，由工作台恢复；当前单局从冻结输入重新运行。可用 `-Port 8791` 避开端口冲突，`-NoBrowser` 仅启动服务。同一数据目录只允许一个 worker 实例。

## 仅使用命令行

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
