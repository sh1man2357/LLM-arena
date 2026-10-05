import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, useResource } from './api';
import { useRevision } from './App';
import { Badge, ErrorPanel, Icon, PageTitle } from './ui';
import type { Row } from './types';

const timeLabel = (time?: string) => time ? new Date(time).toLocaleString('zh-CN', { hour12: false }) : '—';
const jobNames: Record<string, string> = { compile: '编译与资格', match: '双人对局', tournament: '全配对批次', import: '证据导入' };

export function Manage() {
  const revision = useRevision();
  const [ready, setReady] = useState(false), [authError, setAuthError] = useState('');
  const [refresh, setRefresh] = useState(0), [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(''), [failed, setFailed] = useState(false);
  const guard = useRef(false);
  const [now, setNow] = useState(Date.now());
  const [name, setName] = useState(''), [model, setModel] = useState('');
  const [external, setExternal] = useState(false), [startedAt, setStartedAt] = useState(''), [receivedAt, setReceivedAt] = useState('');
  const [sessionId, setSessionId] = useState(''), [source, setSource] = useState('');
  const [selected, setSelected] = useState<string[]>([]), [title, setTitle] = useState('新一轮策略竞技');
  const [mapSeed, setMapSeed] = useState(1), [caseCount, setCaseCount] = useState(50), [official, setOfficial] = useState(false);
  const [interval, setIntervalMs] = useState(50);
  useEffect(() => {
    let canceled = false;
    api('/api/v1/admin/unlock', { method: 'POST', headers: { 'X-Arena-Local': '1' } })
      .then(() => { if (!canceled) setReady(true); }).catch(e => { if (!canceled) setAuthError(e.message); });
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => { canceled = true; clearInterval(timer); };
  }, []);
  const version = revision + refresh;
  const sessions = useResource<{ items: Row[] }>(ready ? '/api/v1/sessions' : null, version);
  const submissions = useResource<{ items: Row[] }>(ready ? '/api/v1/submissions' : null, version);
  const jobs = useResource<{ items: Row[] }>(ready ? '/api/v1/jobs' : null, version);
  const entrants = useResource<{ items: Row[] }>('/api/v1/entrants', version);
  const batches = useResource<{ items: Row[] }>(ready ? '/api/v1/tournaments' : null, version);
  const session = sessions.data?.items.find(s => s.id === sessionId);
  const eligible = entrants.data?.items.filter(e => e.status === 'qualified') || [];
  const remaining = session ? Math.max(0, Math.ceil((new Date(session.deadline).getTime() - now) / 1000)) : 0;
  const frozen = !!session?.submission_id;
  const bytes = new TextEncoder().encode(source).length;

  async function act(work: () => Promise<string>) {
    if (guard.current) return;
    guard.current = true; setBusy(true); setFailed(false); setMessage('');
    try { setMessage(await work()); setRefresh(r => r + 1); }
    catch(e) { setMessage((e as Error).message); setFailed(true); }
    finally { guard.current = false; setBusy(false); }
  }
  function post<T = Row>(path: string, body?: unknown) {
    return api<T>(path, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  }
  async function createSession() {
    const row = await post('/api/v1/sessions', { name: name.trim(), model: model.trim() || '未注明模型', time_source: external ? 'external_record' : 'host_confirmation', ...(external && startedAt ? { started_at: new Date(startedAt).toISOString() } : {}) });
    setSessionId(row.id); setSource(''); setReceivedAt(''); setName('');
    return '收卷记录已建立，截止时间固定为收到任务后 60 分钟。';
  }
  async function freeze() {
    const row = await post(`/api/v1/sessions/${sessionId}/submit`, { source, ...(session?.time_source === 'external_record' && receivedAt ? { received_at: new Date(receivedAt).toISOString() } : {}) });
    setSource(''); return row.late ? '源码已按逾期留档，不进入本次正式参赛。' : '最终源码已冻结，可以开始统一编译与资格检查。';
  }
  async function readSource(file?: File) {
    if (!file) return '尚未选择文件。';
    if (file.size > 1024 * 1024) throw new Error('源码超过 1 MiB。');
    setSource(await file.text()); return '源码已载入编辑区，点击最终交卷后才冻结。';
  }
  async function createCompetition(kind: 'match' | 'tournament') {
    const job = await post(`/api/v1/${kind === 'match' ? 'matches' : 'tournaments'}`, kind === 'match' ? { entrant_ids: selected, map_seed: mapSeed, title, tick_interval_ms: interval } : { entrant_ids: selected, case_count: caseCount, title, official });
    return `${jobNames[kind]}已排队 · ${job.id}。运行进度在下方更新。`;
  }
  async function upload(file?: File) {
    if (!file) return '尚未选择文件。';
    if (file.size > 16 * 1024 * 1024) throw new Error('Replay 超过 16 MiB。');
    const form = new FormData(); form.append('file', file);
    const row = await api<Row>('/api/v1/imports/replay', { method: 'POST', body: form });
    return `Replay 已验证并导入 · ${row.id}。`;
  }
  async function uploadArchive(file?: File) {
    if (!file) return '尚未选择文件。';
    if (file.size > 16 * 1024 * 1024) throw new Error('ZIP 归档超过 16 MiB。');
    const form = new FormData(); form.append('file', file);
    const job = await api<Row>(`/api/v1/imports/archive?title=${encodeURIComponent(file.name.replace(/\.zip$/i, '').slice(0, 120) || '导入的比赛批次')}`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: form });
    return `批次归档已排队验证 · ${job.id}。校验通过后出现在大厅，失败可查看执行日志。`;
  }
  const resourceError = sessions.error || submissions.error || jobs.error || batches.error || entrants.error;
  if (authError) return <ErrorPanel message={authError} />;
  return <><PageTitle eyebrow="主办方 / CONTROL ROOM" title="让比赛准备就绪。" detail="收卷、冻结、资格与比赛调度 · 全程保留真实证据。"><button className="quiet" onClick={() => setRefresh(r => r + 1)}><Icon name="refresh" />刷新状态</button></PageTitle>
    {!ready && <p role="status" className="muted">正在连接本机工作台…</p>}
    {resourceError && <ErrorPanel message={resourceError} />}
    <div className={`workflow-message ${failed ? 'error' : ''}`} role={failed ? 'alert' : 'status'} aria-live="polite">{busy ? '正在提交操作…' : message || '从收到任务开始计时。最终交卷后立即冻结，比赛只执行已冻结的 Bot。'}</div>
    <div className="manage-grid workflow-grid"><div className="workflow-column">
      <section className="panel"><div className="section-heading"><h2><span className="step-number mono">01</span> 收卷与源码冻结</h2><Icon name="people" /></div>
        <form className="workflow-form" onSubmit={e => { e.preventDefault(); void act(createSession); }}>
          <div className="form-row"><label>参赛者名称<input required maxLength={100} value={name} onChange={e => setName(e.target.value)} placeholder="例如：模型名称 / 本次提交" /></label><label>模型标识<input maxLength={160} value={model} onChange={e => setModel(e.target.value)} placeholder="可选，记录实际使用的模型" /></label></div>
          <details className="record-details"><summary>已有外部对话的时间记录</summary><p className="muted">已在外部发卷时，记录真实时间。此项由主办方确认，不代表程序验证了远端开发过程。</p><label className="check-label"><input type="checkbox" checked={external} onChange={e => setExternal(e.target.checked)} />使用外部记录时间</label>{external && <label>实际收到任务时间<input type="datetime-local" required value={startedAt} onChange={e => setStartedAt(e.target.value)} /></label>}</details>
          <button className="primary" disabled={!ready || busy || !name.trim()} type="submit"><Icon name="check" />记录收到任务，开始 60 分钟</button>
        </form>
        <div className="source-workspace"><label className="field-label">选择收卷记录<select aria-label="选择收卷记录" value={sessionId} onChange={e => { setSessionId(e.target.value); setSource(''); setReceivedAt(''); }}><option value="">选择参赛者…</option>{sessions.data?.items.map(s => <option key={s.id} value={s.id}>{s.name} · {s.submission_id ? '已冻结' : new Date(s.deadline).getTime() < now ? '未交卷 / 已截止' : '开发中'}</option>)}</select></label>
          {session && <><div className="session-clock"><div><span className="muted">{frozen ? '最终交卷已固定' : remaining ? '距离截止' : '开发时限已结束'}</span><strong className="mono">{frozen ? '已冻结' : `${String(Math.floor(remaining / 60)).padStart(2, '0')}:${String(remaining % 60).padStart(2, '0')}`}</strong></div><Badge status={session.status} /></div><p className="small muted">发卷 {timeLabel(session.started_at)}<br />截止 {timeLabel(session.deadline)} · {session.time_source === 'external_record' ? '外部记录' : '主办方确认'}</p>
            {!frozen ? <><label className="source-label">最终 bot.cpp<textarea aria-label="最终 bot.cpp" className="source-editor mono" value={source} onChange={e => setSource(e.target.value)} spellCheck={false} placeholder={'#include "arena.hpp"\n// 在此粘贴完整 C++20 源码'} /></label><div className="source-actions"><label className="file-input-label button">载入 bot.cpp<input aria-label="载入 bot.cpp" type="file" accept=".cpp" disabled={busy} onChange={e => { const file = e.target.files?.[0]; void act(() => readSource(file)); e.target.value = ''; }} /></label><span className={`small mono ${bytes > 1024*1024 ? 'danger-text' : 'muted'}`}>{bytes.toLocaleString()} / 1,048,576 bytes</span></div>{session.time_source === 'external_record' && <label className="field-label">实际收到最终源码时间<input type="datetime-local" aria-label="实际收到最终源码时间" value={receivedAt} onChange={e => setReceivedAt(e.target.value)} /><small className="muted">留空按服务端接收时间记录；外部交卷须填写真实接收时间。</small></label>}<button className="primary" disabled={busy || !source || bytes > 1024*1024} onClick={() => void act(freeze)}><Icon name="check" />{remaining || session.time_source === 'external_record' ? '最终交卷并冻结' : '按逾期留档'}</button><p className="small muted">提前交卷即结束开发。编译失败也不重新开放修改。</p></> : <p className="frozen-note"><Icon name="check" />本次最终源码已冻结，可在提交记录中检查资格和诊断。</p>}
          </>}
          {!sessions.loading && !sessions.data?.items.length && <p className="empty-note muted">还没有收卷记录。先填写参赛者名称即可开始。</p>}
        </div>
      </section>
      <section className="panel"><div className="section-heading"><h2><span className="step-number mono">02</span> 统一编译与参赛资格</h2><span className="muted small">C++20 → WASM</span></div>
        {!submissions.data?.items.length && <p className="empty-note muted">最终交卷后，源码哈希、资格与编译日志在此保留。</p>}
        <div className="submission-list">{submissions.data?.items.map(s => <article className="submission-row" key={s.id}><div className="record-heading"><div><strong>{s.name}</strong><small className="muted">{s.model} · {timeLabel(s.received_at)}</small></div><Badge status={s.status} /></div><p className="hash-text mono">源码 {s.source_sha256}</p>{s.wasm_sha256 && <p className="hash-text mono">WASM {s.wasm_sha256}</p>}{s.late && <p className="danger-text small">超过 60 分钟截止，仅保留记录，不能进入本次正式参赛。</p>}<div className="record-actions">{!s.late && ['submitted', 'interrupted'].includes(s.status) && <button disabled={busy} onClick={() => void act(async () => { const job = await post(`/api/v1/submissions/${s.id}/compile`); return `编译作业已排队 · ${job.id}。`; })}>编译并检查资格</button>}<a className="button quiet" href={`/api/v1/submissions/${s.id}/source`} target="_blank" rel="noreferrer">查看冻结源码</a>{s.entrant_id && <Link className="button quiet" to={`/entrants/${s.entrant_id}`}>参赛者详情<Icon name="arrow" /></Link>}</div>{(s.compile_log || s.diagnostic) && <details className="record-details"><summary>编译日志与诊断</summary><pre className="compile-log mono">{s.diagnostic || ''}{s.compile_log ? '\n' + JSON.stringify(s.compile_log, null, 2) : ''}</pre></details>}</article>)}</div>
      </section>
    </div><div className="workflow-column">
      <section className="panel protocol-card"><p className="eyebrow">统一开发协议</p><strong className="protocol-time mono">60<span>min</span></strong><h2>交卷即冻结。</h2><p className="muted">从收到任务起计时，可提前提交。时限内自主编译、测试与修改，无额外 token 或轮数配置。截止之后可以编译已经冻结的源码。</p></section>
      <section className="panel"><div className="section-heading"><h2><span className="step-number mono">03</span> 组织比赛</h2><Icon name="trophy" /></div><p className="muted">选择资格通过的冻结程序。单局需要两名；批次为全配对，每张地图交换出生位。</p><div className="entrant-picker">{eligible.map(e => <label className="check-label" key={e.id} data-entrant-id={e.id}><input type="checkbox" checked={selected.includes(e.id)} onChange={event => setSelected(previous => event.target.checked ? [...previous, e.id] : previous.filter(id => id !== e.id))} /><span>{e.name}<small className="muted">{e.baseline ? '手写 Baseline' : e.model || '冻结提交'} · {e.id.slice(0, 18)}</small></span></label>)}{!eligible.length && <p className="muted small">还没有可参赛程序。先完成资格检查，或导入参考赛的 Baseline。</p>}</div><div className="workflow-form"><label>比赛标题<input aria-label="比赛标题" value={title} maxLength={120} onChange={e => setTitle(e.target.value)} /></label><div className="form-row"><label>单局公开地图 Seed<input aria-label="单局公开地图 Seed" type="number" min={0} max={4294967295} value={mapSeed} onChange={e => setMapSeed(Number(e.target.value))} /></label><label>批次地图数<input aria-label="批次地图数" type="number" min={1} max={1000} value={caseCount} onChange={e => setCaseCount(Number(e.target.value))} /></label></div><label>单局运行节奏<select aria-label="单局运行节奏" value={interval} onChange={e => setIntervalMs(Number(e.target.value))}><option value={50}>便于观赛 · 20 Tick / 秒</option><option value={250}>慢速观察 · 4 Tick / 秒</option><option value={0}>即时计算</option></select><small className="muted">仅主办方设定单局执行间隔；观众播放控制不影响比赛，批次仍快速计算。</small></label><label className="check-label"><input type="checkbox" checked={official} onChange={e => setOfficial(e.target.checked)} />正式隐藏批次，收卷关闭前封存地图</label><p className="small muted">{selected.length} 名参赛者 · {caseCount * selected.length * (selected.length - 1)} 局批次计划。调度和 Bot Seed 创建后固定。</p><div className="record-actions"><button disabled={busy || !ready || selected.length !== 2 || !Number.isInteger(mapSeed) || mapSeed < 0 || mapSeed > 4294967295} onClick={() => void act(() => createCompetition('match'))}>启动双人单局</button><button className="primary" disabled={busy || !ready || selected.length < 2 || selected.length > 16 || !Number.isInteger(caseCount) || caseCount < 1 || caseCount > 1000} onClick={() => void act(() => createCompetition('tournament'))}>创建全配对批次</button></div></div></section>
      <section className="panel"><div className="section-heading"><h2>导入已有证据</h2><Icon name="share" /></div><p className="muted">保留原始文件并验证，历史参考赛明确标记为工程 Baseline。</p><button disabled={busy || !ready} onClick={() => void act(async () => { const job = await post('/api/v1/imports', { source: 'bundled-v0.1' }); return `完整参考赛导入已排队 · ${job.id}。`; })}>导入 v0.1 完整参考赛</button><label className="file-input-label button">上传 Replay<input type="file" aria-label="上传 Replay" accept=".jsonl" disabled={busy || !ready} onChange={e => { const file = e.target.files?.[0]; void act(() => upload(file)); e.target.value = ''; }} /></label><label className="file-input-label button">上传批次 ZIP<input type="file" aria-label="上传批次 ZIP" accept=".zip" disabled={busy || !ready} onChange={e => { const file = e.target.files?.[0]; void act(() => uploadArchive(file)); e.target.value = ''; }} /></label><p className="small muted">ZIP 根目录须含 manifest、schedule、cases、results 与 replays，最大 16 MiB。上传批次先封存地图，确认原收卷结束后再公开。保留原始证据；不同冻结版本使用独立身份，导入不会改写旧成绩。</p></section>
    </div></div>
    <section className="panel workflow-jobs"><div className="section-heading"><h2><span className="step-number mono">04</span> 作业进度与恢复</h2><span className="muted small">一次一个计算作业 · 页面可继续操作</span></div>
      {!jobs.data?.items.length && <p className="empty-note muted">尚无作业。编译、单局、批次与导入会显示在这里。</p>}
      {jobs.data?.items.map(job => <article className="job-row" key={job.id} data-job-id={job.id}><div className="job-info"><div className="record-heading"><strong>{job.resources.title || jobNames[job.kind]}</strong><Badge status={job.status} /></div><small className="muted mono">{job.id} · {jobNames[job.kind]} · 尝试 {job.attempts.length}</small><div className="job-progress"><progress max={job.total || 1} value={job.status === 'succeeded' ? job.total || 1 : job.progress} /><span className="mono">{job.progress} / {job.total}</span></div>{job.diagnostic && <p className="danger-text job-diagnostic">{job.diagnostic}</p>}</div><div className="record-actions">{(job.status === 'queued' || (job.kind === 'tournament' && job.status === 'running')) && <button disabled={busy} onClick={() => void act(async () => { await post(`/api/v1/jobs/${job.id}/stop`); return job.status === 'queued' ? '已停止排队。' : '已请求停止调度，当前单局完成后停止。'; })}>{job.status === 'queued' ? '停止排队' : '当前局后停止'}</button>}{['stopped', 'interrupted', 'failed'].includes(job.status) && <button disabled={busy} onClick={() => void act(async () => { await post(`/api/v1/jobs/${job.id}/resume`); return '作业已重新排队，原尝试与证据保留。'; })}>恢复 / 重试</button>}{job.resources.match_id && <Link className="button quiet" to={`/matches/${job.resources.match_id}`}>进入观赛<Icon name="arrow" /></Link>}{(job.resources.tournament_id || job.result?.tournament_id) && <Link className="button quiet" to={`/tournaments/${job.resources.tournament_id || job.result.tournament_id}`}>查看批次<Icon name="arrow" /></Link>}{job.attempt_id && <a className="button quiet" href={`/api/v1/jobs/${job.id}/log`} target="_blank" rel="noreferrer">执行日志</a>}</div></article>)}
    </section>
    {!!batches.data?.items.some(b => b.official || b.job_id || b.imported) && <section className="panel workflow-publication"><div className="section-heading"><h2>观看与成绩发布</h2><Icon name="share" /></div><p className="muted">正式批次关闭收卷后才开放地图。完整比赛证据校验通过才能发布正式报告。</p>{batches.data.items.filter(b => b.official || b.job_id || b.imported).map(batch => <article className="publication-row" key={batch.id}><div><Link to={`/tournaments/${batch.id}`}><strong>{batch.title}</strong></Link><p className="small muted">{batch.completed_matches} / {batch.expected_matches} 局 · <Badge status={batch.disclosure} /></p>{batch.published_at && <p className="small muted">发布 {timeLabel(batch.published_at)} · 公开副本已固定</p>}</div><div className="record-actions">{(batch.official || batch.requires_disclosure_confirmation) && !batch.submission_window_closed && <button disabled={busy} onClick={() => void act(async () => { await post(`/api/v1/tournaments/${batch.id}/close-submissions`); return '收卷窗口已关闭，地图已披露；后续提交须使用新的隐藏集。'; })}>{batch.requires_disclosure_confirmation ? '确认原收卷结束并开放观看' : '关闭收卷并开放观看'}</button>}{!batch.publication_id && batch.status === 'complete' && (!(batch.official || batch.requires_disclosure_confirmation) || batch.submission_window_closed) && <button disabled={busy} onClick={() => void act(async () => { await post(`/api/v1/tournaments/${batch.id}/publish`); return '完整证据已重新校验，成绩发布记录已保存。'; })}>校验并发布成绩</button>}{batch.publication_id && <a className="button quiet" href={`/api/v1/exports/${batch.id}?kind=publication`}>下载发布清单</a>}</div></article>)}</section>}
  </>;
}
