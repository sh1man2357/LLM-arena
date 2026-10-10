# Bot SDK 与运行契约

C++20 → WebAssembly 已实现：WASI SDK 33.0 / Clang 22.1.0 编译，Wasmtime 49.0.0 执行。版本与验证依据见[架构总览](../architecture/overview.md)。

## 面向模型的接口

SDK 提供值类型和解码器。模型只实现以下两个函数：

```cpp
namespace bot {
void init(uint64_t seed);
Action tick(const GameState& state);
}
```

`Action` 是规则文档中的六个枚举值。`GameState` 包含当前 Tick、地图尺寸、自己 ID、全部地形、玩家和炸弹，以及最大 Tick、炸弹延迟、容量和范围。炸弹公开 owner、坐标、范围和到期 Tick。玩家公开 ID、坐标和存活状态；死亡者保留死亡前坐标，但不占格。

Bot 可以保存静态变量、堆内存和自己的 RNG 状态。每局使用一个全新的实例，先调用一次 init，然后仅在存活 Tick 调用 tick；不同比赛之间不保存状态。

世界信息完全公开，但不提供对手源码、模型名称、对手内存、对手本 Tick 动作、隐藏地图 Seed、宿主时间或评测结果。

`GameState` 只在当前调用期间有效。SDK 不允许 Bot 修改竞技场状态；即使 Bot 修改自己的输入缓冲区，也只改变自己实例中的内存。

## WASM ABI

C++ 引用、STL 对象和编译器结构体布局不作为跨边界协议。固定 SDK 包装器负责二进制状态解码和枚举返回。

模块使用 wasm32，必须导出：

```text
memory                                  linear memory
arena_input_ptr() -> i32                 64 KiB 输入缓冲区的起始偏移
arena_init(seed_lo: i32, seed_hi: i32)    无返回值
arena_tick(state_ptr: i32, state_len: i32) -> i32
```

SDK 合成种子为 `uint64_t(seed_lo) | (uint64_t(seed_hi) << 32)`，参数按无符号位模式解释。模型不必直接编写上述导出函数。

统一编译禁用异常和 RTTI。静态构造在 arena_init 中执行；常用 STL 容器可用，普通 new 分配失败在模块内 trap，nothrow new 返回 null。标准库终止诊断直接 trap，不提供输出、文件或时钟功能。

arena_init 完成后，宿主调用 arena_input_ptr，检查缓冲区完整落在已分配内存内；该偏移在整局固定。每 Tick 将观察写入此区域，再调用 arena_tick。SDK 保留整个 64 KiB 区域，Bot 分配器和内部状态不得占用它。

模块不得导入任何宿主函数、文件、网络、时钟、线程、随机源或 WASI。拒绝共享内存、memory64、多内存和 start section。线性内存必须声明 maximum，且最多 1024 页，每页 64 KiB。SDK 的默认栈建议为 1 MiB，计入总线性内存。

只启用冻结清单中声明的 WASM 特性。比赛行为不得依赖未定义的 C++ 行为或未固定的浮点 NaN 位模式；游戏协议和官方 Baseline 使用整数逻辑。

实现附加资格限制为源码最多 1 MiB、WASM 最多 8 MiB、最多一个 table 且最多 65,536 元素；宿主 WASM 栈上限 1 MiB。仅允许 core WASM、bulk-memory 和 multi-value，具体禁用项由运行清单记录。

## 状态二进制格式

协议版本为 `1`，所有字段均为无符号 32 位小端整数，地形数组例外；不能直接复制宿主结构体。顺序为：48 字节头 → 地形字节 → 玩家记录 → 炸弹记录。数组之间不添加对齐填充。

| 头偏移 | 字段 |
| --- | --- |
| 0 | protocol_version |
| 4 | tick |
| 8 | width |
| 12 | height |
| 16 | self_id |
| 20 | player_count，包含已死亡玩家 |
| 24 | bomb_count |
| 28 | grid_byte_count，必须等于 width × height |
| 32 | max_ticks |
| 36 | bomb_fuse_ticks |
| 40 | bomb_capacity |
| 44 | blast_range |

