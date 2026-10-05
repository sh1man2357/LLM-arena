# LLM Arena

在本机运行的双人炸弹人 AI 竞技场。不同模型在统一条件下编写 C++20 Bot，源码冻结后编译成 WASM，以相同计算预算和内存限制比赛。比赛过程中不调用模型。

支持源码收卷与资格检查、单局与批量换边、真实直播与逐帧回放、成绩分析、公开导出和私有备份恢复。播放速度不影响比赛结算，同一套冻结输入可以重跑验证。

## 快速启动

支持 Windows x64、Python 3.12、Node 24.19.0 / npm 11.17.0。在项目根目录执行：

```powershell
# 首次安装依赖并构建前端
powershell -ExecutionPolicy Bypass -File tools\setup-ui.ps1
# 启动本机应用
powershell -ExecutionPolicy Bypass -File .\start-arena.ps1
```

默认打开 `http://127.0.0.1:8787`，在启动控制台按 Enter 停止。环境选择、离线缓存和端口参数见[安装与启动](./docs/guides/getting-started.md)。

## 从这里开始

| 想做什么 | 阅读入口 |
| --- | --- |
| 了解项目与代码结构 | [项目概览](./docs/project.md)、[架构](./docs/architecture/overview.md) |
| 收卷、开赛、观赛和发布 | [组织比赛与观赛](./docs/guides/organizing-matches.md) |
| 使用命令行编译、比赛和校验 | [CLI 指南](./docs/guides/cli.md) |
| 向模型分发开发任务 | [MODEL_TASK.md](./MODEL_TASK.md)，统一 60 分钟交卷 |
| 给模型提供竞技场和基准 Bot | [模型开发竞技场](./docs/guides/model-development.md) |
| 开发或运行检查 | [开发与验证](./docs/guides/development.md) |
| 查找规则、设计或验收证据 | [文档目录](./docs/README.md) |

## 版本与范围

v0.2 已完成 29 / 29 项验收，包括最终人工视觉确认；逐项状态以[版本交付清单](./docs/releases/v0.2.md)为准，复现与证据索引见[版本交接](./docs/releases/handoff-v0.2.md)。v0.1 CLI 的历史交付单独保留。

当前交付为 Windows 本地应用，参考 Bot 为 Random、Safe、Heuristic。真实外部模型参赛成绩需实际收卷后产生；长期 Rating、多人正式赛制、道具、缩圈、云端账号和自动模型提供方集成属于后续范围。
