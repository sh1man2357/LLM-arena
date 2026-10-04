# 实现决策记录

## 2026-10-05：工程栈与本地版本管理

- 宿主采用 Python 3.12，规则引擎、地图、调度、报告和 Replay 使用标准库，WASM 通过 Wasmtime Python 包调用。
- Windows x64 为首个验收平台；Wasmtime 49.0.0、WASI SDK 33.0 的官方 Windows 包固定版本和 SHA-256，见 configs/toolchain.json 与 requirements.lock。
- WASI SDK 只用于编译。正式 Bot 禁止 WASI 和其他宿主导入；使用 SDK 包装器及统一链接参数生成无导入模块。
- 工具安装在 .venv 与 .tools 中，不修改系统 PATH。工具和批量 Replay 不进入源码 Git；验收清单、日志摘要和报告进入 Git，并提供重建方式。
- 创建 main 分支。设计文档先提交，再按可验证阶段提交代码、检查和对应状态记录；不提交未经检查的阶段完成声明。

## 2026-10-05：SDK 与运行时可行性验证

- Wasmtime 实测支持 fuel trap 后再次调用同一实例，并保留 trap 前内存写入；WAT 和真实 C++ 检查分别覆盖这一行为。
- 固定 C++20、O2、禁异常与 RTTI、1 MiB 栈、64 MiB 线性内存；完整参数和编译哈希由编译入口记录。
- 链接压缩重定位，确保标准库间接调用符合禁用 reference-types 的模块验证。libc++ 异常诊断和分配失败在模块内 trap；SDK 提供 malloc/free 支撑的 new/delete，不依赖宿主 I/O。STL、静态构造、持久堆状态和完整 64 位 Seed 已验证。
- 仅允许 core WASM、bulk-memory 和 multi-value，禁用 SIMD、线程、GC、函数引用、异常、tail-call、stack-switching、memory64、多内存、组件及其 async/map/implements 子特性。Wasmtime 49 Python 高层 API 缺失三个组件 async 开关，因此调用其固定版本 C-API 绑定关闭它们。
- 附加资源资格约束：源码最多 1 MiB、模块最多 8 MiB、table 最多 65,536 元素且最多一个；这些限制与内存预算一起对所有参赛者生效。宿主 WASM 栈上限 1 MiB，watchdog 约 20 秒，只判基础设施故障。
- 公开开发地图 10 张、工程验收地图 50 张已生成并落盘，二者用途分开；工程验收清单是公开数据，不作为未见模型正式测试集。

## 2026-10-05：预算与工程交接验收

- 最终源码阶段提交为 69bdca4；工程源码清单哈希为 `0ac6bbe05e70d4d7f155853755a0ba67c109a592dc1240eabc631dd6ebc7f69e`，由最终运行 manifest 保存。
- 39 项检查通过；66 次公开极端观察最高消耗 196,333 fuel；300 局批次最高单 Tick 消耗 247,103 fuel。无 Baseline fuel 故障、初始化失败、运行淘汰或基础设施失败，保留 1,000,000 / 10,000,000 预算。
- 全部 300 局通过世界回放与真实 Bot 重跑；断点恢复不改变结果文件哈希。独立目录重新准备依赖、编译并运行另外 300 局，12 条交接命令全部成功，Baseline WASM 哈希相同。
- Heuristic 对 Safe 的 100 局有 94 局平局，Heuristic 0 胜 6 负。当前规则允许长期存活平局，这一事实保留在报告中；不事后改变规则或虚构长期 Rating。
- 已检查完整的单局文本与连锁示例：Tick 14 / 17 放弹，Tick 18 连锁引爆第二枚原定 Tick 21 到期的炸弹，双方同 Tick 死亡，各 0.5 分。

工具源：[WASI SDK 官方发布](https://github.com/WebAssembly/wasi-sdk/releases/tag/wasi-sdk-33)、[Wasmtime Python 官方 API](https://bytecodealliance.github.io/wasmtime-py/)。版本和资格行为同时以本地锁文件、编译元数据与实测为依据。

## 2026-10-05：模型任务改为 60 分钟限时交卷

- 按用户要求，模型收到任务后 60 分钟内提交，可提前交卷；提交后冻结源码，不额外要求 token 预算、修改轮数或测试次数配置。
- 时限内自主使用已提供的工具与公开材料；默认当前对话交完整源码，只有无法确定交付位置时询问“交到哪里”。
- 时间、实际模型设置、开发过程和用量由主办方记录，不作为模型开工前的配置问卷。任务以根目录 MODEL_TASK.md 为准。

## 2026-10-05：v0.2 观赛产品规划

以下是实现方向，尚未安装依赖、开发或验收，不属于 v0.1 已有能力。

- 用户明确要求将功能完整、交互优秀、审美统一的观赛前端列为 v0.2 核心交付；同时规划提交与资格、比赛大厅 / 调度、批次分析、本地服务和可审计发布。
- 产品沿用双人 v0.1 规则、地图、SDK、fuel 和名次分，不为减少平局改旧成绩。平局分析纳入本版，玩法升级、长期 Rating 与多人赛制后置。
- 视觉基准为“竞技转播台”，具体 tokens、响应式、动效、完整状态和走查门槛统一在 [前端规范](./09-v0.2-frontend.md)。
- 实现选择 React / TypeScript / Vite、Canvas 2D、FastAPI、HTTP / SSE、独立 worker 与 SQLite；确切依赖版本在实现时锁定，技术依据和边界见 [服务架构](./10-v0.2-service.md)。
- 当前 Replay 在赛后写入，真实直播需要增量持久输出；这是新增工程工作，不宣称现有系统已经实时推流。
- 正式观赛会披露地图，只在参赛池收卷关闭后开放；旧证据原样保留，新源码产生新运行清单。
- 根目录 [DELIVERY_v0.2.md](../DELIVERY_v0.2.md) 独立定义新验收项，v0.1 已勾选清单继续只代表历史工程完成。
