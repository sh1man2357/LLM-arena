# v0.2 成绩核对与行为分析

> 验收记录：下文的检查数量、未完成项和结论属于各自记录时点。当前版本状态见[版本交付清单](../releases/v0.2.md)，最终复现入口见[版本交接](../releases/handoff-v0.2.md)。

日期：2026-10-05。对应 D02、D07。新增描述统计与检查入口，冻结规则、报告算法、旧成绩及原始 Replay 均未修改。

## 界面与证据

用三个真实批次核对：旧 v0.1 三 Baseline 300 局、当前 SDK 三 Baseline 300 局，以及六个工程 WASM 的 90 局全配对 / 换边批次。最后一组不是模型提交；两个 WAIT Bot 提供并列成绩，另四个模块在不同输入下提供 fuel、非法动作、trap 和初始化失败。模块先通过公开资格 smoke check，之后在实际比赛中触发故障；资格不保证所有比赛输入都运行成功。

归档导入重新验证完整调度、世界轨迹和 Reporter 输出。当前 SDK 和工程批次通过正常收卷关闭操作开放所有对局，再由匿名 Chrome 核对。690 份原始 Replay 另由独立脚本直接累计动作 / 事件 / 结果，与 API 分析逐字段比较；该脚本不调用前端事实计算函数来生成预期值。

真实 Chrome 检查全部 42 个有方向配对、690 次地图案例选择，以及每次对应的两局换边入口：

- 榜单排名、对手数、均分、胜 / 负 / 平与验证报告一致；六人批次出现真实同分，并列名次相同，没有额外破同分。
- 矩阵值、有效局数、95% 地图区间、出生槽位均分、平均 Tick 与报告一致。每个案例的数值标签、图上位置和实际两局入口均逐项核对。
- 完整展示 12 项统计和四项故障率，包括调用 / fuel、放弹、爆炸死亡、单一归因击杀 / 自杀、混合归因、运行淘汰与初始化失败。率的分母分别为调用次数或有效对局；少于十个地图案例显示“样本不足”。
- 初始化失败、动作故障与 trap 有非零输入覆盖；trap 不计为动作故障或自杀。全局单次最高 fuel 取最大值，不将最高值相加。
- 修正对局列表原先缺少案例索引 / 换边标记的问题，使列表和详情 API 一致。

批次页按完整批次展示平局分析，选择配对 / 案例不会将全局数字伪装成局部数字。新分析只纳入已完成、已验证且有效的对局；失败 / 中断不计入正式成绩。旧索引没有新事实字段时，从原已验证投影读取，不改写旧报告或在 GET 中写数据库。缺少轨迹时明确列出未覆盖对局，不能以零值声称不存在行为。

## 平局、行动与静止的定义

终局原因与死亡方式分开：`all_eliminated` 可以来自同 Tick 爆炸，也可以来自运行故障；初始化结束、Tick 上限另列。平局特征展示未成功放弹、没有成功移动、伴随故障或爆炸死亡，特征可能重叠，不作为因果推断。

行动计数来自引擎规范化动作，包含故障后的 WAIT；成功移动与成功放弹来自事件，受阻移动指移动动作未产生位移。放弹请求不等于成功放弹。行为数据描述轨迹，不推断 Bot 意图。

“无变化 Tick”要求结算前后都没有在场炸弹，并且地图、玩家、故障计数未变；时钟和调用 fuel 不比较。它排除炸弹倒计时等待；合法移动受阻仍可能留下不变世界。统计总数、最长连续段与终局连续段可复核。检查入口只从有正长度静止结尾的平局中，按结尾长度降序 / 对局 ID 升序取最多三局，并跳到该段开始帧；不是随机代表样本。

## 当前参考赛的发现

新旧两份 300 局的下列描述统计完全一致；报告仍使用原分数：

| 事实 | 每份 300 局的结果 |
| --- | --- |
| 平局 | 94 局，全部达到 500 Tick 上限；集中在 Heuristic / Safe 的 100 局配对 |
| 有胜负 | 206 局，206 次爆炸死亡均为单一归因自杀；单一归因对手击杀与混合归因死亡为 0 |
| 故障 | 初始化、动作故障、fuel 耗尽和运行淘汰均为 0 |
| 行动 | 98,990 次规范化动作，其中 44,058 WAIT；成功移动 50,974 次、受阻移动 2,608 次 |
| 放弹 | 请求 1,350 次，成功 1,185 次 |
| 无变化片段 | 共 906 Tick，最长连续段 465 Tick；不能由此断言所有平局都静止 |

