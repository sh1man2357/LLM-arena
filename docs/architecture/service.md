# 本地服务与 API

FastAPI 监听本机回环地址，并提供 `web/dist/` 下的前端与任务包。默认数据目录为 `artifacts/local/`。SQLite 保存资源索引和任务状态，源码、WASM 与录像存为文件。

## 资源与执行

| 记录类型 | 内容 |
| --- | --- |
| `bot` | 游戏、名称、备注、源码和 WASM 哈希、编译状态、诊断与回收站时间 |
| `run` | 槽位与参赛快照、种子、状态、录像位置和验证结果。五子棋 Bot 对战另存换色组信息 |
| `task` | 请求去重键、固定输入和后台执行状态。一次计算可以关联两盘五子棋 |
| `baseline_reference` | 各游戏当前选定的基准 Bot ID，用于列表展示和榜单计分 |

启动脚本为每个游戏准备一个基准 Bot。构建输入和文件校验均匹配时复用快照，缺失或损坏的产物重新构建。参赛依据 Bot ID，名称可编辑。重新导入生成新 ID，历史对局保留创建时的名称、程序哈希与槽位顺序。历史记录缺少游戏 ID 时按炸弹人读取。

写请求要求 `X-Arena-Local: 1`。服务检查 Host、Origin 和跨站请求标记。导入、开赛和重赛可携带 `Idempotency-Key` 以复用相同请求的结果。SQLite 在事务中检查去重键和计算槽位；计算忙时新任务返回 HTTP 409。数据目录的工作进程锁用于防止重复启动执行器。服务启动时将遗留的未完成计算标记为中断，并保留已完成的盘次。

## API

下表路径除 `/health` 外均以 `/api/v1` 为前缀。具体请求和响应字段见运行中服务的 `/openapi.json`。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/health` | 服务状态及前端构建是否存在 |
| GET | `/status` | 计算槽位及当前操作 |
| GET、POST | `/bots` | 按游戏或回收站状态列出 Bot；上传单文件源码 |
| PATCH | `/bots/{identity}` | 更新名称或备注 |
| POST | `/bots/manage` | 按 ID 批量删除或恢复 Bot |
| GET、POST | `/matches` | 分页查询记录；创建炸弹人单局或五子棋换色组 |
| GET、PATCH | `/matches/{identity}` | 读取对局及换色组状态；修改显示标题 |
| POST | `/matches/manage` | 批量删除或恢复对局，或清理筛选范围内已结束的记录 |
| POST | `/matches/{identity}/rerun` | 根据原记录创建新对局 |
| POST | `/human-matches` | 创建空棋盘五子棋人机单盘 |
| POST | `/matches/{identity}/actions` | 提交指定轮次的人类动作 |
| GET | `/matches/{identity}/frames` | 读取直播或录像的完整帧序列或增量 |
| GET | `/leaderboard` | 按游戏读取本机榜单 |
| GET | `/events` | 通过 SSE 接收资源状态和帧更新通知 |

上传使用 multipart 字段 `file`、`name` 和 `game_id`。Bot 对战接收 `bot_ids`、`game_id`、可选的 `map_seed` 及五子棋的 `opening_mode`。炸弹人需要 2～8 个槽位，五子棋需要两个。重复 ID 表示同一快照多次参赛。64 位 Bot 种子以 16 位十六进制字符串保存。

人机创建请求接收 `bot_id` 和 `human_slot`（0 执黑，1 执白）。动作请求接收整数 `tick` 和 `action`（0～224 为落点，225 为认输）。服务在事务内检查等待轮次、行棋方与空位。最近一次相同输入可重发；过期或冲突返回 409，越界或占位返回 422。等待人类输入期间该盘持续占用计算槽位。

## 录像与恢复

`runs/<id>/frames.jsonl` 依次保存 `header`、`tick` 和 `result`。工作进程逐条写盘，按时间间隔合并帧通知；初始与终局记录单独通知。读取增长中的文件时忽略末尾未完成的行。第 0 帧是初始化后的状态，第 k+1 帧是第 k 次结算后的状态。

帧接口支持 `after_seq` 和 `attempt_id`。运行标识不匹配或游标超过末帧时返回完整序列并设置 `resync_required`。读取历史录像不执行 Bot。Bot 重赛须能取得原 WASM 并核对哈希；人机「再来一局」保留对手及执子，重新生成 Bot 种子。进入回收站的 Bot 须先恢复才能重新参赛。

删除与恢复通过记录的 `deleted_at` 字段实现。移除对局影响榜单输入，移除 Bot 隐藏其榜单行，但其历史对战仍可用于估计其他 Bot 的成绩。详见[榜单规格](../specs/benchmark.md)。
