#include "gomoku.hpp"
namespace bot {
gomoku::Rng rng;
void init(uint64_t seed) { rng.seed(seed); }
Action tick(const GameState& s) {
    int cells[225], n=0;
    for(int i=0;i<225;++i) if(!s.grid[i]) cells[n++]=i;
    if(!n) return Action::resign();
    int i=cells[rng.next()%n]; return {i%15,i/15};
}
}
