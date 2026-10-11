import { ChevronDown } from 'lucide-react';
import { useState } from 'react';
import { useResource } from './api';
import { useRevision } from './App';
import { ErrorPanel } from './ui';
import type { Ranking, GameId } from './types';
import { gameNames, savedGame } from './games';

export function Leaderboard() {
  const [game, setGame] = useState<GameId>(savedGame);
  const data = useResource<{items: Ranking[]; valid_matches: number}>(`/api/v1/leaderboard?game_id=${game}`, useRevision());
  return <><div className="page-heading"><h1>本地榜单</h1></div>
    <label className="game-picker">榜单游戏<select aria-label="榜单游戏" value={game} onChange={e => {setGame(e.target.value as GameId);sessionStorage.setItem('arena.game',e.target.value);}}>{Object.entries(gameNames).map(([id,name]) => <option key={id} value={id}>{name}</option>)}</select></label>
    {data.error && <ErrorPanel message={data.error} onRetry={data.retry} />}
    <section aria-label="Bot 排名">
      {data.loading && <p role="status">正在读取榜单…</p>}
      {data.data && !data.data.items.length && <p className="empty" role="status">暂无成绩</p>}
      {!!data.data?.items.length && <div className="table-scroll"><table><thead><tr><th>名次</th><th>Bot</th><th>实力分</th><th>局数</th><th>胜 / 平 / 负</th><th>平均名次分</th>{game === 'gomoku' && <><th>执黑</th><th>执白</th></>}</tr></thead><tbody>
        {data.data.items.map(row => <tr key={row.id}><td className="ranking-position">{row.rank == null ? '—' : String(row.rank).padStart(2, '0')}</td><th scope="row">{row.baseline ? '基准 BOT' : row.name}</th><td className="ranking-score">{row.rating == null ? '待定' : `${row.rating > 0 ? '+' : ''}${row.rating.toFixed(2)}`}</td><td>{row.matches}</td><td>{row.wins} / {row.draws} / {row.losses}</td><td>{row.mean_score?.toFixed(3) ?? '—'}</td>{game === 'gomoku' && <><td>{row.black_mean?.toFixed(3) ?? '—'}</td><td>{row.white_mean?.toFixed(3) ?? '—'}</td></>}</tr>)}
      </tbody></table></div>}
      <details className="ranking-rules"><summary>计分规则<ChevronDown className="disclosure-chevron" aria-hidden="true" /></summary><p>每种游戏的基准 BOT 实力分固定为 0。实力分根据有效对战及对手强度计算，高于基准为正、低于基准为负，按实力分排名，同分并列。尚未通过直接或间接对战关联当前基准的 Bot 显示“待定”。</p><p>实力分使用带收缩的 Bradley–Terry 模型；每局按槽位两两比较，多人对局按对手数量分摊权重。同一快照自我对战不改变实力分。记录删除、恢复后重新计算，两种游戏的分数分别估计。</p>{game === 'gomoku' ? <><p>平均名次分：胜 1、平 0.5、负 0；执黑、执白分别展示。只统计两盘都完成且校验通过的换色对战。任一盘失败、中断或进入回收站，整组不计分。</p></> : <><p>局内积分：回合结算后仍存活 +1 分，击杀 +100 分，按总积分排名，同分并列。共同命中的不同敌方炸弹主人各得击杀分，自杀不加分。局内积分与榜单实力分分别计算。</p><p>平均名次分使用归一化排名。独占第一记胜，并列第一记平，其余记负。只统计当前积分规则下已完成且校验通过的对局；旧规则比赛保留回放和重赛。重复参赛按槽位累计，多人胜平负不等同于两两比较结果。</p></>}</details>
    </section></>;
}
