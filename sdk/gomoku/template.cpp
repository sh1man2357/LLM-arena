#include "gomoku.hpp"
namespace bot {
void init(uint64_t) {}
Action tick(const GameState& s) {
    for (int y=0;y<15;++y) for(int x=0;x<15;++x) if(!s.cell(x,y)) return {x,y};
    return Action::resign();
}
}
