import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useResource } from './api';
import { useRevision } from './App';
import { MatchRows, type Page } from './Hall';
import { Badge, ErrorPanel, Icon, identityColor, labels, useNameLabel, PageTitle, State } from './ui';
import type { Match, Row, Tournament } from './types';

export function Batch() {
  const nameLabel = useNameLabel();
  const { id } = useParams(); const revision = useRevision(); const [params, setParams] = useSearchParams();
  const batch = useResource<Tournament>(`/api/v1/tournaments/${id}`, revision);
  const pair = params.get('pair')?.split(','); const caseIndex = params.get('case');
  const matches = useResource<Page<Match>>(`/api/v1/matches?tournament_id=${id}&limit=100${pair ? `&entrant=${pair[0]}&opponent=${pair[1]}` : ''}${caseIndex !== null ? `&case_index=${caseIndex}` : ''}`, revision);
  const analysis = useResource<Row>(`/api/v1/tournaments/${id}/analysis`, revision);
  if (batch.error) return <ErrorPanel message={batch.error} />;
  if (!batch.data) return <State title="正在读取批次" />;
  const b = batch.data; const report = b.report || { pairs: [], entrants: [] };
  const rows: Row[] = [...(report.entrants || [])].sort((a, c) => c.mean_placement - a.mean_placement);
  const pairs: Row[] = report.pairs || [];
  const selected = pairs.find(p => pair && p.entrant === pair[0] && p.opponent === pair[1]) || pairs[0];
  function selectPair(a: string, other: string) { const next = new URLSearchParams(params); next.set('pair', `${a},${other}`); next.delete('case'); setParams(next); }
  return <><PageTitle eyebrow="批次详情 / TOURNAMENT" title={b.title} detail={`${b.official ? '正式隐藏集' : '公开工程验收 · 手写 Baseline 参照'} · ${b.id}`}><Badge status={b.status} /></PageTitle>
    <div className="batch-status panel"><span><strong className="mono">{b.completed_matches} / {b.expected_matches}</strong> 局完成</span><div className="progress-track"><span style={{ width: `${b.completed_matches / (b.expected_matches || 1) * 100}%` }} /></div><span>{b.disclosure === 'sealed' ? '案例封存' : '地图已披露'}</span>{b.status === 'complete' && <a className="button quiet" href={`/api/v1/exports/${id}?kind=report`}><Icon name="share" />导出报告</a>}</div>
    {report.status !== 'complete' && <div className="notice"><Icon name="info" />当前批次尚未完成。这里只显示进度和单局事实，不发布正式汇总排名。</div>}
    {report.status === 'complete' && <><div className="analysis-grid"><section className="panel standings"><div className="section-heading"><h2>批次榜单</h2><span className="muted">平均名次分</span></div><div className="ranking-head"><span>排名 / 参赛者</span><span>胜 · 负 · 平</span><span>得分</span></div>{rows.map(r => {
      const rank = rows.findIndex(item => item.mean_placement === r.mean_placement) + 1;
      const details = pairs.filter(p => p.entrant === r.id);
      return <Link className="ranking-row" key={r.id} to={`/entrants/${r.id}`}><span className="rank mono">{String(rank).padStart(2, '0')}</span><span className="ranking-name"><i style={{ background: identityColor(r.id) }} /><strong>{nameLabel(r.id)}</strong><small>{r.opponent_count} 个对手</small></span><span className="mono ranking-wld">{details.reduce((s,p) => s+p.wins,0)} / {details.reduce((s,p) => s+p.losses,0)} / {details.reduce((s,p) => s+p.draws,0)}</span><strong className="mono ranking-score">{r.mean_placement.toFixed(3)}</strong></Link>;
    })}<p className="small muted">相同分数保持并列。此处是批次成绩，不是长期 Rating。</p></section>
    <section className="panel matrix"><div className="section-heading"><h2>对战矩阵</h2><span className="muted">点击检查配对</span></div><div className="table-scroll"><table><thead><tr><th>对手 →</th>{rows.map(r => <th key={r.id}>{nameLabel(r.id)}</th>)}</tr></thead><tbody>{rows.map(r => <tr key={r.id}><th>{nameLabel(r.id)}</th>{rows.map(other => { const p = pairs.find(p => p.entrant === r.id && p.opponent === other.id); return <td key={other.id}>{p ? <button className={`matrix-cell ${selected?.entrant === r.id && selected?.opponent === other.id ? 'active' : ''}`} onClick={() => selectPair(r.id, other.id)}><strong className="mono">{p.mean_placement.toFixed(2)}</strong><small>{p.wins} / {p.losses} / {p.draws}</small></button> : <span className="matrix-self">—</span>}</td>; })}</tr>)}</tbody></table></div><p className="small muted">行参赛者的均分 · 胜 / 负 / 平。每张地图两局换边。</p></section></div>
    {selected && <section className="panel pair-analysis"><div className="section-heading"><h2>{nameLabel(selected.entrant)} <span className="muted">vs</span> {nameLabel(selected.opponent)}</h2><Badge status="complete">{selected.matches} 局有效</Badge></div>
      <div className="pair-metrics"><div><small>平均名次分</small><strong className="mono">{selected.mean_placement.toFixed(3)}</strong></div><div><small>95% 地图区间</small><strong className="mono">{selected.ci95 ? `${selected.ci95[0].toFixed(3)} — ${selected.ci95[1].toFixed(3)}` : '样本不足'}</strong></div><div><small>出生槽位 0 / 1</small><strong className="mono">{selected.spawn_mean.map((v: number) => v.toFixed(3)).join(' / ')}</strong></div><div><small>平均结算 Tick</small><strong className="mono">{selected.mean_ticks.toFixed(1)}</strong></div></div>
      <div className="case-chart"><div><h3>地图换边组合</h3><p className="muted small">每点是同地图两局的均分。点击查看对应案例。</p></div><div className="case-dots">{selected.case_means.map((v: number, i: number) => <button key={i} className={`case-dot ${String(i) === caseIndex ? 'selected' : ''}`} style={{ '--score': v } as React.CSSProperties} title={`案例 ${i+1}，均分 ${v}`} aria-label={`地图案例 ${i+1}，均分 ${v}`} onClick={() => { const next = new URLSearchParams(params); next.set('pair', `${selected.entrant},${selected.opponent}`); next.set('case', String(i)); setParams(next); }}><i /><span className="mono">{i+1}</span></button>)}</div></div>
      <details className="statistics-details"><summary>故障与行为统计</summary><div className="stat-chips">{Object.entries({ '放置炸弹': selected.stats.bombs_placed, '爆炸死亡': selected.stats.explosion_deaths, '动作故障': selected.stats.action_faults, 'fuel 耗尽': selected.stats.fuel_exhaustions, '运行淘汰': selected.stats.runtime_eliminations, '初始化失败': selected.stats.initialization_failures }).map(([k,v]) => <span key={k}>{k}<b className="mono">{String(v)}</b></span>)}</div><p className="muted small">动作故障率 {(selected.rates.action_faults_per_call * 100).toFixed(2)}%（分母：调用次数）；运行淘汰率 {(selected.rates.runtime_eliminations_per_match * 100).toFixed(2)}%（分母：有效对局）。区间只反映地图变化，不反映重新生成代码的波动。</p></details>
    </section>}
    {analysis.data && <section className="panel draw-analysis"><div className="section-heading"><h2>结束原因与平局</h2><span className="muted">根据真实记录</span></div><div className="stat-chips">{Object.entries(analysis.data.reasons || {}).map(([k,v]) => <span key={k}>{labels[k] || k}<b className="mono">{String(v)}</b></span>)}</div><p className="muted small">平局 {analysis.data.draws} 局 · 放弹 {analysis.data.bombs_placed} 次 · 成功移动 {analysis.data.moves} 次 · 受阻移动 {analysis.data.blocked_moves} 次。分析不会改变成绩或推断 Bot 的意图。</p></section>}
    </>}
    <section className="matches-section"><div className="section-heading"><h2>{caseIndex !== null ? `地图案例 ${Number(caseIndex)+1}` : pair ? '配对对局' : '批次对局'}</h2>{(pair || caseIndex !== null) && <button className="quiet" onClick={() => setParams({})}>清除配对筛选</button>}</div>{matches.error ? <ErrorPanel message={matches.error} /> : matches.data?.items.length ? <MatchRows rows={matches.data.items} /> : <p className="empty-note muted">尚无符合条件的对局。</p>}{(matches.data?.total || 0) > 100 && <p className="muted small">当前显示最新 100 局，可从矩阵或地图案例定位，全部记录可在大厅筛选。</p>}</section>
  </>;
}
