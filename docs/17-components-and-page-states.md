# v0.2 共用组件、页面方案与读取状态

本页列出实际组件与高保真页面方案，并记录本轮读取状态修正。五类页面已共用同一视觉系统；完整异常状态 A05、可访问性 A04 和最终人工审美 A06 仍按 [前端规范](./09-v0.2-frontend.md) 另行验收。本轮不新增外部视觉素材、主题或字体服务。

## 视觉系统与组件清单

视觉方向仍为“竞技转播台”。页面由真实 Replay、已验证报告及实际收卷 / 作业记录驱动；工程 Baseline 和测试提交不作为真实模型展示赛。

| 共用基础 | 实际位置 | 用法 |
| --- | --- | --- |
| 色彩 tokens | [tokens.css](../web/src/tokens.css) | 背景 `#10151C`、面板 `#1B242D`、正文 `#F3F1E9`、辅助 `#A6B0BA`、主要操作 `#69DCC9`；警示金 / 红与地形独立定义 |
| 排版、网格和响应式 | [style.css](../web/src/style.css) | 本地中文字体；数字用等宽字体；桌面侧栏、手机底部导航、panel / card / table / 按钮共用尺寸及焦点规范 |
| 产品壳与导航 | [App.tsx](../web/src/App.tsx) | 品牌、主导航、连接提示、跳过导航、主要内容与页脚 |
| 页面标题 / 返回入口 | [ui.tsx](../web/src/ui.tsx) 中的 PageTitle / BackLink | 统一 eyebrow、标题、说明和关联操作 |
| 状态和身份 | 同文件 Badge / labels / identityColor / IdentityNames | 状态同时显示文字与标记，身份颜色按独立 ID 稳定，模型名称不充当唯一键 |
| 图标 | 同文件 Icon | 同一 SVG 线宽与尺寸，装饰图标隐藏于辅助技术 |
| 空状态 / 加载 | 同文件 State / LoadingPanel | 明确说明正在读取或没有资料，提供下一步入口；首次未知数据不以 0 冒充已确认统计 |
| 读取错误 / 保留内容 | 同文件 ErrorPanel / ReadNotice | 404、403 与临时失败分别说明；读取重试局部进行，工作台使用紧凑错误条 |
| 读取生命周期 | [api.ts](../web/src/api.ts) 中的 useResource | 数据与完整请求路径绑定；同资源暂时失败可保留确认内容，换资源 / 筛选不继承旧结果，403 / 404 清除缓存 |
| 棋盘场景 | [Board.tsx](../web/src/Board.tsx) | 同一 Canvas 绘制与实体 / 事件图层供大厅预览和观赛使用 |
| 对局列表 | [Hall.tsx](../web/src/Hall.tsx) 中的 MatchRows | 大厅、批次与参赛者档案复用参赛者、结果、Tick 和观赛入口 |
| 工作台记录 | [Manage.tsx](../web/src/Manage.tsx) | 提交、作业、旧尝试、日志和发布使用统一 panel / record-heading / record-actions / Badge 结构 |

## 五类页面的实际高保真方案

这些是发行构建的实际界面，不是另设一套无法操作的设计稿。布局、控件、真实内容与四尺寸画面可以按脚本重现。

| 页面 | 信息层次 / 视觉中心 | 真实样例及截图前缀 |
| --- | --- | --- |
| 大厅 | 标题 → 参照指标 → 真实精选棋盘 → 批次 → 筛选 / 分页对局 | 旧参考赛与本轮真实运行记录；`hall-normal` |
| 观赛 | 对局身份 → 双方 → 棋盘 / 检查器 / 事件 → 就近播放控件 → 结果与关联入口 | `reference-chain`，帧 13；`viewer-normal` |
| 批次 | 进度 / 披露 → 榜单 / 矩阵 → 配对 / 地图 → 行为解释 → 对局 | 已验证旧 300 局 `reference-v01`；`batch-normal` |
| 参赛者 | 独立身份卡；档案显示冻结信息与参赛对局 | 实际 Baseline、历史导入与本轮资格提交；`entrants-normal` / `entrant-normal` |
| 工作台 | 收卷 / 源码 → 资格；协议 / 组织 / 导入 / 备份；作业 / 发布 | 完整浏览器流程实际留下的成功与失败记录；`manage-normal` |

正常页面各有 390 / 768 / 1280 / 1440px 全页截图；额外保存首屏画面用于查看长页面的细节。真实浏览器确认无页面水平溢出，并在五类页面读取相同的实际颜色 tokens。Codex 查看桌面与手机截图，复核页面共用排版、色彩和状态结构；最终审美仍由 A06 的人工评审单独确认。

## 本轮完成的状态与恢复行为

| 状态 | 实际行为 | 验证方法 |
| --- | --- | --- |
| 首次加载 | 六个入口显示明确加载反馈，工作台未知列表不提前宣称为空 | 延迟真实 API 请求，随后继续原请求 |
| 暂时读取失败 | 解释错误并重试该读取，不整页重载 | 注入 HTTP 503；解除后由界面重试并得到实际内容 |
| 空实例 | 大厅、批次、参赛者提供准备入口；空工作台解释收卷 / 编译 / 作业 | 独立新数据目录与真实空服务，未伪造空响应 |
| 空筛选 / 切换筛选失败 | 清除条件可恢复列表；新条件失败或重试中不显示旧条件结果 | 真实无匹配查询，503 与延迟注入只作用于该新查询 |
| 资源不存在 | 显示“没有找到这份资料”与大厅入口，不停留在加载状态 | 实际请求三个不存在的对局 / 批次 / 身份 ID |
| 观赛刷新失败 / 明确拒绝 | 临时失败保留已确认棋盘与定位；403 隐藏旧画面，成功重试按 URL 恢复位置 | 真实回放与真实会话事件触发刷新，再注入元数据 503 / 403；403 注入只证明前端处理，不替代服务封存验收 |
| 工作台草稿恢复 | 读取重试保留未交卷源码、会话、名称、比赛标题和参赛池选择 | 实际收卷记录与原生输入；记录没有主框架导航 |
| 本机解锁失败 | 可从错误界面重试连接工作台 | 注入解锁 503 后恢复真实接口 |
| 倒计时显示 | 初次记录立即更新本地时间，显示不超过 60:00；服务截止仍固定为发卷后 60 分钟 | 实际创建会话，验证服务时间差为 3,600,000ms；客户端 Date.now 人为落后五秒 |

