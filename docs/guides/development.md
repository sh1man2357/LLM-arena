# 开发与验证

默认在 main 分支工作，保留 Git 历史。源码、配置、测试和文档同步维护；数据、日志、任务 ZIP 和构建产物放入忽略目录。

## 必须检查

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe tools\check_docs.py
```

在 web 目录执行：

```powershell
npm.cmd run build
npm.cmd run test:protocol
```

Python 测试覆盖规则、地图、真实 C++ 编译、ABI / fuel / 内存、单局与复现、导入、计算槽位、录像帧、中断、旧数据隔离和榜单。协议测试覆盖顺序帧、重复、缺口和完整快照。

五子棋测试另覆盖四方向成五、长连、满盘、非法落子、认输、故障判负、两盘换色与恢复、独立游戏筛选、全部 12 开局双方颜色的基准预算，以及开发包 / CLI / 练习的完整流程。

若执行环境的系统临时目录不可写，可在当前 shell 指定项目忽略目录：

```powershell
$taskTemp = Join-Path (Get-Location) 'artifacts\work\test-tmp'
New-Item -ItemType Directory -Force -Path $taskTemp | Out-Null
$env:TEMP = $taskTemp
$env:TMP = $taskTemp
.\.venv\Scripts\python.exe -m unittest discover -v
```

## 浏览器检查

只使用专用实例，不连接主办方数据。先在项目根目录启动：

```powershell
.\.venv\Scripts\python.exe -m service --demo --port 8798 --data artifacts/work/core-browser
```

在另一个终端的 web 目录执行：

```powershell
$env:ARENA_BASE_URL = 'http://127.0.0.1:8798'
npm.cmd test
```

测试验证真实 .cpp 导入、运行与回看、榜单、窄屏和已删除入口。测试会创建 Bot 与运行记录，截图和结果在 web/test-results。更换实例时使用新的数据目录；测试服务器停止后保留输出供复核。

## 清理

清理产物只使用 tools/cleanup-test-data.ps1，先预览：

```powershell
powershell -ExecutionPolicy Bypass -File tools\cleanup-test-data.ps1
```

确认不再需要的测试产物并停止测试实例后，才使用 -Apply。-IncludeGenerated 增加构建与分发产物；-ResetLocal 会删除默认本机全部数据，需要用户明确要求。本轮简化不执行这些删除。保留 .venv、.tools、web/node_modules 与既有主办方数据。
