# LLM Arena：模型 Bot 开发任务书

你正在参加一场顶级前沿大语言模型之间的策略与编程竞技。你的 Bot 将代表你，与其他前沿模型独立开发的 Bot 同台对战。同一竞技项目中，其他参赛模型收到的任务提示词与你完全相同。各方遵守相同的游戏规则、接口与运行资源限制，对手的策略和实现未知。

请交付你能实现的最强炸弹人 Bot，在未知地图和未知对手上争取更高的平均名次分。算法、策略与开发过程由你自主决定，请充分发挥你的判断力、创造力与编程能力。

随包提供的 Baseline 是一个普通的参考 Bot，用于本地练习和计分锚定。最终对战面对的是其他前沿模型的参赛 Bot，基准成绩仅供参考。

本文件用于向不同模型分发同一项 C++20 Bot 开发任务，规则对应已验收的工程。正文包含完成源码所需的规则和接口，可直接粘贴给模型；支持文件工具的模型同时获得指定的 SDK 与公开开发材料。

**本任务书可独立阅读，理解规则和编写源码不需要打开任何外部链接。** 第 5 节已给出完整 SDK 头文件，第 8 节给出提交格式。文中提到的文件路径都是标准开发包内、相对于解压目录或主办方指定工作区根目录的路径，不指向主办方电脑上的原项目。

如果主办方提供了开发包和可执行工具，你可以在该工作区内编译、练习并查看基准 BOT；如果只收到这份文字，就按正文完成源码并在对话中交卷，无需寻找文件或链接，也不要声称已经编译或测试。

## 1. 开发与交付

准备环境后阅读任务书，生成一个完整的 C++20 单文件 `bot.cpp`。可以自主编译、练习和迭代；默认不设开发倒计时、token 或工具次数限制。

使用者明确指定交付位置时写到该位置，否则在当前对话交付完整源码。没有文件工具时按正文 SDK 编写，不声称完成了实际编译或测试。不得修改规则、SDK、包装器、编译参数与运行时。

## 2. 你的任务与目标

你的 Bot 将参与 2～8 个 Bot 各自为战的对局。没有队伍，除自己以外的所有槽位都是对手；相同 Bot 的重复参赛槽位也独立竞争。

请编写一个用于 2～8 人各自为战的炸弹人比赛的 C++20 Bot。你负责生成源码；宿主负责用固定 SDK 编译为 WebAssembly、提供游戏观察并执行比赛。运行期间不再调用模型。

目标是提高在未知地图和未知对手上的平均名次分。每个 Bot 各自为战；名次分 =（排名低于自己的对手数 + 0.5 × 与自己并列的对手数）/（参赛人数 - 1）。双人每局胜得 1 分、平得 0.5 分、负得 0 分。局内排名由总积分决定：回合结算后仍存活 +1 分，击杀敌人 +100 分，同分并列。名次分是排名的归一化指标，不是局内积分。

局内积分从 0 开始：每个 Tick 的故障、移动、爆炸和清理结束后，仍存活者获得 1 分；等待或无效果的合法动作也能获得生存分。死亡的当 Tick 不得生存分。每击杀一名敌人获得 100 分，奖励相当于存活 100 回合。

爆炸死亡按覆盖死亡格的不同炸弹 owner 归因：每个不同于死亡者的 owner 各记一次击杀并得 100 分；同一 owner 的多枚炸弹不重复计分。自杀不给击杀分；混合命中中排除死亡者自身，其余 owner 正常得分。连锁按实际爆炸炸弹的 owner 计分，不把整条连锁归给起爆者。死亡者已放的炸弹仍能击杀得分；运行故障淘汰不奖励任何人。炸墙不加分。

最终仅按总积分降序排名，同分并列，不用存活状态、死亡 Tick 或击杀数破同分。即使已经死亡，也可能凭之前或延迟的击杀积分排在存活者前面。死亡 Tick 仍用于回放诊断。初始化淘汰记 `death_tick = -1`；初始化后存活者不超过一人时，直接结束，所有人均为 0 分并列。正常结算后存活者不超过一人或达到 500 回合上限时结束，不补发剩余回合积分。

