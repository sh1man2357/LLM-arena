# v0.2 最终视觉走查与人工确认

日期：2026-10-06。工程视觉走查者：Codex。**最终人工审美确认：待项目负责人实际查看后确认。** 不把 AI 查看截图或自动检查记作真人评审。

## 已完成的工程视觉走查

实际页面使用同一字体、深色 tokens、方格棋盘、身份色、按钮、表格、日志和状态语言。正常短名 / 92 字符长名、满数据、空态、失败、正常胜负、同 Tick 平局、0 Tick 和终局已保留四尺寸画面；最终交互录像与截图来自真实程序 / 回放，没有截图修饰或模拟比赛。

| 问题 | 级别 | 修正与复核 |
| --- | --- | --- |
| 部分控件不足 44px | 阻断 | 时间轴、速度、顶部操作与案例点扩大；四尺寸实际尺寸检查通过 |
| 手机自动滚动后时间轴可能被底部导航遮挡 | 阻断 | 根滚动区域避让；原生触控命中检查与拖动通过 |
| 桌面超长对抗名称把播放控制推离首屏 | 阻断 | 对抗栏两行，完整身份在标题和检查器保留；1280 / 1440 的首屏控件检查通过 |
| 案例点加宽后全部 50 个不同时可见 | 非阻断 | 局部横向滚动、明确滚动提示、数字和可访问名称保留；整页无水平溢出 |
| 深色表面、细边线、紧凑数字与长日志的风格一致性 | 评审项 | 实际画面逐页核对；详细日志可折叠，不抢占主要观赛信息 |

工程检查没有发现未解决的上述交付阻断问题。审美水平和最终人工认可仍由负责人判断；这是原前端规范要求的独立最后一步。

## 逐页复核结论

下列正常页面均已实际查看 390 / 768 / 1280 / 1440px 的画面，补充的可读首屏位于 `final/visual/review-viewport/`，逐张来源 URL、尺寸和 SHA-256 见 `final/checks/review-viewport.json`。截图等待事件连接和实际身份元数据读取完成，避免将读取过渡帧作为最终画面。长全页画面仍在 `viewer-quality/`，原始清晰度保存在 ZIP 中。

| 页面 | 信息、排版与一致性复核 | 工程处理结论 |
| --- | --- | --- |
| 大厅 | 标题 → 精选真实棋盘 → 批次 → 记录层级明确；手机卡片改为单列，导航与舞台共用同一色板 | 未发现关键遮挡或整页溢出；列表在大厅分页 |
| 观赛 | 数字槽位与颜色共同标识玩家；长名两行，棋盘保持比例；桌面控制位于首屏，768px 需下滚，手机控制在棋盘下方 | 长名和触控遮挡已修复；桌面 / 手机命中与拖动复验通过 |
| 批次 | 桌面榜单与矩阵并置，小屏纵向；分数列稳定，92 字符姓名完整换行，不覆盖胜负数字 | 长名增加行高属非阻断；保留完整文本和独立 ID；案例点使用局部滚动 |
| 参赛者 | 四 / 二 / 一列身份卡片，同一头像边框、状态、哈希和入口；历史工程样例明确注明来源 | 长名卡片增加高度属非阻断；全部卡片仍可读、可进入 |
| 身份档案 | 标题与哈希按窄屏断行；数据总数与真实对局事实清晰 | 超长标题占用较多首屏、最新 100 局形成长列表属非阻断；保留完整姓名，不将首屏截图当作全部记录 |
| 主办方工作台 | 收卷、资格、组织、导入、备份与作业沿用观赛字体 / 边线；桌面分栏、手机单列，日志折叠 | 主操作与禁用态可辨；真实排队 / 编译与失败档案另存；无临时默认主题 |

留白、字重、数字对齐、图标与深色表面一致；长名称满数据确实增加阅读密度，接受完整身份信息优先的处理。时间轴、爆炸、玩家移动与减少动效的动态复核依实际操作记录，静态截图不证明动效。加载、空态、拒绝、失败和恢复的覆盖 / 构造方式见 [工程状态记录](./19-final-engineering-acceptance.md)，最终真人审美结论仍不预填。

## 可查看的实际画面

最终媒体位于 `artifacts/acceptance/v0.2-development/final/visual/`，同时按哈希封存在 `final/evidence.zip`。解压后可检查所有四尺寸、状态和录像。

可以直接打开 [桌面观赛首屏](../artifacts/acceptance/v0.2-development/final/visual/review-viewport/viewer-1280.png)、[手机观赛首屏](../artifacts/acceptance/v0.2-development/final/visual/review-viewport/viewer-390.png)、[桌面大厅](../artifacts/acceptance/v0.2-development/final/visual/review-viewport/hall-1440.png) 和 [手机榜单](../artifacts/acceptance/v0.2-development/final/visual/review-viewport/batch-390.png)。Git 源码交接保留这四张代表画面供直接查看；完整媒体在带哈希的 ZIP 中，本机也保留全部原图。

| 页面 / 范围 | 桌面与手机代表截图 |
| --- | --- |
| 大厅、可立即观赛入口 | `viewer-quality/hall-1280.png`、`viewer-quality/hall-390-viewport.png` |
| 观赛、长名称与主要控制 | `viewer-quality/viewer-1280.png`、`viewer-quality/viewer-390-viewport.png` |
| 批次榜单、矩阵和案例 | `viewer-quality/batch-1440-viewport.png`、`viewer-quality/batch-390-viewport.png` |
| 参赛者、身份档案 | `viewer-quality/entrants-1280.png`、`viewer-quality/profile-390-viewport.png` |
| 主办方工作台 | `viewer-quality/manage-1280.png`、`viewer-quality/manage-390-viewport.png` |
| 收卷、失败、逾期、未完成排名 | `receipts/qualified-1280.png`、`receipts/qualification-failed-390.png`、`receipts/incomplete-batch-1280.png` |
| 空态、读取失败与局部恢复 | `states/` 中实际页面状态截图 |
| 实际等待与编译 | `queued-receipt-1280.png`、`compiling-receipt-1280.png` |

人工确认需检查：风格是否统一、棋盘与控制是否突出、中文 / 长名排版是否自然、异常状态是否清晰、移动端是否可读且可操作。确认后记录实际评审者、范围、意见和结果，再勾选 A06；当前没有预填确认人或“已通过”结论。
