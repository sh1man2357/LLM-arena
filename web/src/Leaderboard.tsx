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
      {!!data.data?.items.length && <div className="table-scroll"><table><thead><tr><th>名次</th><th>Bot</th><th>局数</th><th>胜 / 平 / 负</th><th>平均得分</th>{game === 'gomoku' && <><th>执黑</th><th>执白</th></>}</tr></thead><tbody>
        {data.data.items.map(row => <tr key={row.id}><td className="ranking-position">{String(row.rank).padStart(2, '0')}</td><th scope="row">{row.name}</th><td>{row.matches}</td><td>{row.wins} / {row.draws} / {row.losses}</td><td className="ranking-score">{row.mean_score.toFixed(3)}</td>{game === 'gomoku' && <><td>{row.black_mean?.toFixed(3)}</td><td>{row.white_mean?.toFixed(3)}</td></>}</tr>)}
      </tbody></table></div>}
      <details className="ranking-rules"><summary>计分规则<ChevronDown className="disclosure-chevron" aria-hidden="true" /></summary>{game === 'gomoku' ? <><p>胜 1 分、平 0.5 分、负 0 分，按平均得分排名，同分并列。执黑、执白分别展示平均得分。</p><p>只统计两盘都完成且校验通过的换色对战。任一盘失败、中断或进入回收站，整组不计分；恢复后重新统计。自我对弈按独立槽位累计。</p></> : <><p>名次分 =（排名低于自己的对手数 + 0.5 × 与自己并列的对手数）÷ 对手总数。按平均得分排名，同分并列；双人对局仍为胜 1 分、平 0.5 分、负 0 分。</p><p>独占第一记胜，并列第一记平，其余记负。只统计本机已完成且校验通过的对局。失败、中断不计分；各 Bot 的人数、对手和局数可能不同。重复参赛的 Bot 按槽位分别累计。</p></>}</details>
    </section></>;
}
