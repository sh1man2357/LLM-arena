import { ChevronDown } from 'lucide-react';
import { useResource } from './api';
import { useRevision } from './App';
import { ErrorPanel } from './ui';
import type { Ranking } from './types';

export function Leaderboard() {
  const data = useResource<{items: Ranking[]; valid_matches: number}>('/api/v1/leaderboard', useRevision());
  return <><div className="page-heading"><h1>本地榜单</h1></div>
    {data.error && <ErrorPanel message={data.error} onRetry={data.retry} />}
    <section aria-label="Bot 排名">
      {data.loading && <p role="status">正在读取榜单…</p>}
      {data.data && !data.data.items.length && <p className="empty" role="status">暂无成绩</p>}
      {!!data.data?.items.length && <div className="table-scroll"><table><thead><tr><th>名次</th><th>Bot</th><th>局数</th><th>胜 / 平 / 负</th><th>平均得分</th></tr></thead><tbody>
        {data.data.items.map(row => <tr key={row.id}><td className="ranking-position">{String(row.rank).padStart(2, '0')}</td><th scope="row">{row.name}</th><td>{row.matches}</td><td>{row.wins} / {row.draws} / {row.losses}</td><td className="ranking-score">{row.mean_score.toFixed(3)}</td></tr>)}
      </tbody></table></div>}
      <details className="ranking-rules"><summary>计分规则<ChevronDown className="disclosure-chevron" aria-hidden="true" /></summary><p>名次分 =（排名低于自己的对手数 + 0.5 × 与自己并列的对手数）÷ 对手总数。按平均得分排名，同分并列；双人对局仍为胜 1 分、平 0.5 分、负 0 分。</p><p>独占第一记胜，并列第一记平，其余记负。只统计本机已完成且校验通过的对局。失败、中断不计分；各 Bot 的人数、对手和局数可能不同。重复参赛的 Bot 按槽位分别累计。</p></details>
    </section></>;
}