当前炸弹人规则版本为 2。旧版按存活顺序排名的录像仍按规则 1 验证和播放，旧记录与旧规则重赛不进入规则 2 的榜单。重赛保留原比赛规则、地图、Bot 快照与种子。事件保留完整爆炸 owner 集合和每笔击杀奖励；状态与终局保存总积分、击杀数和生存 / 击杀积分拆分。

使用者在本地应用导入 Bot，选择 2～8 个参赛 Bot 运行单局。应用自动编译与检查，失败时显示诊断；修复后重新导入形成新快照。榜单只汇总本地有效单局，不代表统一赛程或长期评级。

游戏只内置一个 Baseline 参考 BOT，其实力分固定为 0。榜单根据有效对战和对手强度估计相对实力：强于基准为正、弱于基准为负；未通过直接或间接对战关联当前基准时显示待定。名次分和胜平负保留为辅助统计。

## 3. 游戏观察与地图

- 坐标原点在左上角，x 向右、y 向下；地图为 13 × 11。槽位 ID 为 `0..player_count-1`，出生点依次是 `(1,1)`、`(11,9)`、`(11,1)`、`(1,9)`、`(5,1)`、`(7,9)`、`(11,5)`、`(1,5)` 的前 N 个；双人仍使用前两个。不要假设只有一个对手。
- 初始地图关于中心旋转 180° 对称。外边界及内部 x、y 均为偶数的格子是硬墙。出生点及其旋转对应点曼哈顿距离不超过 2 的非硬墙格是道路；奇数人数时未使用的对应出生区也清空。其余候选格按对称轨道约以 55% 概率放软墙，并通过合法性检查。相同地图 Seed 在不同人数下可产生不同地形。
- 地形只有道路、不可破坏硬墙、可破坏软墙；玩家与炸弹是独立实体。地形数组不会用玩家或炸弹覆盖道路值。
- 每次观察包含全部地形、全部玩家、全部炸弹和游戏参数，没有视野遮挡。死亡玩家仍有记录并保留最后坐标，但不占格。
- 炸弹公开 ID、owner、位置、爆炸 Tick 与范围。当前游戏状态完全公开，对手本 Tick 动作尚不可见。
- 不提供对手源码、模型身份、对手内存、隐藏地图 Seed、宿主时间或正式评测结果。初始化种子独立于地图 Seed，不能用来直接推导地图。
- 公开开发地图不能代替隐藏评测集；不要按公开地图或特定对手硬编码答案。

## 4. 动作与 Tick 结算

游戏初始 `tick = 0`，最多结算 Tick 0～499，共 500 次。每次返回一个动作：

| 枚举 | 值 | 效果 |
| --- | --- | --- |
| `Action::WAIT` | 0 | 原地等待 |
| `Action::UP` | 1 | y − 1 |
| `Action::RIGHT` | 2 | x + 1 |
| `Action::DOWN` | 3 | y + 1 |
| `Action::LEFT` | 4 | x − 1 |
| `Action::BOMB` | 5 | 在当前位置放炸弹 |

一个 Tick 不能同时移动和放炸弹。每名玩家最多持有 1 枚尚未爆炸的炸弹，初始爆炸范围为 3 格。

对于 Tick T，严格按以下顺序结算：

1. 给所有存活 Bot 提供同一份世界快照，仅 `self_id` 不同。
2. 收集并验证全部动作；故障处理见第 7 节。此阶段淘汰者在移动前释放位置。
3. 同时结算移动。
4. 执行 BOMB，设新炸弹 `explode_at_tick = T + 4`。容量已满或脚下已有炸弹时，无效果。移动阶段尚未清理到期炸弹，放置阶段也尚未释放它们占用的容量。
5. 让所有到期炸弹及它们触发的连锁炸弹爆炸，确定完整覆盖集合。
6. 覆盖集合中的存活玩家同时死亡，`death_tick = T`。
7. 同时移除爆炸炸弹和被击中的软墙。
8. 结算击杀分，仍存活者各加 1 分。存活者不超过 1 人则立即结束；否则在完成第 500 次结算后结束；其余情况推进到下一 Tick。

初始化淘汰的死亡 Tick 为 −1；初始化后存活者不超过 1 人时，直接结束，不执行 Tick 0。死亡当 Tick 不得生存分；排名仅看累计积分。

### 同时移动

墙和炸弹所在格不可进入。玩家可以从自己脚下的炸弹离开，但不能再进入炸弹格。

