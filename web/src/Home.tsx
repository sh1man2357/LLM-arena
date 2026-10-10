import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, ChevronDown, Play, Plus, Upload, X } from 'lucide-react';
import { api, useResource } from './api';
import { useRevision } from './App';
import { Badge, ErrorPanel, outcome, slotColor } from './ui';
import type { Bot, Match } from './types';

export function Home() {
  const revision = useRevision(), navigate = useNavigate();
  const [refresh, setRefresh] = useState(0), [offset, setOffset] = useState(0);
  const bots = useResource<{items: Bot[]}>('/api/v1/bots', revision + refresh);
  const runs = useResource<{items: Match[]; total: number}>(`/api/v1/matches?offset=${offset}&limit=20`, revision + refresh);
  const status = useResource<{busy: boolean; operation: string | null}>('/api/v1/status', revision + refresh);
  const [file, setFile] = useState<File>(), [name, setName] = useState('');
  const [slots, setSlots] = useState(['', '']), [seed, setSeed] = useState('');
  const [working, setWorking] = useState(false), [message, setMessage] = useState('');
  const guard = useRef(false);
  const importKey = useRef(crypto.randomUUID()), runKey = useRef(crypto.randomUUID());
  const ready = bots.data?.items.filter(b => b.status === 'ready') || [];
  useEffect(() => {
    if (ready.length) setSlots(current => current.map((id, i) => id || ready[i % ready.length].id));
  }, [bots.data]);
  useEffect(() => { importKey.current = crypto.randomUUID(); }, [file, name]);
  useEffect(() => { runKey.current = crypto.randomUUID(); }, [slots, seed]);
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
  return <><div className="page-heading"><h1>对战</h1></div>
    {error && <ErrorPanel message={error.error} onRetry={() => resources.forEach(r => r.retry())} />}
    {message && <div className="notice error" role="alert">{message}</div>}
    {status.data?.busy && <p className="notice" role="status">{status.data.operation === 'match' ? '对局运行中。' : '正在编译 Bot。'}</p>}
    <section className="content-section" id="new-match" aria-labelledby="run-title"><div className="section-heading"><h2 id="run-title">新对局</h2></div><div className="section-body"><form className="run-form" onSubmit={e => { e.preventDefault(); void act(async () => {
      const match = await api<Match>('/api/v1/matches', {method: 'POST', headers: {'X-Arena-Local': '1', 'Idempotency-Key': runKey.current},
        body: JSON.stringify({bot_ids: slots, ...(seed === '' ? {} : {map_seed: Number(seed)})})});
      navigate(`/matches/${match.id}`, {state: {autoplay: true}});
    }); }}><p className="form-hint">{slots.length} 个 Bot 各自为战 · 支持 2～8 人，同一个 Bot 可重复参赛。</p>
      <div className="match-picker">{slots.map((id, slot) => <div className="slot-picker" key={slot}>
        <label><span className="slot-label"><i className="slot-dot" style={{background: slotColor(slot)}} aria-hidden="true" />Bot {slot}</span>
          <select value={id} onChange={e => setSlots(current => current.map((value, i) => i === slot ? e.target.value : value))}>
            <option value="">选择 Bot</option>{ready.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
        <button type="button" className="icon-button" aria-label={`移除 Bot ${slot}`} disabled={slots.length <= 2} onClick={() => setSlots(current => current.filter((_, i) => i !== slot))}><X aria-hidden="true" /></button>
      </div>)}</div>
      <button type="button" className="add-slot" disabled={slots.length >= 8} onClick={() => setSlots(current => [...current, (ready.find(b => !current.includes(b.id)) || ready[0])?.id || ''])}><Plus aria-hidden="true" />增加 Bot</button>
      <div className="run-actions"><details><summary>地图设置<ChevronDown className="disclosure-chevron" aria-hidden="true" /></summary><label>地图 Seed<input type="number" min="0" max="4294967295" step="1" value={seed} onChange={e => setSeed(e.target.value)} placeholder="随机" /></label></details><button className="primary" disabled={busy || slots.some(id => !id)}><Play aria-hidden="true" />开始对战</button></div>
      {bots.data && !ready.length && <p className="form-hint">请先<a href="#bots">导入 Bot</a>。</p>}
    </form></div></section>
    <section className="content-section" id="bots" aria-labelledby="bots-title"><div className="section-heading"><h2 id="bots-title">Bot</h2></div><div className="section-body">
      <details className="import-disclosure"><summary><Upload aria-hidden="true" />导入 Bot<ChevronDown className="disclosure-chevron" aria-hidden="true" /></summary><form className="import-form" onSubmit={e => { e.preventDefault(); void act(async () => {
        if (!file) throw new Error('请选择 bot.cpp。');
        if (file.size > 1024 * 1024) throw new Error('源码超过 1 MiB。');
        const form = new FormData(); form.append('file', file); form.append('name', name.trim());
        await api<Bot>('/api/v1/bots', {method: 'POST', headers: {'X-Arena-Local': '1', 'Idempotency-Key': importKey.current}, body: form});
        importKey.current = crypto.randomUUID();
      }); }}><label>Bot 文件<input type="file" accept=".cpp" aria-label="Bot 文件" required onChange={e => {
        const chosen = e.target.files?.[0]; setFile(chosen); setName(chosen?.name.replace(/\.cpp$/i, '') || '');
      }} /></label><label>名称<input value={name} maxLength={100} onChange={e => setName(e.target.value)} placeholder="默认使用文件名" /></label>
        <button disabled={busy || !file}><Upload aria-hidden="true" />导入 Bot</button></form></details>
      {bots.loading && <p role="status">正在读取 Bot…</p>}
      {bots.data && !bots.data.items.length && <p className="empty">暂无 Bot</p>}
      <ul className="bot-list">{bots.data?.items.map(bot => <li key={bot.id} data-bot-id={bot.id}>
        <div className="bot-row"><strong>{bot.name}</strong><Badge status={bot.status} /></div>
        {bot.diagnostic && <p className="error-text">{bot.diagnostic}</p>}
        {(bot.compile_log?.stderr || bot.compile_log?.stdout) && <details><summary>编译日志<ChevronDown className="disclosure-chevron" aria-hidden="true" /></summary><pre>{bot.compile_log.stderr}{bot.compile_log.stdout}</pre></details>}
      </li>)}</ul>
    </div></section>
    <section className="content-section history" id="history" aria-labelledby="history-title"><div className="section-heading"><h2 id="history-title">对局记录</h2></div><div className="section-body">
      {runs.loading && <p role="status">正在读取运行记录…</p>}
      {runs.data && !runs.data.items.length && <p className="empty">暂无对局</p>}
      <ul className="run-list">{runs.data?.items.map(run => <li key={run.id}><Link to={`/matches/${run.id}`}><div><strong>{run.title}</strong><span className="run-meta">{new Date(run.created).toLocaleString()}{run.status === 'completed' && run.result?.valid ? ` · ${outcome(run)}` : ''}</span></div><Badge status={run.status} /><ArrowRight className="row-arrow" aria-hidden="true" /></Link></li>)}</ul>
      {runs.data && runs.data.total > 20 && <div className="pagination"><button disabled={!offset} onClick={() => setOffset(o => Math.max(0, o - 20))}>上一页</button><span>{offset + 1}～{Math.min(offset + 20, runs.data.total)} / {runs.data.total}</span><button disabled={offset + 20 >= runs.data.total} onClick={() => setOffset(o => o + 20)}>下一页</button></div>}
    </div></section></>;
}
