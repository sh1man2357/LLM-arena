import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, Bomb, Check, ChevronDown, Film, Grid2X2, Play, Plus, X } from 'lucide-react';
import { api, useResource } from './api';
import { useRevision } from './App';
import { botLabel, ErrorPanel, outcome, slotColor, slotInk } from './ui';
import { useGame } from './GamePicker';
import type { Bot, Match, GameId } from './types';
import { gameNames } from './games';

export function Home() {
  const revision = useRevision(), navigate = useNavigate();
  const {game, chooseGame} = useGame();
  const [opening, setOpening] = useState('empty');
  const bots = useResource<{items: Bot[]}>('/api/v1/bots', revision);
  const status = useResource<{busy: boolean; operation: string | null}>('/api/v1/status', revision);
  const running = useResource<{items: Match[]}>('/api/v1/matches?limit=1&status=running', revision);
  const recent = useResource<{items: Match[]}>(`/api/v1/matches?game_id=${game}&status=completed&limit=5`, revision);
  const [slots, setSlots] = useState(['', '']), [seed, setSeed] = useState('');
  const [mode, setMode] = useState('bots'), [humanSlot, setHumanSlot] = useState(0);
  const human = game === 'gomoku' && mode === 'human';
  const [working, setWorking] = useState(false), [message, setMessage] = useState('');
  const guard = useRef(false);
  const gameBots = bots.data?.items.filter(b => (b.game_id || 'bomberman') === game) || [];
  const ready = gameBots.filter(b => b.status === 'ready');
  const runningMatch = running.data?.items[0];
  function changeGame(value: GameId) { chooseGame(value); setSlots(['','']); setMessage(''); }
  useEffect(() => {
    setSlots(current => current.map((id, i) => ready.some(b => b.id === id) ? id : ready[i % Math.max(1,ready.length)]?.id || ''));
  }, [bots.data, game]);
  const busy = working || status.data?.busy || !status.data;
  async function startMatch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (guard.current) return;
    guard.current = true;
    setWorking(true);
    setMessage('');
    try {
      const body = JSON.stringify(human ? {bot_id: slots[0], human_slot: humanSlot} : {
        bot_ids: slots, game_id: game,
        ...(game === 'gomoku' ? {opening_mode: opening} : {}),
        ...(seed === '' ? {} : {map_seed: Number(seed)}),
      });
      // Keep an unacknowledged submission across data refreshes and page reloads.
      const storageKey = 'arena.pendingMatch';
      const pending = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
      const key = pending?.body === body ? pending.key : crypto.randomUUID();
      sessionStorage.setItem(storageKey, JSON.stringify({body, key}));
      const match = await api<Match>(human ? '/api/v1/human-matches' : '/api/v1/matches', {
        method: 'POST', headers: {'X-Arena-Local': '1', 'Idempotency-Key': key}, body,
      });
      sessionStorage.removeItem(storageKey);
      navigate(`/matches/${match.id}`, {state: {autoplay: true}});
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      guard.current = false;
      setWorking(false);
    }
  }
  const resources = [bots, status, running];
  const error = resources.find(r => r.error);
  return <><div className="page-heading"><h1>对战</h1></div>
    {error && <ErrorPanel message={error.error} onRetry={() => resources.forEach(r => r.retry())} />}
    {message && <div className="notice error" role="alert">{message}</div>}
    {runningMatch && <div className="running-bar">
      <i className="live-dot" aria-hidden="true" />
      <span className="live-label">正在运行</span>
      <b>{runningMatch.title}</b>
      <span className="muted">{gameNames[runningMatch.game_id || 'bomberman']} · {runningMatch.entrants.length} 名</span>
      <Link className="watch" to={`/matches/${runningMatch.id}`}>观看<ArrowRight aria-hidden="true" /></Link>
    </div>}
    <div className="lobby"><form className="match-card" onSubmit={startMatch}>
      <h2>新对局</h2>
      <fieldset className="game-choices"><legend className="sr-only">游戏</legend>
        {(['bomberman', 'gomoku'] as const).map(id => <label key={id} className={'game-choice ' + id}>
          <input type="radio" name="game" value={id} aria-label={gameNames[id]} checked={game === id} onChange={() => changeGame(id)} />
          {id === 'bomberman' ? <Bomb aria-hidden="true" /> : <Grid2X2 aria-hidden="true" />}
          <span><strong>{gameNames[id]}</strong><small>{id === 'bomberman' ? '2–8 人混战' : '双人对弈'}</small></span>
          {game === id && <Check className="choice-check" aria-hidden="true" />}
        </label>)}
      </fieldset>
      {game === 'gomoku' && <label className="inline-field">对战模式<select aria-label="对战模式" value={mode} onChange={e => setMode(e.target.value)}><option value="bots">Bot 对战</option><option value="human">人机对战</option></select></label>}
      <div className="match-main">
        <span className="field-title">{human ? '人机对战设置' : '参赛 Bot'}</span>
        <div className="match-picker">
          {human ? <>
            <label className="human-field">对手 Bot<select aria-label="对手 Bot" value={slots[0]} onChange={e => setSlots([e.target.value, slots[1]])}><option value="">选择 Bot</option>{ready.map(b => <option key={b.id} value={b.id}>{botLabel(b)}</option>)}</select></label>
            <label className="human-field">你的执子<select aria-label="你的执子" value={humanSlot} onChange={e => setHumanSlot(Number(e.target.value))}><option value={0}>黑棋 · 先手</option><option value={1}>白棋 · 后手</option></select></label>
          </> : slots.map((id, slot) => <div className="slot-picker" key={slot}>
            {game === 'gomoku'
              ? <i className={`slot-marker ${slot === 0 ? 'stone-black' : 'stone-white'}`} aria-hidden="true" />
              : <i className="slot-marker round" aria-hidden="true" style={{'--marker-bg': slotColor(slot), '--marker-ink': slotInk(slot)} as CSSProperties}>{slot}</i>}
            <select aria-label={game === 'gomoku' ? (slot === 0 ? '首盘黑棋' : '首盘白棋') : `Bot ${slot}`}
              value={id} onChange={e => setSlots(current => current.map((value, i) => i === slot ? e.target.value : value))}>
              <option value="">选择 Bot</option>{ready.map(b => <option key={b.id} value={b.id}>{botLabel(b)}</option>)}
            </select>
            {game === 'bomberman' && slots.length > 2 && <button type="button" className="icon-button" aria-label={`移除 Bot ${slot}`} title="移除该槽位" onClick={() => setSlots(current => current.filter((_, i) => i !== slot))}><X aria-hidden="true" /></button>}
          </div>)}
          {game === 'bomberman' && <button type="button" className="add-slot" disabled={slots.length >= 8} onClick={() => setSlots(current => [...current, (ready.find(b => !current.includes(b.id)) || ready[0])?.id || ''])}><Plus aria-hidden="true" />增加 Bot</button>}
        </div>
      </div>
      {!human && <details className="settings"><summary>{game === 'gomoku' ? '开局设置' : '地图设置'}<ChevronDown className="disclosure-chevron" aria-hidden="true" /></summary>
          {game === 'gomoku' && <label>开局<select aria-label="开局" value={opening} onChange={e => setOpening(e.target.value)}><option value="empty">空棋盘</option><option value="library">固定开局库（三手）</option></select></label>}
          <label>{game === 'gomoku' ? '开局 Seed' : '地图 Seed'}<input type="number" min="0" max="4294967295" step="1" value={seed} onChange={e => setSeed(e.target.value)} placeholder="随机" /></label></details>}
      <div className="launch-footer">
        <span className="match-note">{status.data?.busy ? (status.data.operation === 'match' ? '对局运行中' : '正在编译 Bot') :
          bots.data && !ready.length ? <Link to="/bots">请先到 Bot 库导入选手</Link> :
          human ? '单盘 · 不计入榜单' : game === 'gomoku' ? '同一开局 · 两盘换色' : `${slots.length} 名选手 · 同时行动`}</span>
        <button className="primary" disabled={busy || (human ? !slots[0] : slots.some(id => !id))}><Play aria-hidden="true" />开始对战</button>
      </div>
    </form>
    <section className="recent" aria-labelledby="recent-title">
      <header><h2 id="recent-title">最近录像</h2><Link to="/history">全部记录<ArrowRight aria-hidden="true" /></Link></header>
      {recent.error && <ErrorPanel message={recent.error} onRetry={recent.retry} />}
      {recent.loading && <p role="status">正在读取录像…</p>}
      {recent.data && !recent.data.items.length && <div className="recent-empty"><Film aria-hidden="true" />
        <strong>还没有{gameNames[game]}录像</strong><span>完成一场对局后，可以在这里回看。</span></div>}
      {!!recent.data?.items.length && <ul className="run-list recent-list">{recent.data.items.map(run =>
        <li key={run.id} data-run-id={run.id}><Link to={`/matches/${run.id}`}>
          <span className="replay-icon"><Play aria-hidden="true" /></span>
          <span className="replay-info"><strong>{run.title}</strong>
            <span>{run.mode === 'human' ? '人机对战 · 不计榜单' : run.pair_runs ? `换色第 ${(run.pair_index || 0) + 1} 盘` : `${run.entrants.length} 人混战`} · {outcome(run)}</span>
          </span>
          <time dateTime={run.created}>{new Date(run.created).toLocaleString('zh-CN', {month:'numeric', day:'numeric', hour:'2-digit', minute:'2-digit'})}</time>
        </Link></li>)}</ul>}
    </section></div>
  </>;
}
