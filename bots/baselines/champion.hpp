#pragma once
#include "arena.hpp"
#include <algorithm>

namespace champion {
constexpr int CELLS=961,HORIZON=6,NEVER=255;
constexpr int dx[5]={0,0,1,0,-1},dy[5]={0,-1,0,1,0};
inline int adjacent[CELLS][5],visited[CELLS],stamp=0;
inline int distance[CELLS],previous=-1,older=-1,work;
inline uint32_t graph_width=0,graph_height=0;
inline bool blocked[CELLS];
inline int WORK_LIMIT=900000;
struct Forecast {
    uint32_t danger[CELLS]{};
    uint8_t open[CELLS]{},until[CELLS]{},born[CELLS]{};
};
inline void prepare(const GameState& s) {
    work=12000;
    WORK_LIMIT=s.width*s.height>400?700000:900000;
    for(int i=0;i<int(s.width*s.height);++i) {
        blocked[i]=false;
        if(graph_width!=s.width||graph_height!=s.height) {
            int x=i%int(s.width),y=i/int(s.width);
            adjacent[i][0]=i;adjacent[i][1]=y?i-int(s.width):-1;
            adjacent[i][2]=x+1<int(s.width)?i+1:-1;
            adjacent[i][3]=y+1<int(s.height)?i+int(s.width):-1;
            adjacent[i][4]=x?i-1:-1;
        }
    }
    graph_width=s.width;graph_height=s.height;
    for(uint32_t p=0;p<s.player_count;++p)if(p!=s.self_id&&s.players[p].alive)
        blocked[s.players[p].y*s.width+s.players[p].x]=true;
}
// Each cell records opening time and danger bits. No full terrain copy per tick.
inline Forecast forecast(const GameState& s,int placement=-1,int when=0) {
    Forecast out;int cells=s.width*s.height;
    for(int i=0;i<cells;++i)out.open[i]=s.grid[i]==arena::FLOOR?0:NEVER;
    arena::Bomb bombs[10];bool live[10]{};int birth[10]{};
    int at[CELLS];for(int i=0;i<cells;++i)at[i]=-1;
    int count=s.bomb_count;
    for(int i=0;i<count;++i){bombs[i]=s.bombs[i];live[i]=true;}
    if(placement>=0) {
        bombs[count]={0,s.self_id,uint32_t(placement%int(s.width)),uint32_t(placement/int(s.width)),s.tick+s.bomb_fuse_ticks+uint32_t(when),s.blast_range};
        birth[count]=when;live[count++]=true;
    }
    for(int i=0;i<count;++i){
        int pos=bombs[i].y*s.width+bombs[i].x;at[pos]=i;out.until[pos]=NEVER;out.born[pos]=birth[i];
    }
    work+=cells*12+count*120;
    for(int t=0;t<=HORIZON;++t) {
        bool explode[10]{},done[10]{},changed=true;
        for(int i=0;i<count;++i)if(live[i]&&bombs[i].explode_at_tick<=s.tick+uint32_t(t))explode[i]=true;
        while(changed) {
            changed=false;
            for(int i=0;i<count;++i)if(explode[i]&&!done[i]) {
                done[i]=true;changed=true;work+=80;
                int pos=bombs[i].y*s.width+bombs[i].x;
                out.danger[pos]|=1u<<t;
                for(int d=1;d<=4;++d) {
                    int j=pos;
                    for(int k=1;k<=int(bombs[i].range);++k) {
                        j=adjacent[j][d];work+=38;
                        if(j<0||s.grid[j]==arena::HARD_WALL)break;
                        out.danger[j]|=1u<<t;
                        // Destruction only opens the cell for the next settlement.
                        if(s.grid[j]==arena::SOFT_WALL&&out.open[j]>t){
                            out.open[j]=t+1;break;
                        }
                        if(at[j]>=0&&live[at[j]]&&birth[at[j]]<=t){explode[at[j]]=true;break;}
                    }
                }
            }
        }
        for(int i=0;i<count;++i)if(explode[i]) {
            live[i]=false;out.until[bombs[i].y*s.width+bombs[i].x]=t+1;
        }
    }
    return out;
}
inline bool safe(const Forecast& f,int j,int t,int from) {
    return j>=0&&f.open[j]<=t&&!(f.danger[j]&(1u<<t))&&(f.until[j]<=t||f.born[j]>t||j==from);
}
// Optimistic opponent paths ignore moving players; own paths avoid their cells.
inline int reachable(const GameState& s,const Forecast& f,int start,int first,bool own=true,int* ends=nullptr,int fixed=-1) {
    int a[CELLS],b[CELLS],n=1;a[0]=start;bool pruned=false;
    int limit=s.width*s.height>400?32:80;
    for(int t=first;t<=HORIZON;++t) {
        int next=0;++stamp;
        for(int k=0;k<n;++k)for(int d=0;d<=4;++d) {
            int j=adjacent[a[k]][d];work+=42;
            if(j<0||visited[j]==stamp||!safe(f,j,t,a[k])||(own&&blocked[j])||j==fixed)continue;
            visited[j]=stamp;
            if(next<limit)b[next++]=j;else pruned=true;
        }
        n=next;for(int k=0;k<n;++k)a[k]=b[k];
        if(!n)break;
    }
    if(ends)for(int k=0;k<n;++k)ends[k]=a[k];
    // Truncating a large enemy frontier may lose an escape; it cannot prove a kill.
    return !own&&pruned?std::max(n,limit):n;
}
// Reverse weighted routes choose walls that actually lead toward opponents.
inline void targets(const GameState& s) {
    int heads[8],pos[CELLS*4+8],next_entry[CELLS*4+8],entries=0,active=0,cells=s.width*s.height;
    for(int& h:heads)h=-1;
    auto push=[&](int vertex,int value){
        int e=entries++;next_entry[e]=heads[value&7];heads[value&7]=e;
        // Stored separately because a vertex can be queued again at a lower cost.
        // At most one insertion per directed edge is needed.
        pos[e]=vertex;++active;
    };
    for(int i=0;i<cells;++i)distance[i]=CELLS*8;
    for(uint32_t p=0;p<s.player_count;++p)if(p!=s.self_id&&s.players[p].alive){
        int j=s.players[p].y*s.width+s.players[p].x;distance[j]=0;push(j,0);
    }
    int v=0;
    while(active) {
        while(heads[v&7]<0)++v;
        int entry=heads[v&7];heads[v&7]=next_entry[entry];--active;
        int i=pos[entry];
        if(v!=distance[i])continue;
        work+=100;
        for(int d=1;d<=4;++d){
            int j=adjacent[i][d];work+=35;
            if(j<0||s.grid[j]==arena::HARD_WALL)continue;
            int next=v+(s.grid[i]==arena::SOFT_WALL?6:1);
            if(next<distance[j]){distance[j]=next;push(j,next);}
        }
    }
}
inline bool available(const GameState& s,uint32_t owner,int pos) {
    for(uint32_t i=0;i<s.bomb_count;++i)
        if(s.bombs[i].owner_id==owner||int(s.bombs[i].y*s.width+s.bombs[i].x)==pos)return false;
    return true;
}
inline int attack(const GameState& s,const Forecast& base,const Forecast& bomb,int pos,int first) {
    int score=0;
    for(uint32_t p=0;p<s.player_count&&work<WORK_LIMIT-125000;++p)if(p!=s.self_id&&s.players[p].alive) {
        int start=s.players[p].y*s.width+s.players[p].x;
        int proximity=abs(start%int(s.width)-pos%int(s.width))+abs(start/int(s.width)-pos/int(s.width));
        if(proximity>int(s.blast_range+s.bomb_fuse_ticks+first))continue;
        int before=reachable(s,base,start,0,false);
        int after=reachable(s,bomb,start,0,false);
        if(before&&after==0)score+=20000;
        else if(before>after)score+=(before-after)*180/std::max(1,before);
    }
    return score;
}
inline int choose(const GameState& s,arena::Rng& rng) {
    prepare(s);targets(s);
    int start=s.self().y*s.width+s.self().x;
    auto base=forecast(s);
    auto enemy=s;int considered=0;
    for(uint32_t p=0;p<s.player_count&&considered<2;++p)if(p!=s.self_id&&s.players[p].alive){
        int pos=s.players[p].y*s.width+s.players[p].x;
        int range=abs(int(s.self().x)-int(s.players[p].x))+abs(int(s.self().y)-int(s.players[p].y));
        if(!available(s,p,pos)||range>int(s.blast_range+s.bomb_fuse_ticks))continue;
        enemy.bombs[enemy.bomb_count++]={0,p,s.players[p].x,s.players[p].y,s.tick+s.bomb_fuse_ticks,s.blast_range};++considered;
    }
    auto threat=considered?forecast(enemy):base;
    int scores[6],areas[5]{},best=-10000000,selected=0;
    for(int d=0;d<=4;++d){
        scores[d]=-10000000;int j=adjacent[start][d];
        if(!safe(base,j,0,start)||blocked[j])continue;
        int area=reachable(s,base,j,1);if(!area)continue;
        int robust=considered?reachable(s,threat,j,1):area;
        int risk=0;
        for(uint32_t p=0;p<s.player_count;++p)if(p!=s.self_id&&s.players[p].alive)
            if(abs(j%int(s.width)-int(s.players[p].x))+abs(j/int(s.width)-int(s.players[p].y))==1)risk+=25;
        // In a free-for-all, stay mobile instead of charging into several opponents.
        int score=-distance[j]*(s.player_count>2?20:70)+std::min(area,60)*3+std::min(robust,30)*12-risk+(d?4:0)+int(rng.next()%3);
        if(!robust)score-=20000;
        if(j==older&&j!=start)score-=20;
        areas[d]=area;scores[d]=score;
        if(score>best){best=score;selected=d;}
    }
    bool can_bomb=available(s,s.self_id,start)&&s.bomb_fuse_ticks<=HORIZON;
    if(can_bomb) {
        auto bomb=forecast(s,start),counter=considered?forecast(enemy,start):bomb;
        if(safe(bomb,start,0,start)&&reachable(s,bomb,start,1)>=2&&safe(counter,start,0,start)&&reachable(s,counter,start,1)>=2){
            int walls=0,targets_hit=0;
            for(int d=1;d<=4;++d){
                int j=start;
                for(uint32_t k=1;k<=s.blast_range;++k){
                    j=adjacent[j][d];if(j<0||s.grid[j]==arena::HARD_WALL)break;
                    if(s.grid[j]==arena::SOFT_WALL){walls+=distance[j]<distance[start];break;}
                    targets_hit+=blocked[j];
                    if(base.until[j])break;
                }
            }
            int pressure=attack(s,base,bomb,start,0);
            if(pressure>=20000||walls||(targets_hit&&pressure>=35)){
                older=previous;previous=start;return int(Action::BOMB);
            }
        }
    }
    // Body-block a sole exit only when holding that cell is safe through detonation.
    for(int d=0;d<=4&&work<WORK_LIMIT-160000;++d)if(areas[d]){
        int pos=adjacent[start][d];
        if(base.danger[pos]||threat.danger[pos])continue;
        int bonus=0;
        for(uint32_t p=0;p<s.player_count&&work<WORK_LIMIT-130000;++p)if(p!=s.self_id&&s.players[p].alive){
            int j=s.players[p].y*s.width+s.players[p].x;
            if(abs(j%int(s.width)-pos%int(s.width))+abs(j/int(s.width)-pos/int(s.width))>3)continue;
            int free=reachable(s,base,j,0,false),held=reachable(s,base,j,0,false,nullptr,pos);
            if(free&&!held)bonus+=15000;
        }
        scores[d]+=bonus;
        if(scores[d]>best){best=scores[d];selected=d;}
    }
    // Evaluate move-then-bomb traps. Finish each candidate before replacing the fallback.
    if(can_bomb)for(int d=1;d<=4&&work<WORK_LIMIT-130000;++d)if(areas[d]){
        int pos=adjacent[start][d];auto bomb=forecast(s,pos,1);
        if(!safe(bomb,pos,1,pos)||reachable(s,bomb,pos,2)<2)continue;
        int pressure=attack(s,base,bomb,pos,1);
        scores[d]+=pressure>=20000?10000:pressure/2;
        if(scores[d]>best){best=scores[d];selected=d;}
    }
    // A two-step route can reach a corner from which one bomb cuts two corridors.
    // Cache duplicate destinations reached by different first moves.
    int opportunity[CELLS];for(int i=0;i<int(s.width*s.height);++i)opportunity[i]=-1;
    if(can_bomb&&s.bomb_fuse_ticks+2<=HORIZON)
        for(int d=0;d<=4&&work<WORK_LIMIT-140000;++d)if(areas[d]){
            int first=adjacent[start][d],bonus=0;
            for(int next=0;next<=4&&work<WORK_LIMIT-140000;++next){
                int pos=adjacent[first][next];
                if(!safe(base,pos,1,first)||blocked[pos]||!available(s,s.self_id,pos))continue;
                if(opportunity[pos]<0){
                    auto bomb=forecast(s,pos,2);
                    opportunity[pos]=0;
                    if(safe(bomb,pos,2,pos)&&reachable(s,bomb,pos,3)>=2){
                        int pressure=attack(s,base,bomb,pos,2);
                        opportunity[pos]=pressure>=20000?7000:pressure/3;
                    }
                }
                bonus=std::max(bonus,opportunity[pos]);
            }
            scores[d]+=bonus;
            if(scores[d]>best){best=scores[d];selected=d;}
        }
    older=previous;previous=start;return selected;
}
}