以上请求故障与客户端时钟偏差均为明确记录的测试注入，不声称实际赛事发生了这些故障。读取重试不会重发收卷、比赛或发布操作；草稿只保留在当前页面内，本轮没有实现浏览器关闭后的草稿持久化。

仍待完整覆盖：参赛者未交卷 / 编译状态的独立入口、完整资格与截止边界、直播等待 / 新尝试的全页状态整合、损坏 / 未知 schema 的文件反馈、全部批次状态、完整键盘 / 屏幕阅读器与最终人工审美。已有故障 / 直播证明见 [观赛质量](./14-viewer-quality.md) 和 [恢复说明](./13-live-and-job-recovery.md)，不能据此把 A05 整体勾选。

## 回归与证据

共用读取改动后，原有八条流程与十八条状态检查的完整运行 26 条通过，原日志保留。随后按手机截图压缩工作台错误区、修正倒计时显示，并补充页面设计与时钟检查；最终二十条状态检查通过。报告输出路径曾没有覆盖 Playwright 的显式配置：最终 JSON 从实际输出复制保存，配置现在支持 `ARENA_BROWSER_RESULTS`，独立设计检查也验证了该输出路径。色值大小写比较导致的一次 19 / 20 失败只保留工具输出摘要，原失败报告已被覆盖；这一证据限制明确记录，不伪造原 JSON 或原始日志。

最终构建、状态 JSON / 日志、完整 26 条日志、设计核对、来源及媒体哈希见 [本轮证据索引](../artifacts/acceptance/v0.2-development/checks/read-states-stage.json)。归档保存正常 / 异常四尺寸截图；工作台含本地工程诊断，仅用于开发交接，不作为公开赛事 Replay / 报告。

新读取代码另经实际 500 Tick 四尺寸性能回归：12 次首帧、144 次定位及正常播放均通过，最慢为 478ms / 24.7ms，实际 Canvas 绘制率 80.2～80.8 FPS；定义和限制沿用 [性能说明](./16-performance.md)。当前记录见 [性能回归](../artifacts/acceptance/v0.2-development/read-states-regression/checks/performance-final.json)，机器配置在同目录独立捕获。服务文件导入、规则和计算执行未改，既有 16 MiB 及后台作业证明继续保留。

归档 [read-states-evidence.zip](../artifacts/acceptance/v0.2-development/visual/read-states-evidence.zip) 共 223 个文件、18,394,035 字节，SHA-256 为 `6e0547de69d3ebada12e13abd6322d17957503679dfb98dcbd3a90b3aa1d3b31`。最终截图 123 张，包括 112 张完整正常 / 状态画面、10 张首屏和一张明确保留的预览仍加载画面；初轮截图分目录保留。正常截图补验等待真实棋盘 / 分析 / 工作台读完，不将预览加载画面计作完成的高保真方案。

复现须使用一个已导入旧证据的独立服务和一个全新空实例。当前实际实例为 8841 / 8842，数据在忽略的 `artifacts/work/`；不要复用会覆盖本轮证据的输出路径。按 README 构建后，先在根目录准备新数据并启动第一个服务；准备命令同步验证旧证据，完成后才启动：

```powershell
.\.venv\Scripts\python.exe tools/prepare_performance_checks.py --data artifacts/work/read-states-local --proof artifacts/acceptance/v0.2-read-states-local/checks/read-states-fixture.json
.\.venv\Scripts\python.exe -m service --port 8841 --data artifacts/work/read-states-local
```

保持运行，在第二个根目录 PowerShell 启动空实例；该数据目录必须是新的，不能曾经收过源码或导入证据：

```powershell
.\.venv\Scripts\python.exe -m service --port 8842 --data artifacts/work/read-states-empty-local
```

在第三个 PowerShell 的 `web` 目录设置环境，先运行真实工作流程提供正常工作台的资格与诊断样例，再运行页面检查：

```powershell
$env:ARENA_BASE_URL = 'http://127.0.0.1:8841'
$env:ARENA_EMPTY_URL = 'http://127.0.0.1:8842'
$env:ARENA_STATE_EVIDENCE = '../artifacts/acceptance/v0.2-read-states-local/visual/read-states-final'
$env:ARENA_BROWSER_RESULTS = '../artifacts/acceptance/v0.2-read-states-local/checks/browser-read-states-final.json'
npm.cmd test -- tests/workflows.spec.ts
npm.cmd test -- tests/states.spec.ts
```

两实例均只绑定本机。页面测试会创建真实收卷记录但不会提交草稿；工作流程测试会真实提交、编译和比赛。完整运行用 `npm.cmd test`，涵盖真实编译、直播、换边、发布与备份；它会改变该专用实例，不能对正在使用的比赛数据运行。验收结束分别在两实例控制台按 Ctrl+C 停止自有服务。
