# 开发与验证

所有 Python 命令在项目根目录执行；npm 命令在 `web/` 目录执行。

## 开发服务与浏览器检查

开发服务运行 `.\.venv\Scripts\python.exe -m service --demo`；前端在 `web/` 执行 `npm run dev`。发行安装按[安装与启动](./getting-started.md)构建同源静态页面。

浏览器检查使用 `npm test`，需要本机 Chrome；`ARENA_BASE_URL` 指向专用验收实例，`ARENA_EMPTY_URL` 指向另一个新建的空实例。全量检查需这两个实例，并先通过真实工作流程提供资格 / 作业样例；最终准备与复现顺序见[版本交接](../releases/handoff-v0.2.md)。早期局部检查的范围见[页面状态记录](../records/components-and-page-states.md)。测试会改变专用数据，不对正在使用的比赛实例运行。

## 核心检查与冻结证据

已完成的工程验收证据见 [交接说明](../../artifacts/acceptance/v0.1-release/handoff.md) 和 [逐项审计](../../artifacts/acceptance/v0.1-release/audit.md)：39 项检查、300 局有效比赛、全部世界回放与 Bot 重跑，以及独立目录的另一个 300 局批次均通过。完整原始证据归档为 evidence.zip，恢复方式和 SHA-256 见交接说明。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
git log --oneline
```

检查包含规则、地图向量、真实 C++ 编译、STL/构造/堆状态、ABI、fuel trap 恢复、内存上限、watchdog、调度恢复和结果防篡改。运行时和链接决策见 [实现决策](../architecture/decisions.md)。
