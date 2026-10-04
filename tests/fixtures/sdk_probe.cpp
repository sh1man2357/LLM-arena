#include "arena.hpp"
#include <vector>
static uint64_t observed_seed;
static int constructor_value;
struct Constructor { Constructor(){ constructor_value=7; } } object;
static std::vector<int> state;
namespace bot {
void init(uint64_t seed) { observed_seed=seed; state.push_back(11); }
Action tick(const GameState& s) {
    if(observed_seed!=0xfedcba9876543210ULL||constructor_value!=7||state[0]!=11)return Action(99);
    if(s.width!=13||s.height!=11||s.self_id!=1||s.player_count!=2||s.bomb_count!=1)return Action(98);
    if(s.self().x!=11||s.self().y!=9||s.bombs[0].owner_id!=0||s.bombs[0].explode_at_tick!=4)return Action(97);
    if(s.cell(0,0)!=arena::HARD_WALL||s.blast_range!=3||s.bomb_capacity!=1)return Action(96);
    state.push_back(22);
    return Action(state.size()==2?2:3);
}
}
