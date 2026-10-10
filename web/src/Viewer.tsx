import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Maximize, Pause, Play, Radio, RotateCcw, SkipBack, SkipForward, StepBack, StepForward } from 'lucide-react';
import { api, useResource } from './api';
import { useRevision } from './App';
import { Board } from './Board';
import { appendConfirmed, completeSnapshot } from './live';
import { Badge, ErrorPanel, labels, outcome, playerStateLabel, slotColor, State } from './ui';
import type { Match, Replay } from './types';

export function Viewer() {
  const { id } = useParams(), navigate = useNavigate();
  const match = useResource<Match>(`/api/v1/matches/${id}`, useRevision());
  const status = useResource<{busy: boolean}>('/api/v1/status', useRevision());
  const [data, setData] = useState<Replay>(), [error, setError] = useState(''), [retry, setRetry] = useState(0);
  const [seq, setSeq] = useState(0), [playing, setPlaying] = useState(false), [follow, setFollow] = useState(true);
  const [speed, setSpeed] = useState(1), [rerunning, setRerunning] = useState(false);
  const [actionError, setActionError] = useState('');
  const latest = useRef<Replay | undefined>(undefined), sawLive = useRef(false), stage = useRef<HTMLDivElement>(null);
  const rerunGuard = useRef(false), rerunKey = useRef(crypto.randomUUID());
  latest.current = data;
  useEffect(() => {
    setData(undefined); setSeq(0); setPlaying(false); setFollow(true); setError(''); setActionError('');
    latest.current = undefined; sawLive.current = false; rerunKey.current = crypto.randomUUID();
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
  useEffect(() => {
    if (running) sawLive.current = true;
    if (follow && data?.frames.length && (running || sawLive.current)) setSeq(data.frames.length - 1);
  }, [data, running, follow]);
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => setSeq(current => {
      const value = latest.current;
      if (!value) return current;
      if (current < value.frames.length - 1) return current + 1;
      if (!value.partial) setPlaying(false);
      return current;
    }), 250 / speed);
    return () => clearInterval(timer);
  }, [playing, speed, id]);
  const max = Math.max(0, (data?.frames.length || 1) - 1);
  function seek(index: number) { setFollow(false); setPlaying(false); setSeq(Math.max(0, Math.min(max, index))); }
  function play() {
    setFollow(false);
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
  }, [seq, max, playing, data?.partial]);
  function retryReads() { match.retry(); setRetry(r => r + 1); }
  async function rerun() {
    if (rerunGuard.current) return;
    rerunGuard.current = true; setRerunning(true); setActionError('');
    try {
      const next = await api<Match>(`/api/v1/matches/${id}/rerun`, {method: 'POST', headers: {'X-Arena-Local': '1', 'Idempotency-Key': rerunKey.current}});
      navigate(`/matches/${next.id}`);
    } catch (err) { setActionError((err as Error).message); }
    finally { rerunGuard.current = false; setRerunning(false); }
  }
  if (match.errorStatus === 404) return <><Link className="back-link" to="/"><ArrowLeft aria-hidden="true" />返回首页</Link><ErrorPanel message={match.error} onRetry={retryReads} /></>;
  const run = match.data;
  const hasFrames = !!data?.frames.length;
  const frame = hasFrames ? data!.frames[Math.min(seq, max)] : undefined;
  const failed = run && ['failed', 'interrupted'].includes(run.status);
  return <><div className="viewer-heading"><Link className="back-link" to="/"><ArrowLeft aria-hidden="true" />返回首页</Link>
    {run && <button disabled={rerunning || !status.data || status.data.busy} onClick={() => void rerun()}><RotateCcw aria-hidden="true" />重赛</button>}</div>
    <div className="row-heading viewer-title"><h1>{run?.title || '加载对局…'}</h1>{run && <Badge status={run.status} />}</div>
    {(error || match.error) && <ErrorPanel message={error || match.error} onRetry={retryReads} />}
    {actionError && <p role="alert" className="notice error">{actionError}</p>}
    {failed && <div className="notice error" role="status"><strong>{labels[run.status]} · 本局不计分</strong><p>{run.diagnostic || '执行未完成，已保存的帧仍可查看。'}</p></div>}
    {!hasFrames && <State title={failed ? '无录像' : '加载画面…'} />}
    {run && frame && <section className="spectator-stage" ref={stage} data-frame-count={data!.frames.length} data-seq={frame.seq}>
      <div className="versus-bar">{run.entrants.map(entrant => {
        const player = frame.state.players[entrant.slot], faults = frame.state.fault_counters[entrant.slot];
        const fault = frame.calls.find(call => call.id === entrant.slot)?.fault;
        return <div className="player-card" key={entrant.slot} style={{borderColor: slotColor(entrant.slot)}}><span className="player-number" style={{color: slotColor(entrant.slot)}}>{entrant.slot}</span>
          <strong>{entrant.name}</strong><span className="player-state">{playerStateLabel(player)}{fault ? ` · ${labels[fault] || fault}` : faults.total ? ` · 故障 ${faults.total} 次` : ''}</span></div>;
      })}</div>
      <div className="board-wrap"><Board frame={frame} previous={seq > 0 ? data!.frames[seq - 1] : undefined} entrants={run.entrants} animate={playing || (follow && running)} /></div>
      <div className="playback"><div className="row-heading"><strong>{frame.tick === null ? '初始状态' : `回合 ${frame.tick}`}</strong><span className="muted">{seq} / {max}</span></div>
        <input className="timeline" type="range" aria-label="时间轴" min="0" max={max} value={Math.min(seq, max)} onChange={e => seek(Number(e.target.value))} />
        <div className="controls"><div className="transport"><button className="icon-button" onClick={() => seek(0)} aria-label="回到初始帧" title="回到初始帧"><SkipBack aria-hidden="true" /></button><button className="icon-button" disabled={!seq} onClick={() => seek(seq - 1)} aria-label="上一帧" title="上一帧"><StepBack aria-hidden="true" /></button>
          <button className="primary icon-button" onClick={play} aria-label={playing ? '暂停' : '播放'} title={playing ? '暂停' : '播放'}>{playing ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}</button><button className="icon-button" disabled={seq >= max} onClick={() => seek(seq + 1)} aria-label="下一帧" title="下一帧"><StepForward aria-hidden="true" /></button><button className="icon-button" onClick={() => seek(max)} aria-label="最后一帧" title="最后一帧"><SkipForward aria-hidden="true" /></button></div><div className="playback-tools">
          <select className="speed" aria-label="倍速" title="播放速度" value={speed} onChange={e => setSpeed(Number(e.target.value))}>{[.25, .5, 1, 2, 4].map(value => <option key={value} value={value}>{value}×</option>)}</select>
          {running && <button className="icon-button" aria-label="回到最新" title="回到最新" aria-pressed={follow} onClick={() => { setPlaying(false); setFollow(true); setSeq(max); }}><Radio aria-hidden="true" /></button>}<button className="icon-button" aria-label="全屏" title="全屏" onClick={() => void fullscreen()}><Maximize aria-hidden="true" /></button></div></div>
        {!running && run.result?.valid && <div className="result" role="status"><h2>{outcome(run)}</h2><p>{run.result.ticks} 回合 · {labels[run.result.reason] || run.result.reason}</p></div>}
        {!running && run.result?.valid && <ol className="result-standings" aria-label="本局排名">{run.result.groups.map((group: number[], index: number) => {
          const placement = 1 + run.result!.groups.slice(0, index).reduce((total: number, previous: number[]) => total + previous.length, 0);
          return group.map(slot => <li key={slot} style={{borderColor: slotColor(slot)}}><span>第 {placement} 名{group.length > 1 ? '（并列）' : ''}</span>
            <strong>Bot {slot} · {run.entrants.find(e => e.slot === slot)?.name}</strong><span>{run.result!.players.find((p: any) => p.id === slot).placement_score.toFixed(3)} 分</span></li>);
        })}</ol>}
      </div>
    </section>}
  </>;
}
