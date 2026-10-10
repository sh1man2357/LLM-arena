import { Link } from 'react-router-dom';
import { useResource } from './api';
import { useRevision } from './App';
import { ErrorPanel } from './ui';
import type { Ranking } from './types';

export function Leaderboard() {
  const data = useResource<{items: Ranking[]; valid_matches: number}>('/api/v1/leaderboard', useRevision());
  return <><div className="page-heading"><Link to="/">← 返回首页</Link><h1>本地榜单</h1>
    <p className="muted">胜 1 分 · 平 0.5 分 · 负 0 分，按平均得分排名，同分并列。</p></div>
    {data.error && <ErrorPanel message={data.error} onRetry={data.retry} />}
    <section className="panel"><p className="muted">只统计本机完成并验证通过的单局，失败与中断不计分。不同 Bot 的对手和局数可能不同。</p>
      {data.loading && <p role="status">正在读取榜单…</p>}
      {data.data && !data.data.items.length && <p className="empty" role="status">暂无有效对局，运行结束后自动统计。</p>}
      {!!data.data?.items.length && <div className="table-scroll"><table><thead><tr><th>名次</th><th>Bot</th><th>局数</th><th>胜</th><th>平</th><th>负</th><th>平均得分</th></tr></thead><tbody>
        {data.data.items.map(row => <tr key={row.id}><td>{row.rank}</td><th scope="row">{row.name}</th><td>{row.matches}</td><td>{row.wins}</td><td>{row.draws}</td><td>{row.losses}</td><td>{row.mean_score.toFixed(3)}</td></tr>)}
      </tbody></table></div>}
    </section></>;
}