- 越界、撞墙或进入炸弹格：原地停留，无动作故障。
- 多名玩家请求同一个目的地：这些移动全部失败。
- 进入另一名玩家的起始位置：仅当对方成功离开时才成功。
- 交换位置及其他移动环：全部失败。
- 移动依赖链最终到达空格，则整条链成功；最终到达不移动者、失败请求或移动环，则整条链失败。
- 失败者原地停留，不自动改走其他方向。动作不是按玩家 ID 逐个移动。

### 爆炸与连锁

Tick T 放的炸弹在 T～T+3 不会自行爆炸，在 T+4 的爆炸阶段爆炸；连锁可以提前引爆，包括本 Tick 刚放的炸弹。观察中的剩余延迟为 `explode_at_tick - tick`，到期炸弹为 0。

爆炸覆盖炸弹自身格，并向上、右、下、左各传播最多 3 格：

| 遇到的对象 | 传播规则 |
| --- | --- |
| 地图外 / 硬墙 | 停止；硬墙格不计入覆盖 |
| 软墙 | 覆盖并标记销毁该格，停止此方向 |
| 炸弹 | 覆盖该格并触发该炸弹，停止当前炸弹此方向；被触发炸弹独立传播 |
| 玩家 / 道路 | 覆盖该格，继续传播；玩家不阻挡爆炸 |

整个爆炸阶段都使用“放置后、爆炸前”的同一份墙与炸弹快照。软墙统一在阶段末移除，因此一枚炸弹炸掉的墙不会让另一枚炸弹在同 Tick 穿透。每枚炸弹在连锁闭包中最多处理一次，结果与处理顺序无关。

爆炸前先移动，所以到期 Tick 仍可移出危险格，进入危险格则会死亡。没有跨 Tick 火焰，下一 Tick 可以进入本 Tick 爆炸过的道路。玩家死亡后不再被调用，已经放置的炸弹继续存在并保持原 owner。

## 5. C++20 接口：arena.hpp

SDK 提供以下完整头文件。你只需在源码中 `#include "arena.hpp"`，不要在提交中重定义这些类型。`Action` 和 `GameState` 已导入全局命名空间，其他类型在 `arena` 命名空间。

```cpp
#pragma once
#include <cstdint>

namespace arena {
enum class Action : uint32_t { WAIT, UP, RIGHT, DOWN, LEFT, BOMB };
enum Terrain : uint8_t { FLOOR, HARD_WALL, SOFT_WALL };
struct Player { uint32_t id, x, y, alive, score, kills; };
struct Bomb { uint32_t id, owner_id, x, y, explode_at_tick, range; };
struct GameState {
    uint32_t tick, width, height, self_id, player_count, bomb_count;
    uint32_t max_ticks, bomb_fuse_ticks, bomb_capacity, blast_range;
    uint32_t scoring_version, survival_points, kill_points;
    uint8_t grid[31 * 31];
    Player players[8];
    Bomb bombs[8];
    const Player& self() const { return players[self_id]; }
    bool inside(int x, int y) const { return x >= 0 && y >= 0 && x < int(width) && y < int(height); }
    uint8_t cell(int x, int y) const { return inside(x, y) ? grid[y * width + x] : HARD_WALL; }
};
// xorshift64*: seed 0 has a fixed substitute; all operations are unsigned.
struct Rng {
    uint64_t state = 1;
    void seed(uint64_t value) { state = value ? value : 0x9e3779b97f4a7c15ULL; }
    uint32_t next() {
        state ^= state >> 12; state ^= state << 25; state ^= state >> 27;
        return uint32_t((state * 2685821657736338717ULL) >> 32);
    }
};
}

using arena::Action;
using arena::GameState;
namespace bot {
void init(uint64_t seed);
Action tick(const GameState& state);
}
```

接口使用约定：

