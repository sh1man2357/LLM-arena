# 请执行本包中的 Bot 开发任务

给收到附件的编程代理：准备环境，阅读 MODEL_TASK.md，编写并交付一个完整的 bot.cpp，并在最终回复中用中文梳理编写 Bot 的全过程。请执行任务，不只介绍包内容。

你的 Bot 将代表你，与其他顶级前沿模型独立开发的 Bot 同台竞技。同一竞技项目中，其他参赛模型收到的任务提示词与你完全相同。请交付你能实现的最强参赛程序；算法、策略与开发过程由你自主决定。Baseline 是一个普通的参考 Bot，供本地练习和计分使用，基准成绩仅供参考。

## 执行流程

1. 在你可写的位置解压到新的独立目录；已解压时以本文件所在目录为根目录。不要使用其他模型或主办方的数据目录。
2. 在包根目录运行环境准备与真实单局检查：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-devkit.ps1
```

3. 启动脚本默认用模板完成三人混战检查；可添加 `-Players 2` 或 `-Players 8` 指定人数。成功后阅读 MODEL_TASK.md，用固定 SDK 生成能适应 2～8 人各自为战的根目录 bot.cpp。遍历实际 `player_count`，不要假设只有一个对手。没有默认开发倒计时；可以自主迭代、编译和练习。
4. 可选练习，每轮使用新的输出目录：

```powershell
.\.venv\Scripts\python.exe tools\practice.py --source bot.cpp --output artifacts/work/practice-01
.\.venv\Scripts\python.exe tools\practice.py --source bot.cpp --players 3 --maps 1 --output artifacts/work/practice-3p
.\.venv\Scripts\python.exe tools\practice.py --source bot.cpp --players 8 --opponent baseline --maps 1 --output artifacts/work/practice-8p
```

5. 交付完整 bot.cpp，并在最终回复中另附中文开发流程总结，具体格式见 MODEL_TASK.md 的提交要求。总结与源码分开，只描述实际完成的工作；原始检查结果保留在练习输出中，也不要声称通过了未执行的测试。

SDK、十张公开地图、一个参考 Bot 的源码与 WASM、真实规则引擎和练习工具都在包中。最终 Bot 必须是单文件；复用辅助源码时合并到 bot.cpp，不依赖额外私有文件。

练习默认双人换边；`--players N` 使用候选 Bot 和 N−1 个所选基准的独立实例，在每张地图轮换全部 N 个出生位，所有槽位各自为战。平均分按个人名次计算。局内积分为回合结算存活 +1、击杀 +100，同分并列。SDK 与二进制协议为版本 2；旧 WASM 兼容参赛但看不到积分，建议重新编译。本包清单版本为 5，记录支持人数与地图生成器版本。

本包适用于 Windows x64 编程代理，需要 Python 3.12。首次安装需要联网下载锁定依赖和约 625 MiB 的 WASI 编译器；可用 -CompilerArchive 或 -WheelDirectory 复用缓存，不修改系统 PATH。

只收到任务书文字而无法执行工具时，按内嵌 SDK 完成源码即可。使用者在本地应用首页导入你的 bot.cpp，应用自动编译检查后运行对战。
