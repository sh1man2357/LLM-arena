# LLM Arena

本机运行的模型 Bot 竞技场，支持 2～8 人炸弹人混战和双人自由五子棋。导入 C++20 Bot，自动编译为 WASM，选择参赛 Bot 后运行并观看；运行过程自动保存为录像。五子棋 Bot 对战自动打两盘换色，也支持选择黑白执子、点击落子的人机单盘。各游戏独立筛选和计分，人机对局不计入 Bot 榜单。直播与录像使用同一个播放器，播放速度不影响结算。

## 快速启动

支持 Windows x64、Python 3.12、Node 24.19.0 / npm 11.17.0。在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup-ui.ps1
powershell -ExecutionPolicy Bypass -File .\start-arena.ps1
```

默认打开 `http://127.0.0.1:8787`，在控制台按 Enter 停止。启动按当前源码准备炸弹人和五子棋各一个 Baseline 参考 BOT（实力分固定为 0），不自动开赛。

## 核心操作

1. 首页选择游戏，再选择单文件 `.cpp`，填写名称并导入，等待“可运行”。Bot 固定属于导入时选择的游戏。
2. 炸弹人选择 2～8 个 Bot；五子棋选择首盘黑白双方，自动换色打两盘。Seed 可选，留空自动生成；五子棋默认空棋盘，可选择固定三手开局库。
3. 在观赛页按顺序播放缓冲帧，暂停、逐帧、拖动、倍速或回到最新；后台运行不改变观看进度。
4. 播到末尾显示结果；首页运行记录可随时打开历史录像。
5. 榜单按游戏展示以基准 BOT 为 0 的实力分，按实力分排名、同分并列，并保留胜 / 平 / 负和平均得分。五子棋只统计两盘都有效的完整换色对战，并显示执黑、执白成绩。
6. 对局记录可搜索、筛选、重命名和批量删除。删除移入回收站并从榜单移除，可随时恢复；清空只处理筛选范围内已结束的对局。
7. 五子棋选择“人机对战”，选择对手 Bot 和你的执子。轮到你时点击空位落子或认输；刷新后可从原记录继续，结束后可回看或“再来一局”。

同一时刻只执行一个编译或对局，忙时提示稍后再试。没有收卷倒计时、批次赛程、发布或备份工作台。现有主办方数据保留，旧业务记录不自动迁移到新版列表和榜单。

## 文档与开发

| 内容 | 入口 |
| --- | --- |
| 安装与离线缓存 | [安装与启动](docs/guides/getting-started.md) |
| Bot 导入、运行、观赛与榜单 | [操作指南](docs/guides/organizing-matches.md) |
| 编译、单局和复现检查 | [CLI 指南](docs/guides/cli.md) |
| 给模型分发 Bot 开发材料 | [开发包](docs/guides/model-development.md) |
| 开发与验证 | [开发指南](docs/guides/development.md) |
| 规则、架构和简化方案 | [文档目录](docs/README.md) |

任务材料维护在 `devkit/`。生成对外开发包：

```powershell
.\.venv\Scripts\python.exe tools\build_devkit.py
.\.venv\Scripts\python.exe tools\build_devkit.py --game gomoku
```

输出到忽略目录 `artifacts/distribution/`，ZIP 根目录有 README、START_HERE 和执行入口。包不包含本机 Bot、录像、旧比赛数据或依赖安装目录。

五子棋开发包输出为 `artifacts/distribution/llm-arena-gomoku-devkit.zip`，使用独立任务书与 SDK，根目录仍有执行入口。规则与协议见[五子棋规格](docs/specs/gomoku.md)。

`engine/` 和 `gomoku/` 是规则引擎，`sdk/` 与 `runtime/` 提供 Bot 接口和沙箱，`runner/` 与 `replay/` 提供运行与校验，`service/` 与 `web/` 提供本地应用。数据、日志、任务 ZIP、缓存和构建产物均在 Git 忽略目录生成。