- 每局创建全新实例，先调用一次 `bot::init(seed)`，然后对存活玩家每 Tick 调用一次 `bot::tick(state)`。静态变量、堆内存及 RNG 状态可在该局内保留，不能跨局保留。
- `player_count` 包含死亡者，玩家按 ID 升序，ID 为 `0..player_count-1`，实际人数为 2～8；`alive` 为 0 或 1。通过 `state.self()` 获取自己。
- `score` 为总积分，`kills` 为归因击杀数，含本人死亡后炸弹的击杀；`scoring_version=2`、`survival_points=1`、`kill_points=100`。
- 地形有效区为 `width * height` 字节，行优先索引为 `y * width + x`。值为 0 道路、1 硬墙、2 软墙；`cell()` 对越界坐标返回硬墙。
- 只读取 `players[0..player_count)` 和 `bombs[0..bomb_count)`。炸弹按 ID 升序，ID 随放置递增，不保证是紧凑数组下标。
- 协议上限是每个维度不超过 31、玩家不超过 8、炸弹不超过 8；当前比赛为 2～8 人各自为战、13 × 11。用状态中的实际参数判断游戏，不要把预留容量误认为当前数量。
- `GameState` 仅在当前调用期间有效。需要历史信息时保存数值或副本，不要保存输入引用 / 指针供下一 Tick 使用。不得修改输入状态。
- 可使用提供的 `arena::Rng`，也可实现基于传入种子的可复现 RNG。不使用系统随机源。

## 6. 编译与资源限制

统一编译器为 WASI SDK 33.0 / Clang 22.1.0，语言标准 C++20，优化为 `-O2`，禁用异常和 RTTI；运行时为 Wasmtime 49.0.0。SDK 包装器负责状态解码和 WASM 导出，你不需要编写 ABI 或 `main()`。

| 限制 | 冻结参数 |
| --- | --- |
| 单个提交源码 | 最多 1 MiB |
| 编译后的 WASM | 最多 8 MiB |
| 线性内存 | 最多 64 MiB，包含默认 1 MiB 栈 |
| 初始化预算 | 初始化、协议能力读取与输入指针调用共享 10,000,000 fuel |
| 每 Tick 预算 | 每次独立补足 1,000,000 fuel；包含 SDK 解码和 Bot 执行成本 |

fuel 是运行时执行计量，不是毫秒，也不保证一 fuel 等于一条指令。初始化与每 Tick 的预算不能互相转移，也不能跨 Tick 累积。

允许常用 STL 容器与动态内存；静态构造在初始化时执行。普通 `new` 分配失败直接 trap，`nothrow new` 返回空指针。必须避免未定义行为。

禁止宿主导入、WASI 调用、文件 / 标准输入输出、网络、时钟、线程、系统随机源和需要这些能力的库功能。不要使用 `random_device` 或通过输出日志与宿主交互。不得引入额外源文件或第三方依赖；标准库头文件可以使用。

## 7. 运行故障的处理

| 情况 | 后果 |
| --- | --- |
| 编译失败或 WASM / ABI 不合格 | 导入失败，修复后重新导入 |
| 初始化超 fuel、trap 或输入区域不合法 | 该局初始化淘汰，死亡 Tick 为 −1 |
| Tick fuel 耗尽 | 当前动作变 WAIT，并记录一次动作故障 |
| 返回 0～5 以外的值 | 当前动作变 WAIT，并记录一次动作故障 |
| Tick 非 fuel trap，如越界或 unreachable | 在当前调用验证阶段立即淘汰 |
| 合法动作被墙、玩家、炸弹或容量限制阻止 | 正常无效果，不计故障 |

连续动作故障达到 3 次，或累计达到 20 次时，在当前调用验证阶段淘汰。返回合法动作即清零连续计数，即使动作无效果；累计计数不清零。

fuel 耗尽或非法返回之前的内存写入保留，不回滚，不重新调用当前 Tick。若尚未淘汰，下一 Tick 从同一实例发起新的调用并补充 fuel，不从中断的指令处继续执行。

宿主或引擎错误标为基础设施失败，不当作 Bot 胜负。故障淘汰者保留累计积分，已放置的炸弹仍可在之后产生击杀分；最终按总积分排名。故障淘汰本身不记为爆炸击杀或自杀。

## 8. 提交格式

提交一个完整的 `bot.cpp`，只实现 `bot::init(uint64_t)` 与 `bot::tick(const GameState&)`，可在同一文件中增加辅助函数和内部状态。必须包含 `arena.hpp`，不提供 `main()`，不替换 SDK，不包含占位实现或省略代码。

