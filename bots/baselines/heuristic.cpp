#include "planner.hpp"
static arena::Rng rng;
namespace bot {
void init(uint64_t seed) { rng.seed(seed); }
Action tick(const GameState& s) {
    if(planning::useful_bomb(s)) {
        auto with_bomb=planning::forecast(s,true);
        // BOMB consumes the current action: only accept escape plans starting with WAIT.
        // Constrain other first-step cells so plan tests the actual placement turn.
        int sx=int(s.self().x),sy=int(s.self().y);
        for(int d=1;d<=4;++d) {
            int x=sx+planning::dx[d],y=sy+planning::dy[d];
            if(s.inside(x,y))with_bomb.terrain[0][y*s.width+x]=arena::HARD_WALL;
        }
        if(planning::plan(s,with_bomb,true,rng)==0)return Action::BOMB;
    }
    auto f=planning::forecast(s,false);
    int move=planning::plan(s,f,true,rng);
    return move<0?Action::WAIT:Action(move);
}
}
