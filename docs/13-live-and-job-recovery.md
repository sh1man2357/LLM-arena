# v0.2 直播断连与作业恢复

本文说明实际恢复行为及验证范围。完整私有目录迁移见 [数据恢复说明](./12-data-recovery.md)，整版完成标准见 [交付清单](../DELIVERY_v0.2.md)。首个验收平台为 Windows x64。

## 观众断连和回看

播放器只接收已经持久写入的完整状态帧。HTTP 帧响应包含 `attempt_id`、`last_seq` 和 `resync_required`；查询携带最后已确认序号及尝试 ID。尝试改变或序号超出当前记录时，服务返回完整快照，不能将两个尝试拼成一局。

浏览器检查帧序号、Tick、末尾水位及重复帧内容。相同重复帧只保留一次；缺帧、冲突或尾帧遗漏触发完整快照恢复。恢复后仍须检查从初始帧开始的连续序列，不用动画补造缺失状态。

临时断连保留最后确认棋盘及本地回看位置，展示恢复提示；服务重新连接后重新读取持久状态。暂停、播放和倍速只改变当前浏览器位置，服务器继续计算，其他观众可独立跟随最新。直播数据更新不会反复重置播放计时器，0.25 倍速回看仍能推进。

首次 SSE 订阅没有显式游标时，从订阅时的持久事件水位开始，onopen 重新读取当前资源；不重放所有历史通知来反复取消页面请求。重连的 `Last-Event-ID` 与显式 `after` 取较大的非负值并有序补齐，显式 `after=0` 仍支持从头读取。实际旧数据首连、字段过滤和断连 / 进程恢复的补验收见 [性能与响应验证](./16-performance.md)。

出现新执行尝试时，已有回看的观众回到新尝试初始帧，停止播放 / 自动跟随并显示提示。当前单局完成后读取完整终局快照；只有未经登记的临时 result 行时，不宣布正式胜者。

## 主办方停止、重启和重试

| 操作 / 故障 | 实际行为 | 后续操作 |
| --- | --- | --- |
| 批次“当前局后停止” | 当前单局完整结束后停止新调度，已完成证据保留；批次保持 incomplete | 在工作台恢复原作业 |
| 服务退出或进程中断 | 自有 worker 停止；重启将遗留运行状态和未结束尝试标为 interrupted | 检查日志和冻结输入后手动恢复 |
| worker 崩溃 | 作业失败，未提交完整终局的单局不产生正式胜者 | 工作台重试同一冻结输入 |
| worker 启动失败 | 当前尝试记录失败及结束时间，不遗留“运行中”历史 | 检查诊断后重试 |
| 单局恢复 | 使用同一源码 / WASM、规则、地图与 Bot Seed，从 Tick 0 重新运行 | 新尝试有独立记录与日志 |
| 批次恢复 | 校验并复用已完成对局，只重做未完成或失败的局 | 调度和 match_id 不变，不重复计分 |

工作台可展开“执行尝试与旧日志”，查看每次状态、开始 / 结束时间以及各次原日志。日志读取需要主办方凭据，尝试 ID 必须属于指定作业，不允许通过参数读取任意路径。

Windows 的 worker 及其后代归属一个非继承的 Job Object，最后一个句柄关闭时终止该进程组。worker 先等待父进程完成归属再开始写入，避免启动窗口中产生无人管理的运行。机制依据 [Windows Job Objects 官方说明](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)；本项目的实际退出行为由下述父进程故障检查验证。此阶段不宣称其他操作系统的强制退出具有同样保障。

## 两个提交边界

作业终态与该次尝试的终态 / 结束时间在同一元数据更新中提交，随后才能接受恢复请求。旧 worker 的退出状态只能补充原尝试，不能把已经停止的尝试改成“排队”，也不能覆盖新作业状态。

批次可能在原始 Replay 和结果已经落盘、观赛索引尚未登记时中断。恢复校验缓存后，补齐缺失或中断的单局索引，保留原尝试身份及原文件哈希；不能因存在一条中断索引就跳过登记。完整报告与每局观赛状态必须一致。

失败局重试前归档旧结果与原 Replay；有效缓存不重写。失败、缺失和未完成对局不进入正式排名，不完整批次不能发布完整成绩。

## 验证证据与复现

实际检查包括两份最终冻结的 C++ Wait 提交、500 Tick 单局、两个浏览器的独立位置、传输缺帧 / 重复帧、临时离线、活动慢速 / 快速播放、仅终止主进程、单独终止 worker，以及四案例换边八局的停止 / 重启 / 恢复。

| 证据 | 覆盖范围 |
| --- | --- |
| [真实进程与浏览器证明](../artifacts/acceptance/v0.2-development/checks/live-process-recovery.json) | 缺帧恢复、去重、离线计算继续、播放独立、新尝试、旧记录、父进程退出及批次唯一计分 |
| [Python 完整回归](../artifacts/acceptance/v0.2-development/checks/python-live-recovery.json) | 启动失败、终态竞态、缓存登记窗口、失败证据归档，以及既有规则 / SDK / 服务 / 恢复检查 |
| [Chrome 常规回归](../artifacts/acceptance/v0.2-development/checks/browser-live-recovery.json) | 收卷、编译、真实直播、历史回放、换边批次、发布和私有备份等八条流程 |
| [阶段文件与协议记录](../artifacts/acceptance/v0.2-development/checks/live-stage.json) | 本阶段源码 / 证据哈希、运行环境及帧协议检查的命令、输出和退出状态 |

在已安装锁定依赖、已构建前端的 Windows 环境中，项目根目录可执行以下专门验证。输出目录先创建，数据目录必须是新的；8797 须未被其他实例占用。

```powershell
New-Item -ItemType Directory -Force artifacts\acceptance\v0.2-live-check
node web\tools\verify-live-recovery.mjs .venv\Scripts\python.exe artifacts\work\v0.2-live-check artifacts\acceptance\v0.2-live-check\live-process-recovery.json 8797
```

脚本只操作自己启动的服务 / worker，最终停止自有实例。原始源码、Seed、数据库、日志及失败尝试位于被 Git 忽略的本地工作目录；验收材料保留检查命令、环境、诊断和结果摘要，不分发私有比赛输入或访问凭据。

前端合并协议检查在 `web/` 执行 `npm run test:protocol`。完整 Python 检查在根目录执行 `python tools/record_checks.py --output artifacts/acceptance/v0.2-live-check/python.json`；常规浏览器流程在独立 `--demo` 实例上执行 `npm test`，使用 `ARENA_BASE_URL` 指定端口。

此阶段验证运行 / 传输和数据完整性，不替代初始化 / 动作故障的全部画面走查、最终审美评审、可访问性或性能测量。单局从冻结输入重跑，不保存 WASM 内存检查点；恢复由主办方显式启动。
