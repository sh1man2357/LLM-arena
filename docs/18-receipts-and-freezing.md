# 收卷档案、源码冻结与未完成批次

记录日期：2026-10-05。此阶段补齐主办方收卷档案入口，保持固定 60 分钟、可提前交卷的协议。工程样例使用手写源码及显式外部时间记录，不冒充真实模型提交。

## 实际入口与状态

参赛者页增加“收卷与资格档案”。公开程序仍来自真实程序注册表；主办方可以另外浏览开发中、未交卷、已冻结、编译排队 / 执行中、资格通过 / 失败、逾期及中断档案。档案关联任务书哈希、固定截止时间、源码 / WASM 哈希、作业、诊断和资格记录。详情提供继续收卷、冻结源码及可参赛程序入口。

工作台使用 `/manage?session=<收卷 ID>` 定位记录。切换记录时清除原记录的未提交编辑内容；同一记录后台更新或读取重试仍保留草稿。源码上传先进入编辑区，点击最终交卷才冻结；粘贴和上传均使用相同的服务端 UTF-8 单文件提交与编译路径。

| 状态 | 可用行为及证据边界 |
| --- | --- |
| 开发中 | 继续收卷；截止固定为收到任务后 3600 秒，无 token / 轮数必填配置 |
| 未交卷 | 保留发卷和截止记录；之后收到的源码按逾期留档 |
| 已交卷 | 展示源码哈希与冻结时间；同一源码重送返回原提交，不同内容返回冲突 |
| 编译与资格 | 显示实际作业进度、尝试、日志、资格与 WASM 哈希；编译失败不重新开放源码 |
| 资格失败 | 保留原诊断和冻结源码，不加入可选参赛池 |
| 逾期 | 保留源码和时间；编译参赛请求返回 409 |
| 未完成批次 | 保留进度和已完成单局事实；没有正式汇总榜单或成绩发布入口，发布 API 返回 409 |

截止后档案会重新读取服务端状态，不凭浏览器计时自行改写记录。`external_record` 明确表示主办方确认的外部记录；不能把手动填写时间当作远端收卷过程的自动证明。精确截止、提前冻结、超时和外部时间边界另由 Python 回归验证。

## 私有读取与冻结完整性

`GET /api/v1/admin/status` 只返回当前浏览器是否已进入本机主办方工作台，不提供凭据。`GET /api/v1/receipts` 和单个档案均先检查主办方权限；匿名访问已知或未知 ID 都返回 403。公开参赛者接口不返回这些未交卷、失败或逾期的私有记录。

档案使用字段白名单，不提供原始源码、数据库幂等键、请求哈希或内部文件引用。诊断与编译元数据仅供主办方读取，可能含宿主路径；工程验收归档不是面向观众的公开比赛报告。公开投影的全面披露验收继续按 D05 独立推进。

冻结源码读取会先核对实际文件字节的 SHA-256；磁盘文件被改动时返回 409，不能把替换后的内容作为原交卷源码交付。编译 worker 已有同样的冻结输入检查。有效文件以原始字节返回，避免换行或中文编码改写。

## 验证与复现

本阶段记录位于 `artifacts/acceptance/v0.2-development/checks/`，实际截图与 API 样例封存在 [收卷证据归档](../artifacts/acceptance/v0.2-development/visual/receipts-evidence.zip)，来源、构建哈希、命令、诊断与逐文件校验见 [阶段索引](../artifacts/acceptance/v0.2-development/checks/receipts-stage.json)。

真实 Chrome 检查覆盖上传含中文注释的单文件源码、提前冻结、重复提交、拒绝覆盖、统一编译、资格与哈希、私有读取、四尺寸长名称和纯文本诊断、失败 / 未交卷 / 逾期记录、实际截止后的自动更新，以及停止批次后禁止正式排名 / 发布。七种档案状态与未完成批次各留四尺寸截图，共 32 张。粘贴编译、真实单局直播、隐藏换边批次和发布由既有工作流在当前构建上重验。

Python 完整回归为 78 项；协议检查使用无 worker 的明确构造状态，真实编译则由编译器、完整工作流与 Chrome 检查证明。浏览器记录分为收卷 / 原有工作流 4 项、不完整批次 1 项及页面 / 观赛 / 归档 / 恢复回归 26 项，不以一次执行称呼分开运行的结果。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools\prepare_performance_checks.py --data artifacts/work/receipt-check --proof artifacts/work/receipt-fixture.json
.\.venv\Scripts\python.exe -m service --port 8851 --data artifacts/work/receipt-check
# 另一个终端运行新的空实例：
.\.venv\Scripts\python.exe -m service --port 8852 --data artifacts/work/receipt-empty
# web 目录的另一个终端：
npm.cmd run build
$env:ARENA_BASE_URL = 'http://127.0.0.1:8851'
$env:ARENA_EMPTY_URL = 'http://127.0.0.1:8852'
$env:ARENA_BROWSER_RESULTS = '../artifacts/work/receipt-browser.json'
$env:ARENA_RECEIPT_EVIDENCE = '../artifacts/work/receipt-views'
npm.cmd test -- tests/receipts.spec.ts tests/workflows.spec.ts
npm.cmd test -- tests/states.spec.ts tests/spectator.spec.ts tests/evidence.spec.ts tests/zz_recovery.spec.ts
```

使用独立数据目录，单个 FIFO worker 的相关检查顺序执行；不应在另一个计算批次仍运行时开始依赖执行窗口的验证。上述全收卷文件包含创建上传样例和停止批次样例，单独筛选批次用例时必须已存在资格通过的上传工程样例。每次报告使用独立 `ARENA_BROWSER_RESULTS` 路径，以免覆盖。

首轮完整 Python 执行因沙箱禁止运行 `clang++`，六项受影响；允许执行实际编译器后完整回归通过。浏览器首轮有标题 / 状态定位错误，批次补验另有按钮定位错误和先前作业占用队列导致的启动窗口超时，均保留诊断并独立重验。首轮收卷原始日志因相对路径备份错误被覆盖，失败 JSON 已保留；不能声称那份原始日志仍在归档中。

本阶段完成 C01、C02、C06 的收卷及未完成排名边界。它只补充 A05 的部分状态；完整可访问性、全状态、最终人工审美及整版交接仍待完成。规则、评分、SDK 和冻结 v0.1 证据未改，无需为该界面入口重跑 300 局基线。
