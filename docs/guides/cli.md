# CLI 编译与单局检查

所有命令在项目根目录执行。图形应用的导入会自动编译，以下工具用于开发与诊断。

## 编译

```powershell
.\.venv\Scripts\python.exe arena.py build sdk/template.cpp --output artifacts/work/template.wasm
.\.venv\Scripts\python.exe arena.py qualify artifacts/work/template.wasm
.\.venv\Scripts\python.exe arena.py baselines --output artifacts/work/baselines
```

统一编译生成 WASM、编译日志、依赖和元数据；检查 ABI、内存、禁止特性、初始化及公开状态调用。失败返回非零退出码，不作为正常 0 分对局。

## 一局与复现

使用尚不存在的输出目录，已有录像不覆盖：

```powershell
.\.venv\Scripts\python.exe arena.py match --bot safe=artifacts/work/baselines/safe.wasm --bot random=artifacts/work/baselines/random.wasm --map-seed 1 --output artifacts/work/single-01
.\.venv\Scripts\python.exe arena.py verify artifacts/work/single-01/replay.jsonl
.\.venv\Scripts\python.exe arena.py verify artifacts/work/single-01/replay.jsonl --wasm artifacts/work/baselines/safe.wasm --wasm artifacts/work/baselines/random.wasm
.\.venv\Scripts\python.exe arena.py view artifacts/work/single-01/replay.jsonl --output artifacts/work/single-01/view.txt
```

提供 2～8 个 `--bot`，按槽位顺序各自为战。可为每个槽位传一个 `--bot-seed`，用 16 位十六进制字符串；默认依次使用 1 到参赛人数。`map` 命令可用 `--players N` 生成相应人数的地图，默认 2。世界校验核对记录事实，Bot 校验另需原程序及相同版本。

```powershell
.\.venv\Scripts\python.exe arena.py map 1 --output artifacts/work/map-1.json
```

CLI 单局生成的文件用于开发，不自动导入应用或计入本地榜单。已删除 tournament、report、seeds 和 verify-all 命令。多地图基准练习仍可通过[开发包练习工具](model-development.md)逐局执行，无批次管理业务。
