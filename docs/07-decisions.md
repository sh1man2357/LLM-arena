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

1,000,000 fuel 的正式校准仍待完整批次峰值和极端状态检查。所有组件版本与参数在 M4 前冻结。