默认通过当前对话提交：最终回复先提供一个 `cpp` 代码块，内容为完整源码，再附中文开发流程总结，不提供第二种实现或占位代码。主办方明确指定文件位置时，将同样的源码写入该位置的 `bot.cpp`，在最终回复中说明交付位置并附上中文开发流程总结。

中文开发流程总结应简要梳理本次编写 Bot 的全过程，包括规则理解、策略设计、实现与修改、实际编译和测试情况，以及最终方案与已知局限。按实际完成的工作总结，未执行的环节如实说明。总结放在源码代码块之外，不写入 `bot.cpp`。

下面是接口模板，WAIT 仅展示调用形式，请实现你自己的完整 Bot：

```cpp
#include "arena.hpp"
namespace bot {
void init(uint64_t) {}
Action tick(const GameState&) { return Action::WAIT; }
}
```

## 9. 公开验证方式（有本地工具时使用）

仅在主办方已提供并准备好标准开发包时使用本节命令，执行目录为主办方指定的开发包根目录。可以按需要重复编译和练习。只收到任务书文字时跳过本节运行操作，直接提交源码。

```powershell
.\.venv\Scripts\python.exe arena.py build bot.cpp --output artifacts/work/submission.wasm
.\.venv\Scripts\python.exe arena.py qualify artifacts/work/submission.wasm
.\.venv\Scripts\python.exe arena.py map 1 --output artifacts/work/map-1.json
```

`build` 使用固定 SDK 和统一编译参数；`qualify` 检查结构、导出、内存、初始化和公开状态调用。通过资格检查不保证正式比赛没有运行故障，也不代表策略得分高。

标准开发包包含真实规则引擎、固定 SDK / 编译器配置、受限 WASM 执行器、10 张公开地图，以及一个 Baseline 参考 BOT 的源码和冻结 WASM（基准实力分 0）。公开地图清单是 `configs/public-dev.json`；基准入口为 `bots/baselines/baseline.cpp`，辅助策略为 `bots/baselines/champion.hpp`。拿到这些实际文件后，可以阅读基准策略、查看公开测试日志和 Replay，并修改自己的源码。若复用基准辅助实现，将其合并进单个 `bot.cpp`，最终提交不能依赖额外辅助头文件。

对基准 BOT 进行练习，可指定实际参赛人数：

```powershell
.\.venv\Scripts\python.exe tools\practice.py --source bot.cpp --output artifacts/work/practice-01
.\.venv\Scripts\python.exe tools\practice.py --source bot.cpp --players 3 --maps 1 --output artifacts/work/practice-3p
.\.venv\Scripts\python.exe tools\practice.py --source bot.cpp --players 8 --opponent baseline --maps 1 --output artifacts/work/practice-8p
```

`--players` 支持 2～8，默认 2；每局一个候选 Bot 和所选基准的 N−1 个独立实例各自为战。每张地图让候选 Bot 依次占据全部 N 个出生位，Seed 跟随实例一起轮换。默认一个基准、十张公开地图、双人换边，共 20 局；例如 `--players 3 --maps 1` 为 3 局，`--players 8 --opponent baseline --maps 1` 为 8 局。根目录启动脚本默认进行三人环境检查，也可用 `-Players 2` 或 `-Players 8` 指定人数。

输出 `summary.md` / `summary.json`，以及 `replays/` 下每局的逐 Tick Replay。平均得分按第 2 节名次分计算；独占第一记胜、并列第一记平、其余记负，不能在多人模式下用胜 / 平次数推算平均分。每轮使用新的输出目录。练习与应用使用相同规则和资源限制，练习记录不进入应用榜单；不要按公开地图或特定基准硬编码答案。

---

## 分发与导入说明

向模型发送同一份标准开发 ZIP 即可，包根目录 README 与 START_HERE 提供执行步骤。模型自行选择独立目录，运行 start-devkit.ps1 准备环境，完成后交付 bot.cpp，并在最终回复中用中文梳理开发全过程；使用者在应用首页导入源码。

完整规则、SDK、地图和资源限制与应用保持一致。练习工具只使用公开开发地图，不需要历史比赛归档。开发包不包含本机 Bot 或录像数据。

可选参考资料：`docs/specs/rules.md`、`docs/specs/bot-sdk.md`、`docs/specs/maps-and-randomness.md`、`docs/specs/benchmark.md` 和 `docs/guides/model-development.md`。只收到任务书文字时，以正文为准。
