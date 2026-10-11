#pragma once
#include "planner.hpp"
#include <algorithm>

namespace champion {
using namespace planning;
inline int visited[CELLS],stamp=0;
inline bool blocked[CELLS];
inline int distance[CELLS];
inline int previous=-1,older=-1;
inline void targets(const GameState& s) {
    int queue[CELLS],head=0,tail=0,cells=s.width*s.height;bool bombs[CELLS]{};
    for(uint32_t i=0;i<s.bomb_count;++i)bombs[s.bombs[i].y*s.width+s.bombs[i].x]=true;
    for(int i=0;i<cells;++i) {
        distance[i]=CELLS;
        if(s.grid[i]==arena::SOFT_WALL||blocked[i]){distance[i]=0;queue[tail++]=i;}
    }
    while(head<tail) {
        int i=queue[head++],x=i%int(s.width),y=i/int(s.width);
        for(int d=1;d<=4;++d) {
            int nx=x+dx[d],ny=y+dy[d];if(!s.inside(nx,ny))continue;
            int j=ny*s.width+nx;
            if(s.grid[j]!=arena::FLOOR||bombs[j]||distance[j]!=CELLS)continue;
            distance[j]=distance[i]+1;queue[tail++]=j;
        }
    }
    int start=s.self().y*s.width+s.self().x;
    if(bombs[start])for(int d=1;d<=4;++d) {
        int x=int(s.self().x)+dx[d],y=int(s.self().y)+dy[d];
        if(s.inside(x,y))distance[start]=std::min(distance[start],distance[y*s.width+x]+1);
    }
}
// Compact time-expanded frontiers avoid scanning the entire map for each step.
inline int reachable(const GameState& s,const Forecast& f,int start,int first,int* end=nullptr) {
    int a[CELLS],b[CELLS],n=1;a[0]=start;
    for(int t=first;t<=HORIZON;++t) {
        int next=0;++stamp;
        for(int k=0;k<n;++k) {
            int pos=a[k],x=pos%int(s.width),y=pos/int(s.width);
            for(int d=0;d<=4;++d) {
                int nx=x+dx[d],ny=y+dy[d];if(!s.inside(nx,ny))continue;
                int j=ny*s.width+nx;
                if(visited[j]==stamp||f.terrain[t][j]!=arena::FLOOR||f.danger[t][j]||(f.occupied[t][j]&&j!=pos)||blocked[j])continue;
                visited[j]=stamp;b[next++]=j;
            }
        }
        n=next;for(int k=0;k<n;++k)a[k]=b[k];if(!n)break;
    }
    if(end)for(int k=0;k<n;++k)end[k]=a[k];
    return n;
}
inline int choose(const GameState& s,arena::Rng& rng) {
    for(uint32_t i=0;i<s.width*s.height;++i)blocked[i]=false;
    for(uint32_t p=0;p<s.player_count;++p)if(p!=s.self_id&&s.players[p].alive)
        blocked[s.players[p].y*s.width+s.players[p].x]=true;
    auto f=forecast(s,false);int start=s.self().y*s.width+s.self().x;
    auto enemy=s;int considered=0;
    for(uint32_t p=0;p<s.player_count&&considered<2;++p)if(p!=s.self_id&&s.players[p].alive) {
        int distance=std::abs(int(s.self().x)-int(s.players[p].x))+std::abs(int(s.self().y)-int(s.players[p].y));
        bool available=true;for(uint32_t j=0;j<s.bomb_count;++j)if(s.bombs[j].owner_id==p)available=false;
        if(!available||distance>int(s.blast_range+s.bomb_fuse_ticks))continue;
        enemy.bombs[enemy.bomb_count++]={0,p,s.players[p].x,s.players[p].y,s.tick+s.bomb_fuse_ticks,s.blast_range};++considered;
    }
    auto threat=considered?forecast(enemy,false):f;
    if(useful_bomb(s)) {
        // Hypothetical opponent bombs can change chain timing and terrain.
        // Escape must also work when those opponents do not place bombs.
        auto actual=forecast(s,true);
        auto bomb=forecast(enemy,true);
        if(!actual.danger[0][start] && reachable(s,actual,start,1)>=2 &&
           !bomb.danger[0][start] && reachable(s,bomb,start,1)>=2) {
            int walls=0,targets=0;
            for(int d=1;d<=4;++d)for(int k=1;k<=int(s.blast_range);++k) {
                int x=int(s.self().x)+dx[d]*k,y=int(s.self().y)+dy[d]*k;
                if(!s.inside(x,y)||s.cell(x,y)==arena::HARD_WALL)break;
                if(s.cell(x,y)==arena::SOFT_WALL){++walls;break;}
                if(player_at(s,x,y))++targets;
            }
            if(walls||(targets&&reachable(s,bomb,start,1)>=12)) {older=previous;previous=start;return int(Action::BOMB);}
        }
    }
    bool walls_left=false;for(uint32_t i=0;i<s.width*s.height;++i)walls_left|=s.grid[i]==arena::SOFT_WALL;
    targets(s);
    int best=-10000000,selected=0;
    for(int d=0;d<=4;++d) {
        int x=int(s.self().x)+dx[d],y=int(s.self().y)+dy[d];if(!s.inside(x,y))continue;
        int j=y*s.width+x;
        if(f.terrain[0][j]!=arena::FLOOR||f.danger[0][j]||(f.occupied[0][j]&&j!=start)||player_at(s,x,y))continue;
        int area=reachable(s,f,j,1);if(!area)continue;
        int risk=0;
        for(uint32_t p=0;p<s.player_count;++p)if(p!=s.self_id&&s.players[p].alive) {
            int distance=std::abs(x-int(s.players[p].x))+std::abs(y-int(s.players[p].y));
            // Simultaneous movement may contend for cells next to another player.
            if(distance==1)risk+=25;
        }
        int robust=considered?reachable(s,threat,j,1):area;
        int score=-(walls_left?100:20)*distance[j]+area*3+std::min(robust,30)*12-risk+(d?4:0)+int(rng.next()%3);
        if(!robust)score-=20000;
        if(j==older&&j!=start)score-=20;
        if(score>best){best=score;selected=d;}
    }
    older=previous;previous=start;return selected;
}
}
