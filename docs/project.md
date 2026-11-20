# 项目概览

LLM Arena 在本机编译和运行 C++20 Bot，支持多人炸弹人、双人自由五子棋和五子棋人机对战。主办方在应用中分发任务包、导入源码、选择参赛程序并查看录像及榜单。外部模型在独立开发环境中完成编程和练习。

## 运行单位

- **Bot 快照**对应一次源码导入，包括所属游戏、源码和编译结果。重新导入产生新 ID。名称与备注可编辑，已有对局保存创建时的参赛名称。
- **对局记录**保存一局炸弹人或一盘五子棋。五子棋 Bot 对战在一个计算任务中生成两条关联记录，人机对战生成一条。
- **榜单**按游戏统计本机有效 Bot 对战。每个游戏以当前基准 Bot 的实力分为 0，计分条件见[榜单规格](specs/benchmark.md)。

## 数据位置

| 路径 | 内容 |
| --- | --- |
| `artifacts/local/` | 默认应用数据，包括 SQLite 数据库、Bot 源码与 WASM、运行记录和服务日志。可通过启动参数 `-Data` 指定其他目录 |
| `artifacts/work/` | 命令行示例、练习、测试实例及临时构建目录 |
| `artifacts/distribution/` | 命令行生成的公开任务包及 SHA-256 文件 |
| `web/public/devkits/`、`web/dist/devkits/` | 前端构建准备的 ZIP 及随应用发布的副本 |
| `.venv/`、`.tools/`、`web/node_modules/` | Python 环境、编译工具和前端依赖 |

上述路径均由 Git 忽略。源码模块见[核心架构](architecture/overview.md)，安装和操作见[安装指南](guides/getting-started.md)及[操作指南](guides/organizing-matches.md)。
