# 炸弹人 Bot 开发任务书

## 1. 开发要求

实现可参加 2～8 人混战的 C++20 炸弹人 Bot，目标是在未知地图和对手上取得较高的平均名次分。同一游戏的参赛模型应使用相同的任务包、提示词、接口和计算预算。策略及实现由各模型独立决定。基准 Bot 的实力分固定为 0，用于公开练习和相对实力估计。

在独立目录解压任务包，从 `START_HERE.md` 准备环境。路径均相对于包根目录。开发时间和迭代次数由主办方安排；任务包默认不计时。保持规则、SDK、包装器、编译参数和运行时配置一致。

## 2. 计分与排名

每个槽位独立参赛。每回合结算后存活得 1 分，每击杀一名对手得 100 分。死亡当回合不计生存分。爆炸按命中死亡格的炸弹所有者归因，每名非死者所有者各得一次奖励，同一所有者的多枚炸弹只计一次。连锁按各自炸弹归属计分，死者已放置的炸弹仍可得分。炸墙、自杀和故障淘汰均不产生击杀奖励。

终局按累计积分降序排名，同分并列。名次分为 `(积分低于自己的对手数 + 0.5 × 与自己同分的对手数) / (参赛人数 − 1)`。双人对战胜、平、负分别得 1、0.5、0 名次分。

## 3. 游戏观察与地图

- 坐标原点在左上角，x 向右、y 向下；地图为 13 × 11。槽位 ID 为 `0..player_count-1`，出生点依次是 `(1,1)`、`(11,9)`、`(11,1)`、`(1,9)`、`(5,1)`、`(7,9)`、`(11,5)`、`(1,5)` 的前 N 个；双人仍使用前两个。应按 `player_count` 遍历对手。
- 初始地图关于中心旋转 180° 对称。外边界及内部 x、y 均为偶数的格子是硬墙。出生点及其旋转对应点曼哈顿距离不超过 2 的非硬墙格是道路；奇数人数时未使用的对应出生区也清空。其余候选格按对称轨道约以 55% 概率放软墙，并通过合法性检查。相同地图 Seed 在不同人数下可产生不同地形。
- 地形只有道路、不可破坏硬墙、可破坏软墙；玩家与炸弹是独立实体。地形数组不会用玩家或炸弹覆盖道路值。
- 每次观察包含全部地形、全部玩家、全部炸弹和游戏参数，没有视野遮挡。死亡玩家仍有记录并保留最后坐标，但不占格。
- 炸弹公开 ID、owner、位置、爆炸 Tick 与范围。当前游戏状态完全公开，对手本 Tick 动作尚不可见。
- 不提供对手源码、模型身份、对手内存、地图种子、宿主时间或正式评测结果。初始化种子独立于地图 Seed，不能用来直接推导地图。
- 策略须适用于未知地图和对手，不得为公开地图或特定对手硬编码答案。

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

爆炸前先移动，到期 Tick 仍可移出危险格，进入危险格则会死亡。没有跨 Tick 火焰，下一 Tick 可以进入本 Tick 爆炸过的道路。玩家死亡后不再被调用，已经放置的炸弹继续存在并保持原 owner。

## 5. C++20 接口：arena.hpp

SDK 提供以下完整头文件。在源码中 `#include "arena.hpp"`，使用头文件提供的类型定义。`Action` 和 `GameState` 已导入全局命名空间，其他类型在 `arena` 命名空间。

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

统一编译器为 WASI SDK 33.0 / Clang 22.1.0，语言标准 C++20，优化为 `-O2`，禁用异常和 RTTI；运行时为 Wasmtime 49.0.0。SDK 包装器负责状态解码和 WASM 导出，参赛源码无需提供 ABI 导出或 `main()`。

| 限制 | 参数值 |
| --- | --- |
| 单个提交源码 | 最多 1 MiB |
| 编译后的 WASM | 最多 8 MiB |
| 线性内存 | 最多 64 MiB，包含默认 1 MiB 栈 |
| 初始化预算 | 初始化、协议能力读取与输入指针调用共享 10,000,000 fuel |
| 每 Tick 预算 | 每次独立补足 1,000,000 fuel；包含 SDK 解码和 Bot 执行成本 |

fuel 是运行时执行计量，不是毫秒，也不保证一 fuel 等于一条指令。初始化与每 Tick 的预算不能互相转移，也不能跨 Tick 累积。

允许常用 STL 容器与动态内存；静态构造在初始化时执行。普通 `new` 分配失败直接 trap，`nothrow new` 返回空指针。必须避免未定义行为。

禁止宿主导入、WASI 调用、文件 / 标准输入输出、网络、时钟、线程、系统随机源和需要这些能力的库功能。禁止使用依赖宿主随机源的 `random_device` 或通过标准输出与宿主交互。不得引入额外源文件或第三方依赖；标准库头文件可以使用。

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

## 8. 交付

提交完整的 C++20 单文件 `bot.cpp`。主办方指定交付路径时，将源码写入该路径并在回复中注明位置；通过对话交付时，先给出一个包含完整源码的 `cpp` 代码块。

源码之外另附中文开发总结，包括规则理解、策略设计、实现与修改、实际编译和练习结果、最终方案及已知局限。仅收到任务书文本时，可依据内嵌 SDK 提交源码，并注明未执行编译和练习。源码包含 `arena.hpp` 并实现 `bot::init` 和 `bot::tick`。复用辅助代码时将其合并至同一源文件。

## 9. 编译与练习

在包根目录完成环境准备并保存 `bot.cpp` 后执行：

```powershell
.\.venv\Scripts\python.exe arena.py build bot.cpp --output artifacts/work/submission.wasm
.\.venv\Scripts\python.exe arena.py qualify artifacts/work/submission.wasm
.\.venv\Scripts\python.exe tools\practice.py --source bot.cpp --players 3 --maps 1 --output artifacts/work/practice-3p
```

`qualify` 检查模块结构、初始化和一次公开状态调用。练习另行运行完整对局。默认使用 10 张公开地图、两个槽位，共 20 局。N 人练习每张地图轮换 N 个出生位，其余槽位使用基准的独立实例。每轮使用新的输出目录；统计见 `summary.md` 和 `summary.json`，录像见 `replays/`。

公开案例见 `configs/public-dev.json`，基准源码见 `bots/baselines/baseline.cpp` 和 `bots/baselines/champion.hpp`。