这些记录说明当前工程对手池中，非平局主要来自一方自身爆炸死亡，Heuristic / Safe 的配对区分度有限；它们不能证明真实模型会出现相同结果，也不能证明没有间接战略影响。仍有大量成功移动和放弹，不应把“平局”解释为“没有行动”。

作为故障显示检查，90 局工程赛有 30 次初始化失败、120 次动作故障（含 60 次 fuel）、24 次 trap 调用、60 次运行淘汰；12 局平局中六局是运行故障后的同时淘汰、六局是 WAIT / WAIT 达到上限。这些数字只说明功能覆盖，不参与 Baseline 或模型能力结论。

## 限制与下一版建议

地图区间只反映固定代码在所选地图上的变化，不包含模型独立生成代码的变化；不同对手池的均分不能直接比较。工程 Baseline 不代表模型样本，精选静止片段也不能估计总体频率。击杀 / 自杀按唯一爆炸 owner 归因，混合归因单列，不以该指标打破平局或改变旧成绩。

下一步先收取真实模型提交，并增加独立开发的进攻型工程对手，用新批次复核对手击杀、平局和地图分布。若仍有大量不接触对手的上限平局，可另建 ruleset 2 比较缩圈 / 可达区域压力、软墙密度或出生距离等候选；预先冻结案例，比较存活、攻击归因、偏位与确定性，不能只凭精彩画面选规则。不在 v0.2 直接修改当前成绩或将活动奖励加入名次分。

## 证据与复现

- [报告与原始轨迹核对](../../artifacts/acceptance/v0.2-development/checks/report-traces.json)：三份验证报告、690 份 Replay 哈希和独立累计结果。
- [逐字段 Chrome 检查](../../artifacts/acceptance/v0.2-development/checks/browser-report-quality.json)：42 配对、690 实际案例选择、并列排名、精确片段跳转、24 张四尺寸截图及实测对比度。
- [八条 Chrome 回归](../../artifacts/acceptance/v0.2-development/checks/browser-analysis-regression.json)、[73 项 Python 回归](../../artifacts/acceptance/v0.2-development/checks/python-analysis.log) 与 [最终受影响范围检查](../../artifacts/acceptance/v0.2-development/checks/python-analysis-final.log)。
- [源码 / 检查 / 证据包哈希](../../artifacts/acceptance/v0.2-development/checks/report-stage.json) 及 [截图与工程原始轨迹 ZIP](../../artifacts/acceptance/v0.2-development/visual/report-quality.zip)。工程批次含 WASM / 资格 / 调度 / Replay / 报告；新旧 300 局继续引用原归档，不复制或覆盖。画面均为原生 HTML / CSS / Canvas / SVG，无新增外部视觉资产。

运行于 Windows x64、Python 3.12.14、Node 24.19.0、Chrome 154.0.8037.93。新建隔离目录，不覆盖正式数据；在根目录执行：

```powershell
.\.venv\Scripts\python.exe tools\prepare_report_checks.py --data artifacts\work\report-check-new --proof artifacts\acceptance\v0.2-development\checks\report-traces.json
.\.venv\Scripts\python.exe -c "import uvicorn; from service.app import create_app; uvicorn.run(create_app('artifacts/work/report-check-new', workers=True), host='127.0.0.1', port=8800)"
```

另开终端，在 `web/` 执行 `npm.cmd run build`，设置 `$env:ARENA_BASE_URL = 'http://127.0.0.1:8800'` 后运行 `npm.cmd test`，将 `test-results/results.json` 保存为 `checks/browser-analysis-regression.json`。运行 `node tools/verify-report-quality.mjs` 逐项核对，保留根目录 Python 完整 / 受影响范围检查日志，最后运行 `tools/archive_report_evidence.py --data artifacts/work/report-check-new` 归档。完整命令与退出结果见上述源码 / 证据索引。

本轮截图由 Codex 检查新增统计的桌面 / 手机布局；不替代最终人工审美、完整可访问性或性能验收。
