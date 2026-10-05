# v0.2 观赛画面与交互验证

日期：2026-10-05。对应 A02、A03、B01、B02、B05；支持 A04 的部分自动检查。整版仍在开发，最终人工视觉、完整可访问性、全部异常状态及性能尚未验收。

## 真实画面与行为

使用固定规则的实际 WASM 执行记录生成十个工程案例，独立参赛者明确标注“工程 WASM 检查，不是模型生成”。这些案例不计入正式模型成绩。生成器调用现有 runner / Wasmtime，再通过原始 Replay 的世界验证和公开帧投影导入；不手绘故障动画、不修改冻结规则。

| 案例 | 浏览器核对 |
| --- | --- |
| 双方 / 单方初始化失败 | 唯一初始帧、0 次结算、初始化淘汰文案；没有 Tick -1 或假造 fuel |
| fuel / 非法动作 / trap | 故障类型、累计状态、淘汰事件及结果；trap 单独显示“运行崩溃” |
| 持久输出失败 | 基础设施失败，没有正式胜者 |
| 硬墙阻挡 | 位置未变，合法受阻不算动作故障 |
| 放弹后逃离 | 原定 Tick 4、剩余 3 / 0 Tick，爆炸后下一 Tick 无遗留火焰 |
| 连锁本 Tick 新炸弹 | Tick 13 引爆原定 Tick 17 的新炸弹，同 Tick 淘汰两人 |
| owner 先崩溃 | 已淘汰者的炸弹照常爆炸，并连锁另一枚炸弹 |

观赛检查器新增当前 Tick 的炸弹身份、坐标、owner、原定到期 Tick、到期 / 连锁原因及软墙销毁坐标。覆盖格与真实帧逐格比较：除被玩家 / 炸弹占据的中心像素外，检查全部 143 格的爆炸叠层；显示范围来自既有软墙快照规则。查看下一帧时不保留上一 Tick 的火焰。

切换对局时重置玩家 / 格子选择和旧提示。终局显示实际结算次数；初始化未完成或本 Tick 未调用时明确说明，不填入此前成功调用的 fuel。全屏按钮与浏览器实际状态同步，F / Escape 可退出。

## 布局、操作与对比度

14 组 Chrome 检查及 42 张最终截图覆盖大厅、观赛、批次、参赛者列表 / 档案、主办方工作台，宽度为 390 / 768 / 1280 / 1440px。截图等待真实记录加载：参考批次 300 局、列表 / 档案 100 行、所有参赛者与工作台认证完成；另有手机首屏预览便于人工阅读。长名称为 92 个字符的独立工程展示名称，只修改该隔离实例的显示元数据，原比赛和成绩未改。

所有检查尺寸无页面水平溢出，棋盘保持 13:11，即各格为正方形；矩阵 / 案例图在容器内可横向滚动。长名称修正覆盖检查器、榜单、矩阵、配对标题和卡片。实际鼠标拖动、原生触控选择格子 / 拖动进度、单步、首尾、五档活动播放、暂停、事件定位、全屏以及同地图换边往返通过；换边保留帧 1，参赛者槽位反转。

Tab 可先到“跳到主要内容”，Enter 聚焦主内容；焦点为可见 2px 描边。输入控件聚焦时不拦截方向键。玩家 / 格子选择提供 `aria-pressed`，详情按钮提供 `aria-expanded`。棋盘有当前帧文字标签，玩家 / 格子信息及当前爆炸事实可在检查器读取；核心播放触控按钮不小于 44 × 44px。减少动效时跳过位置插值，仍按原速度逐帧播放；Canvas 插值完成后停止无用的持续重绘。

25 份实际页面对比度报告无已测文本失败，最低为 4.754:1；普通文本要求 4.5:1，大字要求 3:1。实测输入边界 3.569:1，硬墙 / 道路 3.185:1、软墙 / 道路 3.494:1。测量通过计算样式与祖先背景合成；跳过禁用 / 隐藏 / 半透明内容和 SVG / Canvas。墙体另按真实绘制色测量。矩阵自身配对横线、选中案例编号及输入边界已按实测修正。报告不是全面 WCAG 或读屏器验收，A04 继续保留待验收。

## 证据、来源与复现

- [WASM 案例索引](../artifacts/acceptance/v0.2-development/checks/viewer-cases.json)：十份原始 Replay 与模块哈希、实际结果和终帧事件。
- [浏览器画面检查](../artifacts/acceptance/v0.2-development/checks/viewer-quality.json)：控制、换边、触控、截图文件名、Chrome 版本及对比度。
- [常规流程回归](../artifacts/acceptance/v0.2-development/checks/browser-viewer-quality.json)：首次七条通过，备份等待超时；实际备份约 93.4 秒后成功，超过原脚本 90 秒等待。仅调整这条检查的上限后单独重验通过，保留首次和重验原日志。
- [证据包与 SHA-256 索引](../artifacts/acceptance/v0.2-development/checks/viewer-stage.json)：当前前端 / 验收脚本源码哈希，以及 [截图与操作录屏 ZIP](../artifacts/acceptance/v0.2-development/visual/viewer-quality.zip)。包含 42 张 PNG、最终 Chrome 操作 WEBM 及对应检查文件；不包含私有备份或原始隐藏输入。

画面由本项目的 HTML / CSS / Canvas / SVG 生成，无外部图片、字体 CDN 或新增第三方视觉素材。录屏使用锁定 Playwright 1.63.0 的浏览器录制能力及其 FFmpeg 缓存，保存在项目 `.tools/playwright`。运行环境为 Windows x64、Python 3.12.14、Node 24.19.0、Chrome 154.0.8037.93，版本锁文件不变。

新建独立验收目录后执行，不指向正在使用的正式数据：

```powershell
.\.venv\Scripts\python.exe tools\prepare_viewer_cases.py --data artifacts\work\viewer-check-new --proof artifacts\acceptance\v0.2-development\checks\viewer-cases.json
.\.venv\Scripts\python.exe -c "import uvicorn; from service.app import create_app; uvicorn.run(create_app('artifacts/work/viewer-check-new', workers=True), host='127.0.0.1', port=8799)"
```

另开终端，在 `web/` 中构建并检查；先完成常规流程，再检查画面：

```powershell
npm.cmd run build
$env:ARENA_BASE_URL = 'http://127.0.0.1:8799'
npm.cmd test
$env:PLAYWRIGHT_BROWSERS_PATH = '..\.tools\playwright'
node.exe node_modules\@playwright\test\cli.js install ffmpeg
node.exe tools\verify-viewer-quality.mjs http://127.0.0.1:8799
```

检查器输出最终 PNG / WEBM 与 `viewer-quality.json`。常规 Playwright 原日志为 `web/test-results/results.json`；归档脚本仅收录最终画面检查列出的文件，排除失败 / 早期运行录屏。新复现时，在根目录执行 `.\.venv\Scripts\python.exe tools\archive_viewer_evidence.py --regression-log web\test-results\results.json`，要求新一轮全部八条通过，并保存该轮原日志。当前阶段的归档则保留首次和单条重验记录。复现结果中的录屏文件名及哈希会随运行变化。

本轮图像检查由 Codex 查看真实截图并记录修正，不替代用户或独立人工最终审美评审。完整状态一致性、屏幕阅读器 / 全页面键盘与触控、性能测量、最终人工审美与整版交接仍待完成。
