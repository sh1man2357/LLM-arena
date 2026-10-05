import { Link, useParams } from 'react-router-dom';
import { useResource } from './api';
import { useRevision } from './App';
import { MatchRows, type Page } from './Hall';
import { Badge, ErrorPanel, Icon, identityColor, nameLabel, PageTitle, State, labels, LoadingPanel, ReadNotice } from './ui';
import type { Match, Row } from './types';
import { ReceiptList } from './Receipts';

export function Entrants() {
  const entrants = useResource<Page<Row>>('/api/v1/entrants', useRevision());
  if (entrants.error && !entrants.data) return <ErrorPanel message={entrants.error} status={entrants.errorStatus} onRetry={entrants.retry} />;
  return <><PageTitle eyebrow="参赛者 / ENTRANTS" title="策略的独立身份。" detail="每个冻结提交都有独立 ID。模型名称不是成绩的唯一键。" /><ReadNotice resource={entrants} />{entrants.loading && <LoadingPanel title="正在读取参赛者" />}<div className="entrant-grid">{entrants.data?.items.map(e => <Link to={`/entrants/${e.id}`} className="entrant-card panel" key={e.id}><div className="entrant-avatar" style={{ color: identityColor(e.id) }}>{nameLabel(e.name || e.id).slice(0, 1)}</div><Badge status={e.status} /><h2>{nameLabel(e.name || e.id)}</h2><p>{e.baseline ? '手写 Baseline · 工程参照' : e.model || '独立提交'}</p><small className="mono">{e.wasm_sha256?.slice(0, 16) || '等待编译'}</small><span className="entrant-link">查看参赛记录 <Icon name="arrow" /></span></Link>)}</div>{entrants.data && !entrants.data.items.length && <State title="还没有参赛者" detail="进入工作台收卷或导入已有证据。"><Link className="button primary" to="/manage">进入工作台</Link></State>}<ReceiptList /></>;
}

export function EntrantPage() {
  const { id } = useParams();
  const entrant = useResource<Row>(`/api/v1/entrants/${id}`, useRevision());
  const matches = useResource<Page<Match>>(`/api/v1/matches?entrant=${id}&limit=100`, useRevision());
  if (entrant.error && !entrant.data) return <ErrorPanel message={entrant.error} status={entrant.errorStatus} onRetry={entrant.retry} />;
  if (!entrant.data) return <LoadingPanel title="正在读取参赛者" />;
  const e = entrant.data;
  return <><PageTitle eyebrow="参赛者档案 / ENTRANT" title={nameLabel(e.name || e.id)} detail={e.baseline ? '手写 Baseline，仅作工程参照，不是模型生成结果。' : e.model || '独立源码提交'}><Badge status={e.status} /></PageTitle><ReadNotice resource={entrant} /><section className="panel identity-panel"><div><small>提交唯一 ID</small><span className="mono">{e.id}</span></div><div><small>WASM SHA-256</small><span className="mono hash-text">{e.wasm_sha256 || '尚未产生'}</span></div><div><small>源码状态</small><span>{e.status === 'qualified' ? '已冻结 · 资格通过' : labels[e.status] || e.status}</span></div></section><section className="matches-section"><div className="section-heading"><h2>参赛对局</h2><span className="muted mono">{matches.data ? `${matches.data.total || 0} 局` : '—'}</span></div><ReadNotice resource={matches} />{matches.loading ? <LoadingPanel title="正在读取参赛对局" /> : matches.data?.items.length ? <MatchRows rows={matches.data.items} /> : !matches.error && <p className="empty-note muted">当前参赛者尚无公开对局。</p>}</section></>;
}
