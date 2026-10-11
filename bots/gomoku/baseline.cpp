#include "champion.hpp"
namespace bot {
void init(uint64_t) {
    gomoku::Rng rng;rng.seed(0x58c748217e83ac39ULL);
    for(int i=0;i<225;++i)for(int c=1;c<=2;++c)
        champion::keys[i][c]=(uint64_t(rng.next())<<32)|rng.next();
    for(auto& entry:champion::cache)entry={};
}
Action tick(const GameState& s) {
    int i=champion::choose(s);return i<0?Action::resign():Action{i%15,i/15};
}
}
