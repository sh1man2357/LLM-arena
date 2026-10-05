# v0.2 公开回放与私有备份恢复

公开回放用于分发观赛资料，完整私有备份用于迁移主办方实例。两者入口均已实现并通过阶段检查；整版状态仍以 [交付清单](../DELIVERY_v0.2.md) 为准。

## 公开回放再导入

在观赛页下载“公开 Replay”，再到工作台选择“上传 Replay”，可上传 `.json` 公开投影或 `.jsonl` 原始 Replay，文件最大 16 MiB。公开投影支持版本 1 / 2，须包含初始帧、完整已确认帧和终局结果；直播中途的部分投影不能作为完整历史局导入。

服务不相信文件内的 `verified` 标记，会按冻结 ruleset 1 重新结算动作、世界状态、事件、爆炸几何和结果。修改坐标、帧顺序、连锁覆盖或名次分会被拒绝。基础设施失败的完整诊断轨迹可以导入，但没有正式胜者或排名。

公开文件缺少地图 / Bot Seed 和完整冻结输入，只能校验所记录的世界轨迹，不能复现地图生成或重跑 Bot，也不能作为正式批次输入。界面明确显示这个限制。导入文件的 `source_sha256` 是本次上传字节的哈希；`origin_source_sha256` 是文件声称关联的原始证据哈希，标记为 `unverified_claim`，不单独证明来源真实性。核对原始来源应使用主办方固定发布清单和对应原始证据。

## 创建完整私有备份

在主办方工作台的“备份与新目录恢复”中选择“创建完整私有备份”。备份进入持久作业队列，等待当前计算完成，再固定元数据和文件。完成后显示文件数、记录数、大小与 SHA-256，可下载 ZIP。

备份包含收卷时间和最终源码、已注册 WASM、作业冻结输入和尝试记录、比赛 / 批次原始证据、固定发布副本、披露记录及事件序列。已注册在数据目录之外的证据也会纳入归档并生成受控路径映射。备份不包含旧访问凭据、SQLite 文件、worker 锁或此前生成的备份；备份操作本身不作为待恢复的比赛作业。

这是私有资料，包含源码和隐藏 Seed，不使用公开报告的字段过滤；工作台标明用途，列表和下载均要求主办方凭据。创建期间观赛读取仍可继续，修改数据的请求返回 423，并提示等待备份完成。实际归档字节再次绑定冻结元数据中的哈希；初次校验后被改写的源码不能形成完整备份，文件增长也受总量限制。

服务停止后，也可在项目根目录离线创建：

```powershell
.\.venv\Scripts\python.exe -m service.backup create --data artifacts/local --output artifacts/work/private-backup.zip
```

离线命令需要独占该数据目录；仍在运行的服务拥有 worker 锁时会拒绝创建。输出文件必须不存在，不覆盖此前归档。

## 恢复到新目录

先准备当前项目的依赖和发行前端，见 [安装说明](../README.md)。下载私有 ZIP，并保留工作台显示的 SHA-256；以下命令中的哈希来自该下载记录，不是额外开发协议配置。

```powershell
.\.venv\Scripts\python.exe -m service.backup restore artifacts/work/private-backup.zip --destination artifacts/local-restored --sha256 <备份记录中的SHA-256>
powershell -ExecutionPolicy Bypass -File .\start-arena.ps1 -Data artifacts/local-restored -Port 8791
```

`--destination` 必须是尚不存在的新目录。命令先在同卷临时目录校验格式、路径、文件大小 / 哈希、冻结源码 / WASM、Replay、报告和发布副本，再整体生成目标目录；失败不覆盖现有实例，也不留下可启动的半份恢复目录。`--sha256` 对照外部保存的归档哈希，建议始终提供；仅有归档内部哈希不能证明归档来源。

恢复保留原始文件字节、参赛身份、收卷截止与冻结时间、首次关闭 / 发布时间和公开副本哈希。仅已登记的操作路径重定向到新目录，原始日志 / manifest 中的历史路径文本不改写。回放投影属于缓存，恢复时从原始证据重新生成。

新实例生成新的主办方凭据；旧浏览器 cookie 不能沿用。进入新实例工作台重新建立本机主办方会话。备份中的 queued、running、stop_requested 和 compiling 转为 interrupted，不自动执行；核对作业输入和旧诊断后，从工作台“恢复 / 重试”继续。已完成批次与固定发布不重新计分。

恢复后按以下顺序核对：

1. 大厅中的批次 / 对局和参赛者身份符合预期，历史对局逐帧与终局可观看。
2. 工作台中的收卷时间、冻结源码 / WASM 哈希及资格 / 失败状态保留。
3. 固定发布清单和报告可下载，SHA-256 与恢复前一致。
4. 未完成作业标为中断，确认输入后再显式恢复；后续新提交另建收卷记录。

## 格式、限制和版本

私有 ZIP 使用 `arena-private-backup` schema 1，`snapshot.json` 保存元数据、显式文件引用、事件和逐文件哈希索引。上限为 50,000 个文件、2 GiB 原始文件总量、单文件 / 元数据各 64 MiB。恢复只接受未加密的 Stored / Deflate ZIP，拒绝路径逃逸、大小写重复、Windows 设备名、文件 / 目录冲突、符号链接及导入访问凭据。

同一 v0.2 数据 schema 可迁移；不承诺跨未来未知 schema 自动升级。备份仅复制已注册外部产物和数据根目录的文件，不复制工具链 / 前端程序；新实例使用当前项目依赖，精确重跑旧比赛仍须保留其冻结版本和环境。数据超限、冻结文件被修改或注册产物缺失时，创建备份会失败并保留作业诊断。

## 本轮验收证据

- [完整 Python 检查](../artifacts/acceptance/v0.2-development/checks/python-recovery.log)：64 项通过；覆盖篡改 / 路径拒绝、现有目录保护、凭据轮换、缓存重建、排队编译转中断并手动完成真实 C++ 编译。
- [浏览器流程](../artifacts/acceptance/v0.2-development/checks/browser-recovery.json)：8 条 Chrome 流程通过；包括收卷 → 编译 → 真实单局直播 / 回放 → 隐藏批次换边 → 关闭收卷 / 发布 → 下载报告，以及公开回放再导入 / 私有备份下载。
- [最终备份边界检查](../artifacts/acceptance/v0.2-development/checks/browser-backup-boundaries.json)：针对补强后的代码，真实备份运行期间健康 / 回放读取成功，收卷修改返回 423，完成后下载归档哈希一致；归档下载使用独立文件名，保留此前恢复证据。
- [新目录恢复核对](../artifacts/acceptance/v0.2-development/checks/recovery.json)：同一下载归档包含 2,843 个文件、630 条元数据；2,238 个原始文件哈希一致，605 个投影缓存重建，221 条事件保持顺序。验证工具为 `tools/verify_recovery.py`。
- [恢复实例观赛检查](../artifacts/acceptance/v0.2-development/checks/browser-recovery-restored.json)：实际 Chrome 核对同一冻结提交、500 Tick 单局、已发布换边批次、精确帧剪贴板链接、PNG / Replay / 报告下载和旧凭据拒绝。验证工具为 `web/tools/verify-recovery.mjs`。

私有 ZIP 和恢复数据库保存在本地忽略目录，不作为公开源码或验收证明内容提交。本轮不证明实际进程崩溃恢复、直播断连 / attempt 切换、最终视觉与性能均已通过；这些仍单独验收。
