import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Maximize, Pause, Play, Radio, RotateCcw, SkipBack, SkipForward, StepBack, StepForward } from 'lucide-react';
import { api, useResource } from './api';
import { useRevision } from './App';
import { Board } from './Board';
import { GomokuBoard } from './GomokuBoard';
import { appendConfirmed, completeSnapshot } from './live';
import { Badge, ErrorPanel, labels, outcome, playerStateLabel, slotColor, State } from './ui';
import type { Match, Replay, GomokuWorld, World } from './types';

export function Viewer() {
  const { id } = useParams(), navigate = useNavigate(), location = useLocation();
  const match = useResource<Match>(`/api/v1/matches/${id}`, useRevision());
  const status = useResource<{busy: boolean}>('/api/v1/status', useRevision());
  const [data, setData] = useState<Replay>(), [error, setError] = useState(''), [retry, setRetry] = useState(0);
  const [seq, setSeq] = useState(0), [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1), [rerunning, setRerunning] = useState(false);
  const [actionError, setActionError] = useState('');
  const [numbers, setNumbers] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submittedTick, setSubmittedTick] = useState<number | null>(null);
  const moveGuard = useRef(false);
  const followingHuman = useRef(false);
  const latest = useRef<Replay | undefined>(undefined), playbackInitialized = useRef(false), stage = useRef<HTMLDivElement>(null);
  const rerunGuard = useRef(false), rerunKey = useRef(crypto.randomUUID());
  latest.current = data;
  useEffect(() => {
    setData(undefined); setSeq(0); setPlaying(false); setError(''); setActionError(''); setSubmittedTick(null);
    latest.current = undefined; playbackInitialized.current = false; followingHuman.current = false; rerunKey.current = crypto.randomUUID();
  }, [id]);
  useEffect(() => {
    if (match.errorStatus === 404) return;
    let cancelled = false, fetching = false;
    const active = !match.data || ['pending', 'running'].includes(match.data.status);
    async function readFrames() {
      if (fetching) return;
      fetching = true;
      try {
        const value = latest.current;
        const fresh = await api<Replay>(`/api/v1/matches/${id}/frames${active && value ? `?after_seq=${value.frames.length - 1}&attempt_id=${encodeURIComponent(value.attempt_id)}` : ''}`);
        if (cancelled) return;
        let merged = active ? appendConfirmed(value, fresh) : (completeSnapshot(fresh) ? fresh : undefined);
        if (!merged) {
          const full = await api<Replay>(`/api/v1/matches/${id}/frames`);
          if (cancelled) return;
          if (!completeSnapshot(full)) throw new Error('运行帧存在缺口，请重新读取。');
          merged = full;
        }
        latest.current = merged; setData(merged); setError('');
      } catch (err) { if (!cancelled) setError((err as Error).message); }
      finally { fetching = false; }
    }
    void readFrames();
    const timer = active ? setInterval(() => void readFrames(), 400) : undefined;
    return () => { cancelled = true; clearInterval(timer); };
  }, [id, match.data?.status, match.errorStatus, retry]);
  const running = match.data?.status === 'running' || match.data?.status === 'pending';
  const liveHuman = match.data?.mode === 'human' && running;
  const max = Math.max(0, (data?.frames.length || 1) - 1);
  const hasNextFrame = seq < max;
  const waiting = playing && !hasNextFrame && !!data?.partial;
  useEffect(() => {
    if (!playbackInitialized.current && data?.frames.length && data === latest.current) {
      playbackInitialized.current = true;
      setPlaying(!liveHuman && (data.partial || location.state?.autoplay === true));
      if (location.state?.autoplay) navigate(location.pathname + location.search, {
        replace: true, state: {...location.state, autoplay: false},
      });
    }
  }, [data, location.state, location.pathname, location.search, navigate, liveHuman]);
  useEffect(() => {
    if (liveHuman) { followingHuman.current = true; setSeq(max); setPlaying(false); }
    else if (followingHuman.current && data && !data.partial) { setSeq(max); followingHuman.current = false; }
  }, [liveHuman, max, data?.partial]);
  useEffect(() => {
    if (!playing) return;
    if (!hasNextFrame) {
      if (data && !data.partial) setPlaying(false);
      return;
    }
    // Schedule after each displayed frame; late timers never skip buffered Ticks.
    const timer = setTimeout(() => setSeq(seq + 1), 250 / speed);
    return () => clearTimeout(timer);
  }, [playing, speed, seq, id, hasNextFrame, data?.partial]);
  function seek(index: number) { setPlaying(false); setSeq(Math.max(0, Math.min(max, index))); }
  function play() {
    if (!playing && seq === max && !data?.partial) setSeq(0);
    setPlaying(value => !value);
  }
  async function fullscreen() {
    try { if (document.fullscreenElement) await document.exitFullscreen(); else await stage.current?.requestFullscreen(); }
    catch { setActionError('当前浏览器不支持全屏，可使用窗口最大化。'); }
  }
  useEffect(() => {
    function keyboard(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.altKey || (event.target as HTMLElement).closest('input,textarea,select,button,[contenteditable=true]')) return;
      if (![' ', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'f', 'F'].includes(event.key)) return;
      if (liveHuman && !['f', 'F'].includes(event.key)) return;
      event.preventDefault();
      if (event.key === ' ') play();
      else if (event.key === 'ArrowLeft') seek(seq - 1);
      else if (event.key === 'ArrowRight') seek(seq + 1);
      else if (event.key === 'Home') seek(0);
      else if (event.key === 'End') seek(max);
      else void fullscreen();
    }
    window.addEventListener('keydown', keyboard);
    return () => window.removeEventListener('keydown', keyboard);
  }, [seq, max, playing, data?.partial, liveHuman]);
  function retryReads() { match.retry(); setRetry(r => r + 1); }
  async function rerun() {
    if (rerunGuard.current) return;
    rerunGuard.current = true; setRerunning(true); setActionError('');
    try {
      const next = await api<Match>(`/api/v1/matches/${id}/rerun`, {method: 'POST', headers: {'X-Arena-Local': '1', 'Idempotency-Key': rerunKey.current}});
      navigate(`/matches/${next.id}`, {state: {autoplay: true}});
    } catch (err) { setActionError((err as Error).message); }
    finally { rerunGuard.current = false; setRerunning(false); }
  }
  async function humanMove(action: number) {
    const current = latest.current?.frames.at(-1)?.state as GomokuWorld | undefined;
    if (!current || moveGuard.current) return;
    moveGuard.current = true; setSubmitting(true); setActionError('');
    try {
      await api(`/api/v1/matches/${id}/actions`, {method: 'POST', headers: {'X-Arena-Local': '1'},
        body: JSON.stringify({tick: current.tick, action})});
      setSubmittedTick(current.tick);
      match.retry(); setRetry(r => r + 1);
    } catch (err) { setActionError((err as Error).message); match.retry(); setRetry(r => r + 1); }
    finally { moveGuard.current = false; setSubmitting(false); }
  }
  if (match.errorStatus === 404) return <><Link className="back-link" to="/"><ArrowLeft aria-hidden="true" />返回首页</Link><ErrorPanel message={match.error} onRetry={retryReads} /></>;
  const run = match.data;
  const gomoku = run?.game_id === 'gomoku';
  const hasFrames = !!data?.frames.length;
  const frame = hasFrames ? data!.frames[liveHuman ? max : Math.min(seq, max)] : undefined;
  const canMove = !!(liveHuman && frame && !error && !match.error && !submitting
    && submittedTick !== frame.state.tick
    && !(frame.state as GomokuWorld).reason && (frame.state as GomokuWorld).turn_color === run!.human_slot! + 1
    && run!.waiting_tick === frame.state.tick);
  const failed = run && ['failed', 'interrupted'].includes(run.status);
  const showResult = !data?.partial && seq === max && run?.result?.valid;
  return <><div className="viewer-heading"><Link className="back-link" to="/"><ArrowLeft aria-hidden="true" />返回首页</Link>
    {run && <button disabled={rerunning || !status.data || status.data.busy} onClick={() => void rerun()}><RotateCcw aria-hidden="true" />{run.mode === 'human' ? '再来一局' : '重赛'}</button>}</div>
    <div className="row-heading viewer-title"><h1>{run?.title || '加载对局…'}</h1>{run && <Badge status={run.status} />}</div>
    {run && data?.rules && !gomoku && <p className="form-hint">{data.rules.scoring_version === 2 ? '回合结算存活 +1 分 · 击杀 +100 分 · 总积分排名，同分并列' : '本局使用旧规则：按存活和死亡顺序排名，重赛保留原规则。'}</p>}
    {run?.pair && <nav className="pair-navigation" aria-label="换色对战">{run.pair.runs.map(leg => leg.deleted ? <span key={leg.id}>第 {leg.pair_index+1} 盘 · 回收站</span> : <Link key={leg.id} to={`/matches/${leg.id}`} aria-current={leg.id === id ? 'page' : undefined}>第 {leg.pair_index+1} 盘 · {labels[leg.status] || leg.status}</Link>)}</nav>}
    {(error || match.error) && <ErrorPanel message={error || match.error} onRetry={retryReads} />}
    {actionError && <p role="alert" className="notice error">{actionError}</p>}
    {run?.mode === 'human' && <p className="form-hint">人机对战 · 你执{run.human_slot === 0 ? '黑' : '白'} · 本局不计入 Bot 榜单。{liveHuman ? '可刷新或暂时离开，返回本局继续。' : ''}</p>}
    {failed && <div className="notice error" role="status"><strong>{labels[run.status]} · 本局不计分</strong><p>{run.diagnostic || '执行未完成，已保存的帧仍可查看。'}</p></div>}
    {!hasFrames && <State title={failed ? '无录像' : '加载画面…'} />}
    {run && frame && <section className="spectator-stage" ref={stage} data-frame-count={data!.frames.length} data-seq={frame.seq}>
      <div className="versus-bar">{run.entrants.map(entrant => {
        if (gomoku) {
          const state = frame.state as GomokuWorld, color = entrant.slot+1;
          const fault = state.fault?.players.includes(entrant.slot) ? state.fault.cause : null;
          return <div className="player-card" key={entrant.slot} style={{borderColor: color === 1 ? '#666' : '#faf7f0'}}><span className={`stone-label ${color === 1 ? 'black' : 'white'}`}>{color === 1 ? '黑' : '白'}</span><strong>{entrant.name}</strong><span className="player-state">{state.reason ? (state.winner === null ? '平局' : state.winner === entrant.slot ? '获胜' : '负') : state.turn_color === color ? '行棋中' : '等待对手'}{fault ? ` · ${labels[fault] || fault}` : ''}</span></div>;
        }
        const state = frame.state as World;
        const player = state.players[entrant.slot], faults = state.fault_counters[entrant.slot];
        const fault = frame.calls.find(call => call.id === entrant.slot)?.fault;
        return <div className="player-card" key={entrant.slot} style={{borderColor: slotColor(entrant.slot)}}><span className="player-number" style={{color: slotColor(entrant.slot)}}>{entrant.slot}</span>
          <strong>{entrant.name}</strong><span className="player-state">{playerStateLabel(player)}{player.score !== undefined ? ` · ${player.score} 分 · 击杀 ${player.kills}` : ''}{fault ? ` · ${labels[fault] || fault}` : faults.total ? ` · 故障 ${faults.total} 次` : ''}</span></div>;
      })}</div>
      {liveHuman && <div className="human-controls"><p role="status">{submitting ? '正在提交…' : canMove ? '轮到你了，点击空位落子。' : (frame.state as GomokuWorld).reason ? '对局正在结算…' : '等待 Bot 应手或棋盘更新…'}</p><button disabled={!canMove} onClick={() => void humanMove(225)}>认输</button></div>}
      <div className="board-wrap">{gomoku ? <GomokuBoard frame={frame} numbers={numbers} interactive={canMove} onMove={liveHuman ? action => void humanMove(action) : undefined} /> : <Board frame={frame} previous={seq > 0 ? data!.frames[seq - 1] : undefined} entrants={run.entrants} animate={playing} />}</div>
      <div className="playback"><div className="row-heading"><strong>{gomoku ? `已落 ${(frame.state as GomokuWorld).moves.length} 子${frame.tick === null ? ' · 初始状态' : ''}` : frame.tick === null ? '初始状态' : `回合 ${frame.tick}`}</strong><span className="muted">{seq} / {max}</span></div>
        {gomoku && <label className="move-numbers"><input type="checkbox" checked={numbers} onChange={e => setNumbers(e.target.checked)} />显示落子顺序</label>}
        {!liveHuman && <>
        {waiting && <p className="muted" role="status">等待下一帧…</p>}
        <input className="timeline" type="range" aria-label="时间轴" min="0" max={max} value={Math.min(seq, max)} onChange={e => seek(Number(e.target.value))} />
        <div className="controls"><div className="transport"><button className="icon-button" onClick={() => seek(0)} aria-label="回到初始帧" title="回到初始帧"><SkipBack aria-hidden="true" /></button><button className="icon-button" disabled={!seq} onClick={() => seek(seq - 1)} aria-label="上一帧" title="上一帧"><StepBack aria-hidden="true" /></button>
          <button className="primary icon-button" onClick={play} aria-label={playing ? '暂停' : '播放'} title={playing ? '暂停' : '播放'}>{playing ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}</button><button className="icon-button" disabled={seq >= max} onClick={() => seek(seq + 1)} aria-label="下一帧" title="下一帧"><StepForward aria-hidden="true" /></button><button className="icon-button" onClick={() => seek(max)} aria-label="最后一帧" title="最后一帧"><SkipForward aria-hidden="true" /></button></div><div className="playback-tools">
          <select className="speed" aria-label="倍速" title="播放速度" value={speed} onChange={e => setSpeed(Number(e.target.value))}>{[.25, .5, 1, 2, 4].map(value => <option key={value} value={value}>{value}×</option>)}</select>
          {running && <button className="icon-button" aria-label="回到最新" title="跳到已收到的最新帧，然后按顺序播放" onClick={() => { setSeq(max); setPlaying(true); }}><Radio aria-hidden="true" /></button>}<button className="icon-button" aria-label="全屏" title="全屏" onClick={() => void fullscreen()}><Maximize aria-hidden="true" /></button></div></div>
        </>}
        {showResult && <div className="result" role="status"><h2>{outcome(run)}</h2><p>{run.result!.ticks} {gomoku ? '步' : '回合'} · {labels[run.result!.reason] || run.result!.reason}</p>
          {run.pair?.complete && <p className="pair-score">两盘比分 {run.pair_index === 1 ? [...run.pair.score!].reverse().join(' : ') : run.pair.score!.join(' : ')}{!run.pair.counted ? ' · 整组不计入榜单' : ''}</p>}</div>}
        {showResult && <ol className="result-standings" aria-label="本局排名">{run.result!.groups.map((group: number[], index: number) => {
          const placement = 1 + run.result!.groups.slice(0, index).reduce((total: number, previous: number[]) => total + previous.length, 0);
          return group.map(slot => <li key={slot} style={{borderColor: slotColor(slot)}}><span>第 {placement} 名{group.length > 1 ? '（并列）' : ''}</span>
            <strong>{gomoku ? (slot === 0 ? '黑棋' : '白棋') : `Bot ${slot}`} · {run.entrants.find(e => e.slot === slot)?.name}</strong><span>{(() => {
              const p = run.result!.players.find((p: any) => p.id === slot);
              return p.score !== undefined ? `${p.score} 分 · 生存 ${p.survival_score} + 击杀 ${p.kill_score}（${p.kills} 人）` : `${p.placement_score.toFixed(3)} 名次分`;
            })()}</span></li>);
        })}</ol>}
      </div>
    </section>}
  </>;
}
