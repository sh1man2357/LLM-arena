import { useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useResource } from './api';
import { useRevision } from './App';
import { Badge, ErrorPanel, Icon, identityColor, PageTitle, State, LoadingPanel, ReadNotice, labels } from './ui';
import type { Row } from './types';

const time = (value?: string) => value ? new Date(value).toLocaleString('zh-CN', {hour12:false}) : '—';
const reasons: Record<string,string> = {
  open:'仍在开发时限内，可提前提交最终源码。', missing:'截止时间已到，尚未收到最终源码。记录保留，之后收到的源码按逾期留档。',
  submitted:'最终源码已冻结，等待统一编译与资格检查。', queued:'编译作业已排队，冻结源码不会重新开放修改。',
  compiling:'正在统一编译与资格检查，请等待实际执行结果。', qualified:'冻结程序已通过资格，可进入参赛池。',
  qualification_failed:'编译或资格检查未通过。冻结源码和原始诊断保留，不能覆盖本次最终提交。',
  late:'最终源码晚于固定截止时间，仅保留记录，不进入本次正式参赛。', stopped:'编译排队已停止。可在工作台检查后恢复同一冻结提交。',
  interrupted:'编译执行已中断。可检查日志后重试同一冻结源码，原尝试保留。',
  failed:'编译作业没有成功完成。请检查执行诊断；该状态不代表已有可参赛程序。',
};

function useDeadlineRefresh(rows: Row[], retry: () => void) {
  const deadline = rows.filter(row => row.status === 'open').map(row => new Date(row.deadline).getTime()).sort((a,b)=>a-b)[0];
  useEffect(() => {
    if (deadline === undefined) return;
    // Re-read authoritative server status at the deadline; do not relabel locally.
    const timer = setTimeout(retry, Math.min(2147483647, Math.max(500, deadline - Date.now() + 150)));
    return () => clearTimeout(timer);
  }, [deadline, retry]);
}

export function ReceiptList() {
  const revision = useRevision();
  const access = useResource<{owner:boolean}>('/api/v1/admin/status', revision);
  const receipts = useResource<{items:Row[]}>(access.data?.owner ? '/api/v1/receipts' : null, revision);
  useDeadlineRefresh(receipts.data?.items || [], receipts.retry);
  return <section className="matches-section receipt-section"><div className="section-heading"><h2>收卷与资格档案</h2><span className="muted small">主办方记录</span></div>
    <ReadNotice resource={access} /><ReadNotice resource={receipts} />
    {(access.loading || receipts.loading) && <LoadingPanel title="正在读取收卷档案" />}
    {access.data && !access.data.owner && <State title="收卷档案仅供主办方查看" detail="公开程序可在上方浏览。开发中的会话、源码与编译诊断保留在本机工作台。"><Link className="button quiet" to="/manage">进入主办方工作台</Link></State>}
    {receipts.data && !receipts.data.items.length && <State title="还没有收卷档案" detail="在工作台记录收到任务，再接收一个最终源码。"><Link className="button primary" to="/manage">开始收卷</Link></State>}
    <div className="entrant-grid">{receipts.data?.items.map(row => <Link className="entrant-card panel" key={row.id} data-receipt-id={row.id} to={`/entrants/receipts/${row.id}`}>
      <div className="entrant-avatar" style={{color:identityColor(row.id)}}>{row.name.slice(0,1)}</div><Badge status={row.status} /><h3>{row.name}</h3><p>{row.model}</p>
      <small>截止 {time(row.deadline)}</small><p className="small muted">{row.submission ? '最终源码已冻结' : '尚未交卷'} · {row.time_source === 'external_record' ? '外部时间记录' : '主办方确认'}</p>
      <span className="entrant-link">查看收卷与资格 <Icon name="arrow" /></span>
    </Link>)}</div>
  </section>;
}

