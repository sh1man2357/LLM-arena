import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronDown, Play, Plus, Upload, X } from 'lucide-react';
import { api, useResource } from './api';
import { useRevision } from './App';
import { Badge, ErrorPanel, slotColor } from './ui';
import { History } from './History';
import type { Bot, Match, GameId } from './types';
import { gameNames, savedGame } from './games';

export function Home() {
  const revision = useRevision(), navigate = useNavigate();
  const [refresh, setRefresh] = useState(0);
  const [game, setGame] = useState<GameId>(savedGame), [opening, setOpening] = useState('empty');
  const bots = useResource<{items: Bot[]}>('/api/v1/bots', revision + refresh);
  const status = useResource<{busy: boolean; operation: string | null}>('/api/v1/status', revision + refresh);
  const [file, setFile] = useState<File>(), [name, setName] = useState('');
  const [slots, setSlots] = useState(['', '']), [seed, setSeed] = useState('');
  const [mode, setMode] = useState('bots'), [humanSlot, setHumanSlot] = useState(0);
  const human = game === 'gomoku' && mode === 'human';
  const [working, setWorking] = useState(false), [message, setMessage] = useState('');
  const guard = useRef(false);
  const importKey = useRef(crypto.randomUUID()), runKey = useRef(crypto.randomUUID());
  const gameBots = bots.data?.items.filter(b => (b.game_id || 'bomberman') === game) || [];
  const ready = gameBots.filter(b => b.status === 'ready');
  function changeGame(value: GameId) { setGame(value); sessionStorage.setItem('arena.game', value); setSlots(['','']); setMessage(''); }
  useEffect(() => {
    setSlots(current => current.map((id, i) => ready.some(b => b.id === id) ? id : ready[i % Math.max(1,ready.length)]?.id || ''));
  }, [bots.data, game]);
  useEffect(() => { importKey.current = crypto.randomUUID(); }, [file, name, game]);
  useEffect(() => { runKey.current = crypto.randomUUID(); }, [slots, seed, game, opening, mode, humanSlot]);
  const busy = working || status.data?.busy || !status.data;
  async function act(work: () => Promise<void>) {
    if (guard.current) return;
    guard.current = true; setWorking(true); setMessage('');
    try { await work(); setRefresh(r => r + 1); }
    catch (error) { setMessage((error as Error).message); }
    finally { guard.current = false; setWorking(false); }
  }
  const resources = [bots, status];
  const error = resources.find(r => r.error);
  return <><div className="page-heading"><h1>对战</h1></div>
    {error && <ErrorPanel message={error.error} onRetry={() => resources.forEach(r => r.retry())} />}
    {message && <div className="notice error" role="alert">{message}</div>}
    <label className="game-picker">游戏<select aria-label="游戏" value={game} onChange={e => changeGame(e.target.value as GameId)}>{Object.entries(gameNames).map(([id,name]) => <option key={id} value={id}>{name}</option>)}</select></label>
    {status.data?.busy && <p className="notice" role="status">{status.data.operation === 'match' ? '对局运行中。' : '正在编译 Bot。'}</p>}
    <section className="content-section" id="new-match" aria-labelledby="run-title"><div className="section-heading"><h2 id="run-title">新对局</h2></div><div className="section-body"><form className="run-form" onSubmit={e => { e.preventDefault(); void act(async () => {
      const match = await api<Match>(human ? '/api/v1/human-matches' : '/api/v1/matches', {method: 'POST', headers: {'X-Arena-Local': '1', 'Idempotency-Key': runKey.current},
        body: JSON.stringify(human ? {bot_id: slots[0], human_slot: humanSlot} : {bot_ids: slots, game_id: game, ...(game === 'gomoku' ? {opening_mode: opening} : {}), ...(seed === '' ? {} : {map_seed: Number(seed)})})});
      navigate(`/matches/${match.id}`, {state: {autoplay: true}});
    }); }}>
      {game === 'gomoku' && <label className="game-picker">对战模式<select value={mode} onChange={e => setMode(e.target.value)}><option value="bots">Bot 对战</option><option value="human">人机对战</option></select></label>}
      <p className="form-hint">{human ? '15 × 15 自由五子棋 · 单盘，点击棋盘落子，自动保存录像，不计入 Bot 榜单。' : game === 'gomoku' ? '15 × 15 自由五子棋 · 自动进行两盘换色对战，支持自我对弈。' : `${slots.length} 个 Bot 各自为战 · 支持 2～8 人。回合结束存活 +1 分，击杀 +100 分，按总积分排名。`}</p>
      <div className="match-picker">{human ? <>
        <label>对手 Bot<select value={slots[0]} onChange={e => setSlots([e.target.value, slots[1]])}><option value="">选择 Bot</option>{ready.map(b => <option key={b.id} value={b.id}>{b.baseline ? '基准 BOT · 0 分' : b.name}</option>)}</select></label>
        <label>你的执子<select value={humanSlot} onChange={e => setHumanSlot(Number(e.target.value))}><option value={0}>黑棋 · 先手</option><option value={1}>白棋 · 后手</option></select></label>
      </> : slots.map((id, slot) => <div className="slot-picker" key={slot}>
        <label><span className="slot-label"><i className="slot-dot" style={{background: game === 'gomoku' ? (slot === 0 ? '#202226' : '#faf7f0') : slotColor(slot)}} aria-hidden="true" />{game === 'gomoku' ? (slot === 0 ? '首盘黑棋' : '首盘白棋') : `Bot ${slot}`}</span>
          <select value={id} onChange={e => setSlots(current => current.map((value, i) => i === slot ? e.target.value : value))}>
            <option value="">选择 Bot</option>{ready.map(b => <option key={b.id} value={b.id}>{b.baseline ? '基准 BOT · 0 分' : b.name}</option>)}</select></label>
        {game === 'bomberman' && <button type="button" className="icon-button" aria-label={`移除 Bot ${slot}`} disabled={slots.length <= 2} onClick={() => setSlots(current => current.filter((_, i) => i !== slot))}><X aria-hidden="true" /></button>}
      </div>)}</div>
      {game === 'bomberman' && <button type="button" className="add-slot" disabled={slots.length >= 8} onClick={() => setSlots(current => [...current, (ready.find(b => !current.includes(b.id)) || ready[0])?.id || ''])}><Plus aria-hidden="true" />增加 Bot</button>}
      <div className="run-actions">{!human && <details><summary>{game === 'gomoku' ? '开局设置' : '地图设置'}<ChevronDown className="disclosure-chevron" aria-hidden="true" /></summary>
        {game === 'gomoku' && <label>开局<select aria-label="开局" value={opening} onChange={e => setOpening(e.target.value)}><option value="empty">空棋盘</option><option value="library">固定开局库（三手）</option></select></label>}
        <label>{game === 'gomoku' ? '开局 Seed' : '地图 Seed'}<input type="number" min="0" max="4294967295" step="1" value={seed} onChange={e => setSeed(e.target.value)} placeholder="随机" /></label></details>}<button className="primary" disabled={busy || (human ? !slots[0] : slots.some(id => !id))}><Play aria-hidden="true" />开始对战</button></div>
      {bots.data && !ready.length && <p className="form-hint">请先<a href="#bots">导入 Bot</a>。</p>}
    </form></div></section>
    <section className="content-section" id="bots" aria-labelledby="bots-title"><div className="section-heading"><h2 id="bots-title">Bot</h2></div><div className="section-body">
      <details className="import-disclosure"><summary><Upload aria-hidden="true" />导入 Bot<ChevronDown className="disclosure-chevron" aria-hidden="true" /></summary><form className="import-form" onSubmit={e => { e.preventDefault(); void act(async () => {
        if (!file) throw new Error('请选择 bot.cpp。');
        if (file.size > 1024 * 1024) throw new Error('源码超过 1 MiB。');
        const form = new FormData(); form.append('file', file); form.append('name', name.trim()); form.append('game_id', game);
        await api<Bot>('/api/v1/bots', {method: 'POST', headers: {'X-Arena-Local': '1', 'Idempotency-Key': importKey.current}, body: form});
        importKey.current = crypto.randomUUID();
      }); }}><label>Bot 所属游戏<select aria-label="Bot 所属游戏" value={game} onChange={e => changeGame(e.target.value as GameId)}>{Object.entries(gameNames).map(([id,name]) => <option key={id} value={id}>{name}</option>)}</select></label><label>Bot 文件<input type="file" accept=".cpp" aria-label="Bot 文件" required onChange={e => {
        const chosen = e.target.files?.[0]; setFile(chosen); setName(chosen?.name.replace(/\.cpp$/i, '') || '');
      }} /></label><label>名称<input value={name} maxLength={100} onChange={e => setName(e.target.value)} placeholder="默认使用文件名" /></label>
        <button disabled={busy || !file}><Upload aria-hidden="true" />导入 Bot</button></form></details>
      {bots.loading && <p role="status">正在读取 Bot…</p>}
      {bots.data && !gameBots.length && <p className="empty">暂无{gameNames[game]} Bot</p>}
      <ul className="bot-list">{gameBots.map(bot => <li key={bot.id} data-bot-id={bot.id}>
        <div className="bot-row"><strong>{bot.baseline ? '基准 BOT · 0 分' : bot.name}</strong><Badge status={bot.status} /></div>
        {bot.diagnostic && <p className="error-text">{bot.diagnostic}</p>}
        {(bot.compile_log?.stderr || bot.compile_log?.stdout) && <details><summary>编译日志<ChevronDown className="disclosure-chevron" aria-hidden="true" /></summary><pre>{bot.compile_log.stderr}{bot.compile_log.stdout}</pre></details>}
      </li>)}</ul>
    </div></section>
    <History game={game} /></>;
}
