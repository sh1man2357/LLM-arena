# 开发与验证

默认在 main 分支工作，保留 Git 历史。源码、配置、测试和文档同步维护；数据、日志、任务 ZIP 和构建产物放入忽略目录。

## 必须检查

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe tools\check_docs.py
.\.venv\Scripts\python.exe tools\check_repository.py
```

在 web 目录执行：

```powershell
npm.cmd run build
npm.cmd run test:protocol
```

Python 测试覆盖规则、地图、真实 C++ 编译、ABI / fuel / 内存、单局与复现、导入、计算槽位、录像帧、中断、旧数据隔离和榜单。协议测试覆盖顺序帧、重复、缺口和完整快照。

五子棋测试另覆盖四方向成五、长连、满盘、非法落子、认输、故障判负、两盘换色与恢复、独立游戏筛选、全部 12 开局双方颜色的基准预算，以及开发包 / CLI / 练习的完整流程。

人机测试覆盖黑白执子、真实 WASM 应手、成五与认输、重复 / 过期 / 占用位置输入、刷新续玩、录像验证和榜单排除。浏览器用例 `web/tests/human-gomoku.spec.ts` 验证首页入口、鼠标 / 键盘落子、移动端布局、回看及再来一局。

Bot 管理测试覆盖名称 / 备注编辑、历史快照隔离、批量事务回滚、基准删除保护与编译 / 参赛保护、开赛和删除并发、回收站恢复、录像和统计保留。基准改名用例覆盖旧记录兼容、启动复用、产物损坏修复、保持唯一身份及 0 分锚点。`web/tests/bots.spec.ts` 使用专用实例验证编辑、搜索、状态筛选、分页选择、批量恢复和窄屏布局；`web/tests/reference.spec.ts` 验证两个游戏的基准改名和独立标记。

若执行环境的系统临时目录不可写，可在当前 shell 指定项目忽略目录：

```powershell
$taskTemp = Join-Path (Get-Location) 'artifacts\work\test-tmp'
New-Item -ItemType Directory -Force -Path $taskTemp | Out-Null
$env:TEMP = $taskTemp
$env:TMP = $taskTemp
.\.venv\Scripts\python.exe -m unittest discover -v
```

## 浏览器检查

自动启动独立测试实例、执行浏览器测试并关闭实例：

```powershell
powershell -ExecutionPolicy Bypass -File tools\test-browser.ps1
```

脚本默认使用新建的 `artifacts/work/browser-*` 数据目录，拒绝主服务端口 8787、工作目录以外的数据目录和已有数据目录。只关闭自己创建的进程，保留日志和测试结果。也可按下面的手动方式指定专用实例。

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

## 公开发布检查

CI 在 Windows runner 上从空 checkout 安装 Python / npm 依赖和 WASI SDK，执行全部检查并构建两个开发包。Action 固定到提交 SHA，工作流只具有读取仓库内容的权限。

`check_repository.py` 检查已跟踪路径、全部可达历史中的产物 / 私有路径、超过 100 MiB 的对象，以及常见凭据格式；输出只包含路径和对象标识，不输出疑似凭据内容。模式扫描不能替代对个人数据和第三方授权的人工复核。仓库不提交数据与安装缓存，开发包必须包含项目许可证、第三方说明和编译运行库许可文本。

## 清理

清理产物只使用 tools/cleanup-test-data.ps1，先预览：

```powershell
powershell -ExecutionPolicy Bypass -File tools\cleanup-test-data.ps1
```

确认不再需要的测试产物并停止测试实例后，才使用 -Apply。-IncludeGenerated 增加构建与分发产物；-ResetLocal 会删除默认本机全部数据，需要用户明确要求。本轮简化不执行这些删除。保留 .venv、.tools、web/node_modules 与既有主办方数据。

只整理历史任务包时，先运行 `powershell -ExecutionPolicy Bypass -File tools\cleanup-test-data.ps1 -OldDevkitsOnly` 预览，再加 `-Apply` 执行。该模式只处理 `artifacts/distribution/` 中已识别的开发包及对应 SHA-256 文件，按文件修改时间为每个游戏保留最新一份，删除前验证保留包的校验和。它不清理测试目录、前端构建或主办方数据，也不能与其他清理范围选项组合。
