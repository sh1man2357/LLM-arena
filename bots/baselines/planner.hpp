#pragma once
#include "arena.hpp"

namespace planning {
constexpr int CELLS=31*31, HORIZON=6;
constexpr int dx[5]={0,0,1,0,-1}, dy[5]={0,-1,0,1,0};
struct Forecast {
    uint8_t terrain[HORIZON+1][CELLS]{};
    bool danger[HORIZON+1][CELLS]{};
    bool occupied[HORIZON+1][CELLS]{};
};

inline Forecast forecast(const GameState& s, bool new_bomb) {
    Forecast out{};
    uint8_t grid[CELLS];
    int cells=int(s.width*s.height);
    for(int i=0;i<cells;++i) grid[i]=s.grid[i];
    arena::Bomb bombs[9]; bool live[9]{};
    int count=int(s.bomb_count);
    for(int i=0;i<count;++i) { bombs[i]=s.bombs[i]; live[i]=true; }
    if(new_bomb) {
        bombs[count]={0,s.self_id,s.self().x,s.self().y,s.tick+s.bomb_fuse_ticks,s.blast_range};
        live[count++]=true;
    }
    for(int t=0;t<=HORIZON;++t) {
        for(int i=0;i<cells;++i) out.terrain[t][i]=grid[i];
        int at[CELLS]; for(int i=0;i<cells;++i) at[i]=-1;
        bool explode[9]{}, done[9]{}, destroyed[CELLS]{};
        for(int i=0;i<count;++i) if(live[i]) {
            int pos=bombs[i].y*s.width+bombs[i].x;
            at[pos]=i; out.occupied[t][pos]=true;
            explode[i]=bombs[i].explode_at_tick<=s.tick+uint32_t(t);
        }
        bool changed=true;
        while(changed) {
            changed=false;
            for(int i=0;i<count;++i) if(explode[i]&&!done[i]) {
                done[i]=true; changed=true;
                const auto& b=bombs[i]; out.danger[t][b.y*s.width+b.x]=true;
                for(int d=1;d<=4;++d) for(int k=1;k<=int(b.range);++k) {
                    int x=int(b.x)+dx[d]*k,y=int(b.y)+dy[d]*k;
                    if(!s.inside(x,y)) break;
                    int pos=y*s.width+x;
                    if(grid[pos]==arena::HARD_WALL) break;
                    out.danger[t][pos]=true;
                    if(grid[pos]==arena::SOFT_WALL) {destroyed[pos]=true;break;}
                    if(at[pos]>=0) {explode[at[pos]]=true;break;}
                }
            }
        }
        for(int i=0;i<count;++i) if(explode[i]) live[i]=false;
        for(int i=0;i<cells;++i) if(destroyed[i]) grid[i]=arena::FLOOR;
    }
    return out;
}

inline bool player_at(const GameState& s,int x,int y) {
    for(uint32_t i=0;i<s.player_count;++i)
        if(i!=s.self_id&&s.players[i].alive&&int(s.players[i].x)==x&&int(s.players[i].y)==y) return true;
    return false;
}

inline int objective(const GameState& s,int x,int y) {
    // Search through walkable cells. A target behind a wall may require moving
    // away from it first; geometric distance cannot recognize that detour.
    int distance[CELLS],queue[CELLS],head=0,tail=0;
    bool blocked[CELLS]{};
    for(int i=0;i<int(s.width*s.height);++i)distance[i]=-1;
    for(uint32_t i=0;i<s.bomb_count;++i)
        blocked[s.bombs[i].y*s.width+s.bombs[i].x]=true;
    int start=y*s.width+x;
    distance[start]=0;queue[tail++]=start;
    while(head<tail) {
        int pos=queue[head++],cx=pos%int(s.width),cy=pos/int(s.width);
        for(int d=1;d<=4;++d) {
            int nx=cx+dx[d],ny=cy+dy[d];
            if(!s.inside(nx,ny))continue;
            int next=ny*s.width+nx;
            if(s.cell(nx,ny)==arena::HARD_WALL||blocked[next])continue;
            if(s.cell(nx,ny)==arena::SOFT_WALL||player_at(s,nx,ny))
                return -(distance[pos]+1);
            if(distance[next]>=0)continue;
            distance[next]=distance[pos]+1;queue[tail++]=next;
        }
    }
    return -CELLS;
}

inline int plan(const GameState& s,const Forecast& f,bool aggressive,arena::Rng& rng) {
    int cells=int(s.width*s.height),sx=int(s.self().x),sy=int(s.self().y),start=sy*s.width+sx;
    int selected=-1,best=-1000000;
    for(int first=0;first<=4;++first) {
        int x=sx+dx[first],y=sy+dy[first];
        if(!s.inside(x,y))continue;
        int pos=y*s.width+x;
        if(f.terrain[0][pos]!=arena::FLOOR||f.danger[0][pos]||player_at(s,x,y))continue;
        if(f.occupied[0][pos]&&pos!=start)continue;
        bool current[CELLS]{},next[CELLS]{};current[pos]=true;
        for(int t=1;t<=HORIZON;++t) {
            for(int i=0;i<cells;++i)next[i]=false;
            for(int i=0;i<cells;++i)if(current[i]) {
                int cx=i%int(s.width),cy=i/int(s.width);
                for(int d=0;d<=4;++d) {
                    int nx=cx+dx[d],ny=cy+dy[d];if(!s.inside(nx,ny))continue;
                    int dest=ny*s.width+nx;
                    if(f.terrain[t][dest]!=arena::FLOOR||f.danger[t][dest])continue;
                    // Waiting on one's current bomb is allowed; entering a bomb is not.
                    if(f.occupied[t][dest]&&dest!=i)continue;
                    next[dest]=true;
                }
            }
            for(int i=0;i<cells;++i)current[i]=next[i];
        }
        int area=0;
        for(int i=0;i<cells;++i)area+=current[i];
        if(area==0)continue;
        int score=(aggressive?100*objective(s,x,y):0)+area+(first?4:0)+int(rng.next()%3);
        if(score>best){best=score;selected=first;}
    }
    return selected;
}

inline bool useful_bomb(const GameState& s) {
    int sx=int(s.self().x),sy=int(s.self().y);
    for(uint32_t i=0;i<s.bomb_count;++i)
        if(s.bombs[i].owner_id==s.self_id||(s.bombs[i].x==s.self().x&&s.bombs[i].y==s.self().y))return false;
    for(int d=1;d<=4;++d)for(int k=1;k<=int(s.blast_range);++k) {
        int x=sx+dx[d]*k,y=sy+dy[d]*k;
        if(s.cell(x,y)==arena::HARD_WALL)break;
        if(s.cell(x,y)==arena::SOFT_WALL||player_at(s,x,y))return true;
    }
    return false;
}
}