export function ReceiptPage() {
  const {id} = useParams();
  const revision = useRevision();
  const access = useResource<{owner:boolean}>('/api/v1/admin/status', revision);
  const receipt = useResource<Row>(access.data?.owner ? `/api/v1/receipts/${id}` : null, revision);
  useDeadlineRefresh(receipt.data ? [receipt.data] : [], receipt.retry);
  if (access.error && !access.data) return <ErrorPanel message={access.error} onRetry={access.retry} status={access.errorStatus} />;
  if (access.loading) return <LoadingPanel title="正在检查档案访问状态" />;
  if (!access.data?.owner) return <><PageTitle eyebrow="收卷档案 / RECEIPT" title="收卷档案仅供主办方查看" detail="这份档案没有公开源码、时间记录或诊断。" /><State title="从本机工作台继续" detail="进入工作台后，可查看自己实例中的收卷记录。"><Link className="button primary" to={`/manage?session=${encodeURIComponent(id || '')}`}>进入主办方工作台</Link></State></>;
  if (receipt.error && !receipt.data) return <ErrorPanel message={receipt.error} status={receipt.errorStatus} onRetry={receipt.retry} />;
  if (!receipt.data) return <LoadingPanel title="正在读取收卷档案" />;
  const row = receipt.data, submission = row.submission, job = row.job;
  const diagnostic = submission?.diagnostic || job?.diagnostic;
  return <><Link className="back-link" to="/entrants"><Icon name="back" />参赛者与档案</Link>
    <PageTitle eyebrow="收卷与资格 / RECEIPT" title={row.name} detail={row.model}><Badge status={row.status} /></PageTitle><ReadNotice resource={receipt} />
    <div className="notice" role="status"><Icon name="info" />{reasons[row.status] || labels[row.status]}</div>
    <section className="panel identity-panel receipt-times"><div><small>收到任务</small><span>{time(row.started_at)}</span></div><div><small>固定 60 分钟截止</small><span>{time(row.deadline)}</span></div><div><small>时间来源</small><span>{row.time_source === 'external_record' ? '外部记录 · 主办方确认' : '本机工作台记录'}</span></div><div><small>收到最终源码</small><span>{time(submission?.received_at)}</span></div></section>
    <section className="panel receipt-evidence"><div className="section-heading"><h2>冻结与资格证据</h2><span className="muted small">独立收卷记录</span></div>
      <dl><dt>收卷 ID</dt><dd className="mono hash-text">{row.id}</dd><dt>任务书 SHA-256</dt><dd className="mono hash-text">{row.task_sha256}</dd><dt>最终提交 ID</dt><dd className="mono hash-text">{submission?.id || '尚未交卷'}</dd><dt>源码 SHA-256</dt><dd className="mono hash-text">{submission?.source_sha256 || '收到最终源码后才产生'}</dd><dt>冻结时间</dt><dd>{time(submission?.frozen_at)}</dd><dt>WASM SHA-256</dt><dd className="mono hash-text">{submission?.wasm_sha256 || '尚未产生资格通过的程序'}</dd></dl>
      <div className="record-actions"><Link className="button primary" to={`/manage?session=${row.id}`}>{submission ? '在工作台查看与管理' : '继续收卷'}<Icon name="arrow" /></Link>{submission && <a className="button quiet" href={`/api/v1/submissions/${submission.id}/source`} target="_blank" rel="noreferrer">查看冻结源码</a>}{submission?.entrant_id && <Link className="button quiet" to={`/entrants/${submission.entrant_id}`}>查看可参赛程序</Link>}</div>
      <p className="small muted">档案不会把未交卷或资格失败的记录加入参赛池。交卷之后不能覆盖正式源码；编译错误不会延长开发截止。</p>
    </section>
    {job && <section className="panel receipt-evidence"><div className="section-heading"><h2>编译执行</h2><Badge status={job.status} /></div><p className="mono hash-text">{job.id}</p><p className="small muted">尝试 {job.attempts.length} · 实际作业 {job.progress} / {job.total}</p>{job.attempt_id && <a className="button quiet" href={`/api/v1/jobs/${job.id}/log`} target="_blank" rel="noreferrer">查看执行日志</a>}</section>}
    {(diagnostic || submission?.compile_log || submission?.qualification) && <section className="panel receipt-evidence"><h2>诊断与资格记录</h2>{diagnostic && <pre className="compile-log mono" data-receipt-diagnostic>{diagnostic}</pre>}{submission?.compile_log && <details className="record-details"><summary>原始编译日志</summary><pre className="compile-log mono">{JSON.stringify(submission.compile_log,null,2)}</pre></details>}{submission?.qualification && <details className="record-details"><summary>资格检查结果</summary><pre className="compile-log mono">{JSON.stringify(submission.qualification,null,2)}</pre></details>}</section>}
  </>;
}
