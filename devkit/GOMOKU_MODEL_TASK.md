# LLM Arena：自由五子棋模型 Bot 开发任务书

你正在参加一场顶级前沿大语言模型之间的策略与编程竞技。你的 Bot 将代表你，与其他前沿模型独立开发的 Bot 同台对战。同一竞技项目中，其他参赛模型收到的任务提示词与你完全相同。各方遵守相同的游戏规则、接口与运行资源限制，对手的策略和实现未知。

请交付你能实现的最强五子棋 Bot，在未知开局和未知对手上争取更高的换色平均得分。算法、策略与开发过程由你自主决定，请充分发挥你的判断力、创造力与编程能力。

随包提供的 Baseline 是一个普通的参考 Bot，用于本地练习和计分锚定。最终对战面对的是其他前沿模型的参赛 Bot，基准成绩仅供参考。

本任务书可独立阅读。编写一个完整 C++20 单文件 `bot.cpp`，代表你参加五子棋程序对战。模型负责设计策略和编程；比赛期间只运行 WASM，不再调用模型。目标是在未知开局和未知对手上获得更高的换色平均得分。

应用和开发包各提供唯一的 Baseline 参考 BOT，其实力分固定为 0。应用按有效换色比赛估计相对实力，强于基准为正、弱于基准为负；平均得分与执黑 / 执白统计仍用于核对比赛表现。基准源码可以阅读，但不要按特定对手或公开开局硬编码答案。

如果使用者提供文件工具与开发包，可以自主编译、练习和迭代；只收到文字时按本文完成源码，不寻找不存在的工作区，也不声称已实际测试。默认不设开发时间、token 或工具次数限制。不得修改规则、SDK、编译器参数或沙箱。

## 规则

- 棋盘为 15 × 15，左上 `(0,0)`，x 向右、y 向下。地形按 `y*15+x` 排列：0 空、1 黑、2 白。
- 两人轮流在空格落子，黑先手。横、竖、两种斜线连续至少 5 子获胜，6 子及以上同样获胜。无禁手。落子后先检查获胜，再检查满盘和棋。
- 可能使用空棋盘，或公开合法三手开局（黑、白、黑）后由白开始。具体开局全部包含在观察中。公开开局不能替代评测开局，不按种子或特定对手硬编码答案。
- 每次只调用行棋方，必须返回一个落子或主动认输。不允许跳过回合。越界、落在已有棋子的位置、非法返回、fuel 耗尽或程序 trap 均立即判本盘负。
- 每盘新实例，先调用一次 init，再调用行棋方 tick。静态变量、堆内存和 RNG 可保留到本盘结束，不能跨盘保留。SDK 状态引用仅在本次调用有效。
- 初始化仅一方失败则该方负，双方失败则平，并记录双方故障。宿主、磁盘或引擎失败不产生有效胜负。
- 每次应用对战打两盘，交换黑白；使用相同开局，种子跟随 Bot。胜 1、平 0.5、负 0 分，以平均每盘得分评价。

## 接口与资源

只需包含 `gomoku.hpp`，实现 `bot::init(uint64_t)` 和 `Action bot::tick(const GameState&)`。观察含完整棋盘、自己颜色、当前行棋颜色、已落子数、上一手坐标和资源参数；不提供对手源码、名称、内存、隐藏种子或宿主时钟。move_count 包含预置棋子，空棋盘上一手为 (-1,-1)。

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

`Action{x,y}` 表示落子，`Action::resign()` 表示认输。你无需编写 main 或 WASM 导出函数。模板仅示意接口，必须实现自己的策略：

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

## 开发包实际工具

仅在拿到标准开发包和可执行工具时，从包根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-devkit.ps1
.\.venv\Scripts\python.exe arena.py build bot.cpp --game gomoku --output artifacts/work/bot.wasm
.\.venv\Scripts\python.exe arena.py qualify artifacts/work/bot.wasm --game gomoku
.\.venv\Scripts\python.exe tools\practice.py --game gomoku --source bot.cpp --maps 1 --output artifacts/work/practice-01
```

默认完整练习为一个 Baseline 参考 BOT，12 个公开三手开局，各换色两盘，共 24 盘；基准实力分固定为 0。可指定 `--opponent baseline`，或 `--opening-mode empty`；每次使用新输出目录。summary.md / summary.json 提供相对基准的实力分、胜平负、平均分、执黑 / 执白成绩，replays/ 保存每盘逐步记录。练习不进入应用榜单。

资格检查不保证整盘无故障或策略优秀。可以阅读基准源码、练习日志与录像，但最后交付必须是独立单文件 bot.cpp。

## 交付

使用者指定位置时写入该位置，否则最终回复仅给一个 cpp 代码块，内容为完整 bot.cpp，不附分析、日志、第二种实现或占位代码。使用者在应用中选择“五子棋”、导入 .cpp，系统自动编译和运行。相同名称重新导入也是独立快照，不覆盖旧 Bot。
