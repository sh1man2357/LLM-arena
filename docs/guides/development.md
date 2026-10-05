# 开发与验证

所有 Python 命令在项目根目录执行；npm 命令在 `web/` 目录执行。

## 开发服务与浏览器检查

开发服务运行 `.\.venv\Scripts\python.exe -m service --demo`；前端在 `web/` 执行 `npm run dev`。发行安装按[安装与启动](./getting-started.md)构建同源静态页面。

浏览器检查使用 `npm test`，需要本机 Chrome；`ARENA_BASE_URL` 指向专用验收实例，`ARENA_EMPTY_URL` 指向另一个新建的空实例。全量检查需这两个实例，并先通过真实工作流程提供资格 / 作业样例；最终准备与复现顺序见[版本交接](../releases/handoff-v0.2.md)。早期局部检查的范围见[页面状态记录](../records/components-and-page-states.md)。测试会改变专用数据，不对正在使用的比赛实例运行。

运行浏览器测试必须显式设置 `ARENA_BASE_URL`，不再默认连接日常使用的 8787 实例。专用实例的数据目录放在 `artifacts/work/` 下，例如：

```powershell
# 项目根目录的一个终端；完整验收样例准备见版本交接
.\.venv\Scripts\python.exe -m service --demo --port 8861 --data artifacts/work/browser-tests
# web 目录的另一个终端
$env:ARENA_BASE_URL = 'http://127.0.0.1:8861'
npm.cmd test
```

## 清理测试数据

停止测试实例后，从项目根目录预览或执行[清理工具](../../tools/cleanup-test-data.ps1)：

```powershell
powershell -ExecutionPolicy Bypass -File tools\cleanup-test-data.ps1
powershell -ExecutionPolicy Bypass -File tools\cleanup-test-data.ps1 -Apply
```

工具清理 `artifacts/work/`、`web/test-results/` 和 `web/playwright-report/`，保留验收归档、依赖、编译器和发行前端。遇到跟踪文件、链接目录或被服务占用的数据目录会停止。

`-ResetLocal` 另外清空 `artifacts/local/`，包括全部收卷、源码、作业、比赛及主办方凭据。只在确认该实例全部为测试数据，或已另行备份时使用。清空后运行 `start-arena.ps1` 会重新初始化实例并导入工程参考赛。

## 核心检查与冻结证据

已完成的工程验收证据见 [交接说明](../../artifacts/acceptance/v0.1-release/handoff.md) 和 [逐项审计](../../artifacts/acceptance/v0.1-release/audit.md)：39 项检查、300 局有效比赛、全部世界回放与 Bot 重跑，以及独立目录的另一个 300 局批次均通过。完整原始证据归档为 evidence.zip，恢复方式和 SHA-256 见交接说明。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
git log --oneline
```

检查包含规则、地图向量、真实 C++ 编译、STL/构造/堆状态、ABI、fuel trap 恢复、内存上限、watchdog、调度恢复和结果防篡改。运行时和链接决策见 [实现决策](../architecture/decisions.md)。
