# LLM Arena

在本机运行的双人炸弹人 AI 竞技场。不同模型在统一的 60 分钟内编写 C++20 Bot，源码冻结后编译成 WASM，在相同计算预算和内存限制下比赛。

支持源码收卷与资格检查、单局与批量换边、真实直播与逐帧回放、成绩分析、公开导出和本机数据恢复。正式比赛执行冻结程序，播放速度不影响结算。

## 快速启动

支持 Windows x64、Python 3.12、Node 24.19.0 / npm 11.17.0。在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup-ui.ps1
powershell -ExecutionPolicy Bypass -File .\start-arena.ps1
```

默认打开 `http://127.0.0.1:8787`，在启动控制台按 Enter 停止。首次启动从当前源码编译 Random、Safe、Heuristic 并生成工程参考赛，供观赛和操作练习。参考赛使用公开地图，不代表真实模型参赛成绩。

## 使用入口

| 想做什么 | 入口 |
| --- | --- |
| 安装、启动与离线缓存 | [安装与启动](docs/guides/getting-started.md) |
| 收卷、开赛、观赛与发布 | [组织比赛](docs/guides/organizing-matches.md) |
| 给 AI 分发任务 | [模型开发包](docs/guides/model-development.md) |
| 编译、批量换边与复现 | [CLI 指南](docs/guides/cli.md) |
| 开发与运行检查 | [开发指南](docs/guides/development.md) |
| 了解规则与项目结构 | [文档目录](docs/README.md) |

任务材料统一维护在 `devkit/`。生成对外任务包：

```powershell
.\.venv\Scripts\python.exe tools\build_devkit.py
```

将 `artifacts/distribution/llm-arena-devkit.zip` 发给每个参赛 AI 即可；包内包含执行指令、任务书、SDK、公开地图、基准 Bot 和练习工具。

## 项目目录

`engine/` 是规则引擎，`sdk/` 与 `runtime/` 提供 Bot 接口和沙箱，`runner/` 与 `replay/` 负责比赛与复现，`service/` 与 `web/` 提供本机应用。任务材料在 `devkit/`，使用和架构文档在 `docs/`。

依赖、任务 ZIP、比赛数据、备份、测试日志和构建结果均在 Git 忽略目录中生成。仓库维护当前源码、配置、测试和文档。多人正式赛制、道具、缩圈、长期 Rating、云端账号与自动模型 API 编排不在当前范围内。
