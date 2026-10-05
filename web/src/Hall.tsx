import { Link, useSearchParams } from 'react-router-dom';
import { useResource } from './api';
import { useRevision } from './App';
import { Board } from './Board';
import { Badge, ErrorPanel, Icon, identityColor, labels, useNameLabel, PageTitle, State, LoadingPanel, ReadNotice } from './ui';
import type { Match, Replay, Row, Tournament } from './types';

export type Page<T> = { items: T[]; total?: number };
export function MatchRows({ rows }: {rows: Match[]}) {
  const nameLabel = useNameLabel();
  return <div className="match-list">{rows.map(row => <Link className="match-row" to={`/matches/${row.id}`} key={row.id}>
    <div className="match-players">{row.entrants.map((e, i) => <span key={e.id}>{i > 0 && <small className="versus-text">vs</small>}<i style={{ background: identityColor(e.id) }} /><strong>{nameLabel(e.id)}</strong></span>)}<small>{row.title}</small></div>
    <div className="match-score mono">{row.result?.valid ? row.result.players.map((p: Row) => p.placement_score).join(' : ') : '—'}</div>
    <div className="match-reason"><Badge status={row.status} /><small>{labels[row.result?.reason || ''] || '等待结果'}</small></div>
    <div className="match-ticks mono">{row.ticks}<small>Tick</small></div><Icon name="arrow" />
  </Link>)}</div>;
}

function Feature({ match }: {match: Match}) {
  const nameLabel = useNameLabel();
  const replay = useResource<Replay>(`/api/v1/matches/${match.id}/frames`);
  const index = replay.data ? Math.min(15, replay.data.frames.length - 1) : 0;
  return <Link to={`/matches/${match.id}`} className="feature-match">
    <div className="feature-copy"><div className="feature-label"><span className="eyebrow">精选对局</span><Badge status={match.status} /></div>
      <h2>{match.entrants.map((e, i) => <span key={e.id}>{i > 0 && <em>vs</em>}<strong style={{ color: identityColor(e.id) }}>{nameLabel(e.id)}</strong></span>)}</h2>
      <p>{match.title}</p><div className="feature-facts"><span><b className="mono">{match.ticks}</b>结算 Tick</span><span><b>{labels[match.result?.reason || ''] || '计算中'}</b>结束原因</span></div>
      <span className="feature-cta">进入观赛 <Icon name="arrow" /></span>
    </div><div className="feature-board">{replay.data?.frames[index] ? <Board frame={replay.data.frames[index]} entrants={replay.data.entrants} compact /> : <div className="board-loading">{replay.error ? '预览暂不可用，点击进入观赛查看状态。' : '正在读取真实回放…'}</div>}<span className="preview-caption">真实回放预览 · 点击进入</span></div>
  </Link>;
}

