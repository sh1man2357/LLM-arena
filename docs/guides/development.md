# 开发与验证

Python 命令在项目根目录执行；npm 命令在 `web/` 执行。先按[安装与启动](getting-started.md)准备依赖和编译器。

默认在 `main` 分支开发；项目整理保留 Git 历史。代理开发约定见 [AGENTS.md](../../AGENTS.md)。应用版本和规则 / SDK / 评测标识用于复现，不因清理文件而重置。

## 核心检查

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe tools\check_docs.py
```

检查覆盖规则、地图、真实 C++ 编译、ABI、fuel、内存、调度、回放、收卷、结果防篡改、导入与恢复。参考样例由当前基准源码和公开配置生成，缓存于 `artifacts/work/reference/`，首次检查需要编译器。连锁样例的源码在 `bots/examples/`。

## 前端与浏览器

在 `web/` 执行 `npm run dev` 开发界面、`npm run build` 构建静态页面、`npm run test:protocol` 检查直播帧合并。

浏览器测试使用 Chrome 和专用实例，显式设置 `ARENA_BASE_URL`；页面状态测试另需空实例，由 `ARENA_EMPTY_URL` 指定。测试会创建收卷、作业和比赛，数据放在 `artifacts/work/`。

```powershell
# 项目根目录，独立终端
.\.venv\Scripts\python.exe -m service --demo --port 8861 --data artifacts/work/browser-tests
# 项目根目录，另一个终端
.\.venv\Scripts\python.exe -m service --port 8862 --data artifacts/work/browser-empty
# web 目录，第三个终端；等待参考赛生成完成
$env:ARENA_BASE_URL = 'http://127.0.0.1:8861'
$env:ARENA_EMPTY_URL = 'http://127.0.0.1:8862'
npm.cmd test
```

`workflows.spec.ts` 提供后续页面检查使用的真实冻结提交和比赛样例。运行 `release.spec.ts` 前，在项目根目录导出连锁样例：

```powershell
.\.venv\Scripts\python.exe tools\build_reference.py --chain-output artifacts/work/browser-fixtures/chain.jsonl
```

独立观赛、报告与性能工具位于 `tools/` 和 `web/tools/`，以当前源码准备数据，结果写入 `artifacts/work/`。视觉修改需检查实际页面，尺寸、对比度和性能测量不能替代人工判断。

## 清理生成数据

停止测试实例后运行：

```powershell
powershell -ExecutionPolicy Bypass -File tools\cleanup-test-data.ps1
powershell -ExecutionPolicy Bypass -File tools\cleanup-test-data.ps1 -Apply
```

默认清理 `artifacts/work/`、`web/test-results/` 和 `web/playwright-report/`。遇到跟踪文件、链接目录或服务占用的工作区会停止，依赖、编译器和前端构建保留。

全量清理生成产物时增加 `-IncludeGenerated`，先预览，再执行：

```powershell
powershell -ExecutionPolicy Bypass -File tools\cleanup-test-data.ps1 -IncludeGenerated
powershell -ExecutionPolicy Bypass -File tools\cleanup-test-data.ps1 -IncludeGenerated -Apply
```

此选项另外删除历史验收输出、任务 ZIP、`web/dist/`、TypeScript 构建缓存与 Python 源码缓存。随后启动界面前重新执行 `npm.cmd run build`；开发环境与 `artifacts/local/` 的主办方数据保留。历史源码和验收记录可从清理前的 Git 提交查阅。

`-ResetLocal` 另外清空 `artifacts/local/` 的全部收卷、源码、作业、比赛和本机凭据。清空后启动应用会重新生成工程参考赛。
