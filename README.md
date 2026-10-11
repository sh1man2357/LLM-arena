# LLM Arena

本机运行的 2～8 人炸弹人 Bot 混战工具，每个 Bot 各自为战。导入 C++20 Bot，自动编译为 WASM，选择参赛 Bot 后运行并观看；运行过程自动保存为录像。直播与录像使用同一个播放器，播放速度不影响游戏结算。

## 快速启动

支持 Windows x64、Python 3.12、Node 24.19.0 / npm 11.17.0。在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup-ui.ps1
powershell -ExecutionPolicy Bypass -File .\start-arena.ps1
```

默认打开 `http://127.0.0.1:8787`，在控制台按 Enter 停止。首次启动自动编译 Random、Safe、Heuristic 三个基准 Bot，不自动开赛。

## 核心操作

1. 首页选择单文件 `.cpp`，填写名称并导入，等待“可运行”。
2. 选择 Bot 0 和 Bot 1，点击“运行”。地图 Seed 可选，留空自动生成。
3. 在观赛页按顺序播放缓冲帧，暂停、逐帧、拖动、倍速或回到最新；后台运行不改变观看进度。
4. 播到末尾显示结果；首页运行记录可随时打开历史录像。
5. 榜单汇总本机有效单局的胜 / 平 / 负和平均得分，同分并列。
6. 对局记录可搜索、筛选、重命名和批量删除。删除移入回收站并从榜单移除，可随时恢复；清空只处理筛选范围内已结束的对局。

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
```

输出到忽略目录 `artifacts/distribution/`，ZIP 根目录有 README、START_HERE 和执行入口。包不包含本机 Bot、录像、旧比赛数据或依赖安装目录。

`engine/` 是规则引擎，`sdk/` 与 `runtime/` 提供 Bot 接口和沙箱，`runner/` 与 `replay/` 提供单局与校验，`service/` 与 `web/` 提供本地应用。数据、日志、任务 ZIP、缓存和构建产物均在 Git 忽略目录生成。