export function Hall() {
  const revision = useRevision();
  const [params, setParams] = useSearchParams();
  const q = params.get('q') || '', status = params.get('status') || '', offset = Number(params.get('offset') || 0);
  const matches = useResource<Page<Match>>(`/api/v1/matches?q=${encodeURIComponent(q)}&status=${status}&offset=${offset}&limit=15`, revision);
  const batches = useResource<Page<Tournament>>('/api/v1/tournaments', revision);
  const entrants = useResource<Page<Row>>('/api/v1/entrants', revision);
  function filter(key: string, value: string) { const next = new URLSearchParams(params); next.set(key, value); next.delete('offset'); setParams(next, { replace: true }); }
  if (matches.error && !matches.data) return <ErrorPanel message={matches.error} status={matches.errorStatus} onRetry={matches.retry} />;
  const feature = matches.data?.items.find(m => m.status === 'running') || matches.data?.items.find(m => m.id === 'reference-chain') || matches.data?.items[0];
  const completed = batches.data?.items.reduce((sum, b) => sum + (b.completed_matches || 0), 0) || 0;
  return <><PageTitle eyebrow="观赛大厅 / MATCH CENTER" title="让策略在场上说话。" detail="观看对抗，回到关键时刻，理解每一场的结果。"><Link className="button quiet" to="/manage"><Icon name="sliders" />主办方工作台</Link></PageTitle>
    <ReadNotice resource={matches} /><ReadNotice resource={batches} /><ReadNotice resource={entrants} />
    <div className="hall-metrics"><div><span className="metric-symbol"><Icon name="people" /></span><span><strong className="mono">{entrants.data ? entrants.data.items.filter(e => e.baseline).length : '—'}</strong><small>冻结 Baseline</small></span></div><div><span className="metric-symbol"><Icon name="grid" /></span><span><strong className="mono">{batches.data ? completed : '—'}</strong><small>已完成批次对局</small></span></div><div><span className="metric-symbol"><Icon name="check" /></span><span><strong>规则 1</strong><small>相同预算 · 可复现</small></span></div><div><span className="metric-symbol"><Icon name="bolt" /></span><span><strong className="mono">60 min</strong><small>模型限时开发 · 可提前交卷</small></span></div></div>
    {matches.loading && <LoadingPanel title="正在读取对局记录" />}
    {feature ? <Feature match={feature} /> : !matches.loading && <State title="竞技场已就绪" detail="还没有对局。进入工作台导入参考赛或创建新比赛。"><Link className="button primary" to="/manage">开始准备 <Icon name="arrow" /></Link></State>}
    {!!batches.data?.items.length && <section className="batch-strip"><div className="section-heading"><h2>比赛批次</h2><Link to="/tournaments">全部批次 <Icon name="arrow" /></Link></div><div className="batch-cards">{batches.data.items.slice(0, 3).map(b => <Link className="batch-card" to={`/tournaments/${b.id}`} key={b.id}><div><Badge status={b.status} /><span className="mono muted">{b.completed_matches} / {b.expected_matches}</span></div><h3>{b.title}</h3><p>{b.official ? '正式隐藏集' : '公开工程参考赛'} · {b.report?.entrants?.length || '—'} 名参赛者</p><div className="progress-track"><span style={{ width: `${b.completed_matches / (b.expected_matches || 1) * 100}%` }} /></div></Link>)}</div></section>}
    <section className="matches-section"><div className="section-heading"><h2>对局记录 <span className="mono muted count">{matches.data?.total || 0}</span></h2><div className="filter-controls"><input aria-label="搜索对局" placeholder="搜索对局…" value={q} onChange={e => filter('q', e.target.value)} /><select aria-label="对局状态" value={status} onChange={e => filter('status', e.target.value)}><option value="">全部状态</option><option value="running">进行中</option><option value="completed">已结束</option><option value="failed">失败</option></select></div></div>
      {matches.data?.items.length ? <><MatchRows rows={matches.data.items} /><div className="pagination"><button disabled={offset === 0} onClick={() => { const p = new URLSearchParams(params); p.set('offset', String(Math.max(0, offset - 15))); setParams(p); }}>上一页</button><span className="muted mono">{offset + 1}–{Math.min(offset + 15, matches.data.total || 0)} / {matches.data.total}</span><button disabled={offset + 15 >= (matches.data.total || 0)} onClick={() => { const p = new URLSearchParams(params); p.set('offset', String(offset + 15)); setParams(p); }}>下一页</button></div></> : !matches.loading && <State title={q || status ? '没有符合筛选条件的对局' : '暂无对局记录'} detail={q || status ? '调整条件或清除筛选，继续浏览比赛。' : '可以进入工作台创建比赛。'}>{(q || status) && <button onClick={() => { const next = new URLSearchParams(params); next.delete('q'); next.delete('status'); next.delete('offset'); setParams(next); }}>清除筛选</button>}</State>}
    </section></>;
}

export function Batches() {
  const data = useResource<Page<Tournament>>('/api/v1/tournaments', useRevision());
  if (data.error && !data.data) return <ErrorPanel message={data.error} status={data.errorStatus} onRetry={data.retry} />;
  return <><PageTitle eyebrow="批次 / TOURNAMENTS" title="每一轮，都有完整证据。" detail="成绩只在同一规则、同一对手池和完整调度内比较。" /><ReadNotice resource={data} />{data.loading && <LoadingPanel title="正在读取比赛批次" />}<div className="batch-cards expanded">{data.data?.items.map(b => <Link className="batch-card" to={`/tournaments/${b.id}`} key={b.id}><Badge status={b.status} /><h2>{b.title}</h2><p>{b.completed_matches} / {b.expected_matches} 局 · {b.official ? '正式比赛' : '工程参考赛'}</p><span>进入批次 <Icon name="arrow" /></span></Link>)}</div>{data.data && !data.data.items.length && <State title="还没有比赛批次" detail="在主办方工作台导入参考赛或启动全配对。"><Link className="button primary" to="/manage">进入工作台</Link></State>}</>;
}