地形按行优先排列，索引为 `y * width + x`；0 = FLOOR，1 = HARD_WALL，2 = SOFT_WALL。

每个玩家记录 16 字节：`id, x, y, alive`。alive 只能为 0 或 1，记录按 id 升序。

每个炸弹记录 24 字节：`id, owner_id, x, y, explode_at_tick, range`。记录按炸弹 id 升序。炸弹 id 从 0 开始，每次放置递增，同 Tick 按玩家 id 升序分配。

总长度必须恰为 `48 + width*height + 16*player_count + 24*bomb_count`。 输入约束为地图尺寸各不超过 31、最多 8 个玩家、最多 8 枚炸弹；任何违反协议的宿主状态都是竞技场错误，不算 Bot 故障。

## 计算预算与内存

固定参数：初始化及输入指针调用共享 10,000,000 fuel；每次 tick 调用独立补足 1,000,000 fuel；线性内存上限 64 MiB。当前验证从源码生成，不依赖历史批次或交接归档。

fuel 是指定运行时的执行计量单位，不承诺等于一条 WASM 指令，也不承诺等于固定毫秒。运行时升级或计量配置变化后必须重新校准和发布版本。修改资源契约前，用 Baseline 和极端状态确认预算足够、异常可及时终止。

状态复制由宿主完成，不计入 Bot fuel；解码器、包装器、Bot 算法和内存增长的运行成本受所选运行时 fuel 机制约束。若运行时无法约束昂贵宿主操作，则不得直接用于正式评测。

每个 Bot 独立实例、内存和预算，逐个调用也必须先收齐动作再推进世界。可以设置宿主 watchdog 防止运行时卡死，但它只用于基础设施保护；watchdog 超时使该局标为基础设施失败，不能转成正式比赛胜负。

## 故障处理

| 情况 | 处理 |
| --- | --- |
| 编译失败、ABI 不合格、禁止特性 | 导入失败；不当作 0 分正常 Bot |
| 初始化或输入指针调用超 fuel、trap、缓冲区不合法 | 该局初始化淘汰，death_tick = -1 |
| tick fuel 耗尽 | 本 Tick WAIT，记录一次动作故障 |
| tick 返回非 0～5 | 本 Tick WAIT，记录一次动作故障 |
| tick 非 fuel trap，例如越界、unreachable | 本 Tick 立即淘汰，记录运行崩溃 |
| 合法动作撞墙、争抢位置、容量满时放炸弹 | 正常无效果，不算动作故障 |
| 宿主、引擎、状态序列化或 worker 错误 | 基础设施失败，结果不进入正式统计 |

连续动作故障达到 3 次或累计达到 20 次时，在本 Tick 的调用验证阶段淘汰。返回合法枚举值即清零连续故障计数，即使游戏动作无效果；累计计数不清零。

fuel trap 或非法返回之前的内存写入保留，不回滚，不重跑当前调用。下一 Tick 在同一实例补充 fuel 后继续。所选运行时必须支持 trap 后再次调用；如果不支持，需要修改并版本化此契约，不能静默重置 Bot 状态。

超时已发生在调用期间，因此自己的当前观察仍显示自己存活；淘汰影响这一步之后的游戏状态。其他 Bot 当前观察保持一致，下一 Tick 才看到淘汰结果。

## 运行检查与 Bot 快照

编译产物先验证 WASM 结构、导出签名、内存限制、输入区域和禁止项，再运行公开状态 smoke check。通过运行检查不保证对局永不故障。

每个提交保留源码、WASM、编译日志、SDK 版本、编译器版本与参数、源码和 WASM 的 SHA-256。不得为不同模型单独修改包装器或编译参数。
