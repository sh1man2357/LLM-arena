import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, useResource } from './api';
import { useRevision } from './App';
import { Badge, ErrorPanel, outcome } from './ui';
import type { Bot, Match } from './types';

export function Home() {
  const revision = useRevision(), navigate = useNavigate();
  const [refresh, setRefresh] = useState(0), [offset, setOffset] = useState(0);
  const bots = useResource<{items: Bot[]}>('/api/v1/bots', revision + refresh);
  const runs = useResource<{items: Match[]; total: number}>(`/api/v1/matches?offset=${offset}&limit=20`, revision + refresh);
  const status = useResource<{busy: boolean; operation: string | null}>('/api/v1/status', revision + refresh);
  const [file, setFile] = useState<File>(), [name, setName] = useState('');
  const [first, setFirst] = useState(''), [second, setSecond] = useState(''), [seed, setSeed] = useState('');
  const [working, setWorking] = useState(false), [message, setMessage] = useState('');
  const guard = useRef(false);
  const importKey = useRef(crypto.randomUUID()), runKey = useRef(crypto.randomUUID());
  const ready = bots.data?.items.filter(b => b.status === 'ready') || [];
  useEffect(() => {
    if (!first && ready.length) setFirst(ready[0].id);
    if (!second && ready.length > 1) setSecond(ready[1].id);
  }, [bots.data]);
  useEffect(() => { importKey.current = crypto.randomUUID(); }, [file, name]);
  useEffect(() => { runKey.current = crypto.randomUUID(); }, [first, second, seed]);
  const busy = working || status.data?.busy || !status.data;
  async function act(work: () => Promise<void>) {
    if (guard.current) return;
    guard.current = true; setWorking(true); setMessage('');
    try { await work(); setRefresh(r => r + 1); }
    catch (error) { setMessage((error as Error).message); }
    finally { guard.current = false; setWorking(false); }
  }
  const resources = [bots, runs, status];
  const error = resources.find(r => r.error);
  return <><div className="page-heading home-heading"><p className="eyebrow">双人炸弹人 / BOT ARENA</p><h1>LLM ARENA<span className="title-dot">.</span></h1><p className="intro">选好 Bot，开始对战。每一局，都可以回看。</p>
    <div className="quick-links" aria-label="页面内导航"><a href="#new-match">运行一局 <span aria-hidden="true">↗</span></a><a href="#bots">管理 Bot <span aria-hidden="true">↗</span></a><a href="#history">运行记录 <span aria-hidden="true">↗</span></a></div></div>
    {error && <ErrorPanel message={error.error} onRetry={() => resources.forEach(r => r.retry())} />}
    {message && <div className="notice error" role="alert">{message}</div>}
    {status.data?.busy && <p className="notice" role="status">{status.data.operation === 'match' ? '对局正在运行；可以打开观赛或查看已有录像。' : '正在编译与检查 Bot，请稍候。'}</p>}
    <section className="content-section" id="new-match" aria-labelledby="run-title"><div className="section-heading"><p className="eyebrow">01 / PLAY</p><h2 id="run-title">运行一局</h2><p className="muted">选择两个 Bot，进入赛场。</p></div><div className="section-body"><form className="run-form" onSubmit={e => { e.preventDefault(); void act(async () => {
      const match = await api<Match>('/api/v1/matches', {method: 'POST', headers: {'X-Arena-Local': '1', 'Idempotency-Key': runKey.current},
        body: JSON.stringify({bot_ids: [first, second], ...(seed === '' ? {} : {map_seed: Number(seed)})})});
      navigate(`/matches/${match.id}`);
    }); }}><div className="match-picker"><label><span className="slot-label"><i className="slot-dot slot-zero" aria-hidden="true" />Bot 0</span><select value={first} onChange={e => setFirst(e.target.value)}><option value="">选择 Bot</option>{ready.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
      <span className="versus" aria-hidden="true">VS</span><label><span className="slot-label"><i className="slot-dot slot-one" aria-hidden="true" />Bot 1</span><select value={second} onChange={e => setSecond(e.target.value)}><option value="">选择 Bot</option>{ready.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label></div>
      <div className="run-actions"><details><summary>地图设置</summary><label>地图 Seed<input type="number" min="0" max="4294967295" step="1" value={seed} onChange={e => setSeed(e.target.value)} placeholder="自动生成" /></label></details><button className="primary" disabled={busy || !first || !second || first === second}>运行 <span aria-hidden="true">↗</span></button></div>
      {first && first === second && <p className="form-hint" role="status">请选择两个不同的 Bot。</p>}
      {bots.data && ready.length < 2 && <p className="form-hint">需要两个可运行的 Bot。<a href="#bots">前往导入 ↓</a></p>}
    </form></div></section>
    <section className="content-section" id="bots" aria-labelledby="bots-title"><div className="section-heading"><p className="eyebrow">02 / BOTS</p><h2 id="bots-title">Bot{bots.data && <span className="section-count">{bots.data.items.length}</span>}</h2><p className="muted">导入 .cpp，自动编译。</p></div><div className="section-body">
      <details className="import-disclosure"><summary>导入 Bot</summary><form className="import-form" onSubmit={e => { e.preventDefault(); void act(async () => {
        if (!file) throw new Error('请选择 bot.cpp。');
        if (file.size > 1024 * 1024) throw new Error('源码超过 1 MiB。');
        const form = new FormData(); form.append('file', file); form.append('name', name.trim());
        await api<Bot>('/api/v1/bots', {method: 'POST', headers: {'X-Arena-Local': '1', 'Idempotency-Key': importKey.current}, body: form});
        importKey.current = crypto.randomUUID();
      }); }}><label>Bot 文件<input type="file" accept=".cpp" aria-label="Bot 文件" required onChange={e => {
        const chosen = e.target.files?.[0]; setFile(chosen); setName(chosen?.name.replace(/\.cpp$/i, '') || '');
      }} /></label><label>名称<input value={name} maxLength={100} onChange={e => setName(e.target.value)} placeholder="默认使用文件名" /></label>
        <button disabled={busy || !file}>导入 Bot</button></form></details>
      {bots.loading && <p role="status">正在读取 Bot…</p>}
      {bots.data && !bots.data.items.length && <p className="muted">还没有 Bot。导入一个 .cpp 文件即可自动编译。</p>}
      <ul className="bot-list">{bots.data?.items.map(bot => <li key={bot.id} data-bot-id={bot.id}>
        <div className="bot-row"><div><strong>{bot.name}</strong>{bot.baseline && <span className="baseline-label">基准</span>}</div><Badge status={bot.status} /></div>
        {bot.diagnostic && <p className="error-text">{bot.diagnostic}</p>}
        {(bot.compile_log?.stderr || bot.compile_log?.stdout) && <details><summary>编译日志</summary><pre>{bot.compile_log.stderr}{bot.compile_log.stdout}</pre></details>}
      </li>)}</ul>
    </div></section>
    <section className="content-section history" id="history" aria-labelledby="history-title"><div className="section-heading"><p className="eyebrow">03 / REPLAYS</p><h2 id="history-title">运行记录{runs.data && <span className="section-count">{runs.data.total}</span>}</h2><Link className="text-link" to="/leaderboard">查看榜单 ↗</Link></div><div className="section-body">
      {runs.loading && <p role="status">正在读取运行记录…</p>}
      {runs.data && !runs.data.items.length && <p className="muted">暂无运行记录。选择两个 Bot 开始第一局。</p>}
      <ul className="run-list">{runs.data?.items.map(run => <li key={run.id}><Link to={`/matches/${run.id}`}><div><strong>{run.title}</strong><small className="muted">{new Date(run.created).toLocaleString()}{run.status === 'completed' && run.result?.valid ? ` · ${outcome(run)}` : ''}</small></div><Badge status={run.status} /><span className="row-arrow" aria-hidden="true">↗</span></Link></li>)}</ul>
      {runs.data && runs.data.total > 20 && <div className="pagination"><button disabled={!offset} onClick={() => setOffset(o => Math.max(0, o - 20))}>上一页</button><span>{offset + 1}～{Math.min(offset + 20, runs.data.total)} / {runs.data.total}</span><button disabled={offset + 20 >= runs.data.total} onClick={() => setOffset(o => o + 20)}>下一页</button></div>}
    </div></section></>;
}
