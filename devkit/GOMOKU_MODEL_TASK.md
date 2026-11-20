# 自由五子棋 Bot 开发任务书

实现自由五子棋 C++20 Bot，目标是在未知开局和对手上取得较高的换色平均得分。同一游戏的参赛模型应使用相同的任务包、提示词、接口和计算预算。策略及实现由各模型独立决定。基准 Bot 的实力分固定为 0，用于公开练习和相对实力估计。

在独立目录解压并按 `START_HERE.md` 准备环境。使用包内工具编译和练习。比赛只运行编译后的 WASM。策略须适用于未知局面，不得为特定对手或公开开局硬编码答案。任务包不限制开发时间或工具调用次数，规则、SDK、编译参数和沙箱配置固定。

## 规则

- 棋盘为 15 × 15，左上 `(0,0)`，x 向右、y 向下。地形按 `y*15+x` 排列：0 空、1 黑、2 白。
- 两人轮流在空格落子，黑先手。横、竖、两种斜线连续至少 5 子获胜，6 子及以上同样获胜。无禁手。落子后先检查获胜，再检查满盘和棋。
- 可能使用空棋盘，或公开合法三手开局（黑、白、黑）后由白开始。具体开局全部包含在观察中。公开开局不能替代评测开局，不按种子或特定对手硬编码答案。
- 每次只调用行棋方，必须返回一个落子或主动认输。不允许跳过回合。越界、落在已有棋子的位置、非法返回、fuel 耗尽或程序 trap 均立即判本盘负。
- 每盘新实例，先调用一次 init，再调用行棋方 tick。静态变量、堆内存和 RNG 可保留到本盘结束，不能跨盘保留。SDK 状态引用仅在本次调用有效。
- 初始化仅一方失败则该方负，双方失败则平，并记录双方故障。宿主、磁盘或引擎失败不产生有效胜负。
- 应用的 Bot 对战每组两盘，交换黑白；使用相同开局，种子跟随 Bot。胜 1、平 0.5、负 0 分，以平均每盘得分评价。

## 接口与资源

只需包含 `gomoku.hpp`，实现 `bot::init(uint64_t)` 和 `Action bot::tick(const GameState&)`。观察含完整棋盘、自己颜色、当前行棋颜色、已落子数、上一手坐标和资源参数；不提供对手源码、名称、内存、开局种子或宿主时钟。move_count 包含预置棋子，空棋盘上一手为 (-1,-1)。

统一编译 C++20，WASI SDK 33.0 / Clang 22.1.0，`-O2`，禁用异常和 RTTI；Wasmtime 49.0.0 执行。初始化和输入指针调用共享 10,000,000 fuel；每步独立 20,000,000 fuel，含 SDK 解码和程序执行；内存上限 64 MiB，含默认 1 MiB 栈；源码不超过 1 MiB、WASM 不超过 8 MiB。fuel 不是毫秒，不能跨步结转。

允许常用 STL、堆内存与自己的确定性随机数。禁止宿主 / WASI 导入、文件、标准输入输出、网络、时钟、线程和系统随机源。不得引入其他源文件或第三方依赖；复用基准代码时合并到单文件。避免 C++ 未定义行为，分配失败会 trap。

完整 SDK 如下，提交时不要重新定义这些类型：

```cpp
#pragma once
#include <cstdint>

namespace gomoku {
constexpr int SIZE = 15;
enum Cell : uint8_t { EMPTY = 0, BLACK = 1, WHITE = 2 };
struct Action {
    int32_t x, y;
    static Action resign() { return {-1, -1}; }
};
struct GameState {
    uint32_t width, height, self_id, self_color, turn_color, move_count, move_fuel, win_length;
    int32_t last_x, last_y;
    uint8_t grid[SIZE * SIZE];
    bool inside(int x, int y) const { return x >= 0 && y >= 0 && x < SIZE && y < SIZE; }
    uint8_t cell(int x, int y) const { return inside(x,y) ? grid[y*SIZE+x] : 3; }
};
struct Rng {
    uint64_t state = 1;
    void seed(uint64_t value) { state = value ? value : 0x9e3779b97f4a7c15ULL; }
    uint32_t next() {
        state ^= state >> 12; state ^= state << 25; state ^= state >> 27;
        return uint32_t((state * 2685821657736338717ULL) >> 32);
    }
};
}
using gomoku::Action;
using gomoku::GameState;
namespace bot {
void init(uint64_t seed);
Action tick(const GameState& state);
}

```

`Action{x,y}` 表示落子，`Action::resign()` 表示认输。包装器提供 WASM 导出，无需实现 `main()`。以下示例仅演示接口。

```cpp
#include "gomoku.hpp"
namespace bot {
void init(uint64_t seed) {}
Action tick(const GameState& s) {
    for (int y=0;y<15;++y) for(int x=0;x<15;++x) if(!s.cell(x,y)) return {x,y};
    return Action::resign();
}
}
```

## 编译与练习

在包根目录运行环境准备脚本，保存 `bot.cpp` 后执行编译、资格检查和练习。

```powershell
powershell -ExecutionPolicy Bypass -File .\start-devkit.ps1
.\.venv\Scripts\python.exe arena.py build bot.cpp --game gomoku --output artifacts/work/bot.wasm
.\.venv\Scripts\python.exe arena.py qualify artifacts/work/bot.wasm --game gomoku
.\.venv\Scripts\python.exe tools\practice.py --game gomoku --source bot.cpp --maps 1 --output artifacts/work/practice-01
```

默认对手为基准 Bot。在 12 个公开三手开局分别换色两盘，共 24 盘。`--opening-mode empty` 可改用空棋盘。每次练习使用新输出目录。`summary.md` 与 `summary.json` 提供实力分、胜平负及执黑和执白得分，`replays/` 保存每盘录像。练习不计入应用榜单。

资格检查验证初始化及一次公开状态调用；整盘表现以实际练习结果为准。

## 交付

提交完整的 C++20 单文件 `bot.cpp`。主办方指定交付路径时，将源码写入该路径并在回复中注明位置；通过对话交付时，先给出一个包含完整源码的 `cpp` 代码块。

源码之外另附中文开发总结，包括规则理解、策略设计、实现与修改、实际编译和练习结果、最终方案及已知局限。仅收到任务书文本时，可依据内嵌 SDK 提交源码，并注明未执行编译和练习。
