# 文档目录

从[项目概览](./project.md)了解用途，从[安装与启动](./guides/getting-started.md)开始使用。文档按用途分类，文件名描述内容，不再使用连续编号。

## 使用指南

| 文档 | 用途 |
| --- | --- |
| [安装与启动](./guides/getting-started.md) | 浏览器应用、CLI 环境、启动与停止 |
| [组织比赛与观赛](./guides/organizing-matches.md) | 收卷、资格、开赛、观赛、导入与发布 |
| [命令行使用](./guides/cli.md) | 编译、单局、批量换边、报告与复现 |
| [模型开发竞技场](./guides/model-development.md) | 统一公开开发包、三基准和练习反馈 |
| [数据恢复](./guides/data-recovery.md) | 公开回放导入、私有备份、新目录恢复 |
| [开发与验证](./guides/development.md) | 开发服务、浏览器检查、核心检查 |
| [模型任务书](../MODEL_TASK.md) | 可直接分发的 60 分钟 Bot 开发任务 |

## 规则与接口规格

这些文档定义比赛行为。v0.2 沿用 v0.1 对局规则，产品版本与规则版本分别管理。

| 文档 | 用途 |
| --- | --- |
| [游戏规则](./specs/rules.md) | 同时移动、爆炸、死亡与终局 |
| [Bot SDK](./specs/bot-sdk.md) | C++20 接口、WASM ABI、观察与资源限制 |
| [地图与随机性](./specs/maps-and-randomness.md) | Seed、地图生成、出生位与复现 |
| [评测与评分](./specs/benchmark.md) | 开发协议、冻结、换边、名次分与统计 |

## 架构与产品设计

| 文档 | 用途 |
| --- | --- |
| [项目概览](./project.md) | 目标、版本边界、默认参数和目录职责 |
| [架构总览](./architecture/overview.md) | 模块边界、Replay 契约、确定性校验 |
| [本地服务](./architecture/service.md) | API、SQLite 索引、worker、作业、发布 |
| [实现决策历史](./architecture/decisions.md) | 工具链选择、资源校准及阶段决策 |
| [v0.2 产品规划](./design/v0.2-plan.md) | 版本目标、功能取舍与历史实施安排 |
| [前端规范](./design/frontend.md) | 页面、视觉系统、播放器、响应式与可访问性 |

## 版本交付与交接

**当前完成状态只在版本交付清单汇总。** 使用指南说明操作，规格说明契约，阶段记录保留当时的证据与限制。

| 文档 | 用途 |
| --- | --- |
| [v0.2 交付清单](./releases/v0.2.md) | 当前版本范围、29 项逐项验收与证据 |
| [v0.2 交接](./releases/handoff-v0.2.md) | 完整使用路径、复现命令、证据索引与限制 |
| [v0.1 历史交付](./releases/v0.1.md) | 已冻结的 CLI 交付范围与验收 |

## 验收记录

这些是按主题保留的检查和评审记录。正文中的“仍待完成”指记录时点，后续结果从版本交付清单查询。

| 文档 | 证据范围 |
| --- | --- |
| [视觉迭代](./records/design-review.md) | 页面走查、发现的问题与修正 |
| [直播与作业恢复](./records/live-and-job-recovery.md) | 断连补帧、尝试切换、进程中断与重试 |
| [观赛质量](./records/viewer-quality.md) | 规则画面、长名称、拖动、触控与全屏 |
| [成绩与行为分析](./records/results-analysis.md) | 报告核对、平局、故障与静止片段 |
| [性能](./records/performance.md) | 首帧、定位、播放与后台响应 |
| [组件与页面状态](./records/components-and-page-states.md) | 共用组件、真实页面与局部读取恢复 |
| [收卷与冻结](./records/receipts-and-freezing.md) | 截止、源码上传、私有档案与未完成排名 |
| [最终工程验收](./records/final-engineering-acceptance.md) | 完整状态、可访问性、边界与最终回归 |
| [最终视觉确认](./records/final-visual-review.md) | 实际画面、逐页结论与负责人确认 |

文档维护约定、旧路径查询及冻结证据说明见[维护说明](./maintenance.md)。
