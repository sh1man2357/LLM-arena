import { useEffect, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { api, useResource } from './api';
import { Board } from './Board';
import { actionNames, BackLink, Badge, ErrorPanel, Icon, identityColor, labels, useNameLabel, State } from './ui';
import type { Match, Replay, Row } from './types';
import { useRevision } from './App';

export function Viewer() {
  const nameLabel = useNameLabel();
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const revision = useRevision();
  const match = useResource<Match>(`/api/v1/matches/${id}`, revision);
  const initial = useResource<Replay>(`/api/v1/matches/${id}/frames`);
  const [data, setData] = useState<Replay>();
  const [seq, setSeq] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [follow, setFollow] = useState(true);
  const [overlay, setOverlay] = useState(true);
  const [details, setDetails] = useState(true);
  const [player, setPlayer] = useState(0);
  const [mode, setMode] = useState<'player' | 'cell'>('player');
  const [cell, setCell] = useState<[number, number]>([1, 1]);
  const [hint, setHint] = useState('');
  const [liveError, setLiveError] = useState('');
  const stage = useRef<HTMLDivElement>(null);
  const wasLive = useRef(false);
  const latest = useRef<Replay | undefined>(undefined);
  latest.current = data;
  useEffect(() => { wasLive.current = false; setData(undefined); setPlaying(false); setFollow(!params.has('frame')); setSeq(0); }, [id]);
  useEffect(() => {
    if (initial.data) {
      setData(initial.data);
      const index = Number(params.get('frame') || 0);
      setSeq(Number.isFinite(index) ? Math.max(0, Math.min(initial.data.frames.length - 1, Math.floor(index))) : 0);
    }
  }, [initial.data]);
  useEffect(() => {
    if (match.data?.status !== 'running') return;
    let cancelled = false, fetching = false;
    const timer = setInterval(async () => {
      if (fetching) return;
      fetching = true;
      try {
        const value = latest.current;
        const fresh = await api<Replay>(`/api/v1/matches/${id}/frames?after_seq=${(value?.frames.length || 0) - 1}`);
        if (cancelled) return;
        setLiveError('');
        if (value && fresh.attempt_id !== value.attempt_id) {
          const reset = await api<Replay>(`/api/v1/matches/${id}/frames`); setData(reset); setSeq(0); return;
        }
        if (fresh.frames.length || fresh.result) setData(old => old ? { ...old, ...fresh, frames: [...old.frames, ...fresh.frames.filter(f => f.seq >= old.frames.length)] } : fresh);
      } catch (error) { if (!cancelled) setLiveError((error as Error).message); }
      finally { fetching = false; }
    }, 400);
    return () => { cancelled = true; clearInterval(timer); };
  }, [id, match.data?.status]);
  useEffect(() => {
    if (['completed', 'failed'].includes(match.data?.status || '') && latest.current?.partial) {
      const controller = new AbortController();
      api<Replay>(`/api/v1/matches/${id}/frames`, { signal: controller.signal }).then(setData).catch(e => { if (e.name !== 'AbortError') setLiveError(e.message); });
      return () => controller.abort();
    }
  }, [id, match.data?.status]);
  useEffect(() => {
    if (!data) return;
    const next = new URLSearchParams(params); next.set('frame', String(seq)); setParams(next, { replace: true });
  }, [seq]);
  useEffect(() => {
    if (!playing || !data) return;
    const timer = setInterval(() => setSeq(s => {
      if (s < data.frames.length - 1) return s + 1;
      if (!data.partial) setPlaying(false);
      return s;
    }), 250 / speed);
    return () => clearInterval(timer);
  }, [playing, speed, data]);
  useEffect(() => {
    if (match.data?.status === 'running') wasLive.current = true;
    if (follow && data && (match.data?.status === 'running' || (wasLive.current && ['completed', 'failed'].includes(match.data?.status || '')))) setSeq(Math.max(0, data.frames.length - 1));
  }, [data, follow, match.data?.status]);
  const max = Math.max(0, (data?.frames.length || 1) - 1);
  function seek(index: number) {
    setPlaying(false); setFollow(false);
    const value = Math.max(0, Math.min(max, index)); setSeq(value);
    const next = new URLSearchParams(params); next.set('frame', String(value)); setParams(next, { replace: true });
  }
  async function fullscreen() {
    try { if (document.fullscreenElement) await document.exitFullscreen(); else await stage.current?.requestFullscreen(); }
    catch { setHint('当前浏览器不支持全屏，请使用窗口最大化。'); }
  }
  useEffect(() => {
    function keyboard(e: KeyboardEvent) {
      if (e.ctrlKey || e.metaKey || e.altKey || (e.target as HTMLElement).closest('input,textarea,select,button,[contenteditable=true]')) return;
      const keys = [' ', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'f', 'F'];
      if (!keys.includes(e.key)) return;
      e.preventDefault();
      if (e.key === ' ') { setFollow(false); setPlaying(p => !p); }
      else if (e.key === 'ArrowLeft') seek(seq - 1); else if (e.key === 'ArrowRight') seek(seq + 1);
      else if (e.key === 'Home') seek(0); else if (e.key === 'End') seek(max); else void fullscreen();
    }
    window.addEventListener('keydown', keyboard);
    return () => window.removeEventListener('keydown', keyboard);
  }, [seq, max]);
  if (initial.error || match.error) return <ErrorPanel message={initial.error || match.error} />;
  if (!data?.frames.length || !match.data) return <State title="正在准备观赛画面" detail="等待第一个完整状态帧…" />;
  const frame = data.frames[Math.min(seq, max)];
  const current = frame.state.players[player];
  const position: [number, number] = mode === 'player' ? [current.x, current.y] : cell;
  const bomb = frame.state.bombs.find(b => b.x === position[0] && b.y === position[1]);
  const events: Row[] = data.frames.flatMap(f => f.events.filter(e => e.type !== 'move' && e.type !== 'destroy').map((e, i) => ({ ...e, seq: f.seq, tick: f.tick, key: `${f.seq}-${i}` })));
  const done = !!data.result && seq === max;
  const score = data.result?.players || [];
  const winner = score.find((p: any) => p.placement_score === 1);
  const outcome = !data.result?.valid ? '对局运行失败' : winner ? `${nameLabel(data.entrants[winner.id].id)} 获胜` : '双方平局';
  const phase = frame.tick === null ? '初始状态' : `Tick ${frame.tick} 已结算`;
  async function share() {
    const url = new URL(location.href); url.searchParams.set('frame', String(seq));
    try { await navigator.clipboard.writeText(url.toString()); setHint('已复制本地对局与帧链接。'); } catch { setHint(url.toString()); }
  }
  function image() {
    const canvas = stage.current?.querySelector('canvas');
    canvas?.toBlob(blob => { if (blob) { const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `${id}-frame-${seq}.png`; a.click(); URL.revokeObjectURL(url); } });
  }
  return <div className="viewer-page"><div className="viewer-top"><BackLink /><div className="viewer-tools">
    <button className="quiet" onClick={share}><Icon name="share" />复制帧链接</button><a className="button quiet" href={`/api/v1/exports/${id}`}><Icon name="share" />公开 Replay</a>
  </div></div><div className="match-heading"><div><p className="eyebrow">{match.data.tournament_id ? '批次对局' : '单局观赛'} · 双人规则 1</p><h1>{match.data.title}</h1></div><Badge status={match.data.status} /></div>
  <div className="spectator-stage" ref={stage}>
    <div className="versus-bar">{data.entrants.map((entrant, slot) => {
      const p = frame.state.players[slot]; const color = identityColor(entrant.id);
      return <button className={`versus-player ${player === slot && mode === 'player' ? 'selected' : ''}`} key={entrant.id}
        onClick={() => { setPlayer(slot); setMode('player'); }} style={{ '--player': color } as React.CSSProperties}>
        <span className={`player-marker p${slot}`}>{slot}</span><span><strong>{nameLabel(entrant.id)}</strong><small>槽位 {slot} · {p.alive ? '存活' : `淘汰于 Tick ${p.death_tick}`}</small></span>
        <span className="player-action">{actionNames[frame.actions.find(a => a.id === slot)?.action ?? 0]}<small>{p.x}, {p.y}</small></span>
      </button>;
    })}<span className="versus-divider">VS</span></div>
    <div className={`arena-layout ${details ? '' : 'details-hidden'}`}><section className="arena-scene">
      <div className="scene-meta"><span className="mono">{phase}</span><span>{data.verified ? '世界回放已验证' : data.partial ? '已确认的直播帧' : '未验证记录'}</span></div>
      <div className="board-wrap"><Board frame={frame} previous={data.frames[seq - 1]} entrants={data.entrants} overlay={overlay} selected={position}
        animate={playing} onSelect={p => { setCell(p); setMode('cell'); }} /></div>
      <div className="scene-caption"><span>13 × 11 <span className="muted">/ 地图完整公开</span></span><span>{frame.visual.coverage.length ? '正在显示本 Tick 事件叠层' : `下一结算 Tick ${frame.state.tick}`}</span></div>
      {liveError && <div className="connection-banner" role="status">连接中断，正在恢复。{liveError}</div>}
      <div className="playback-controls">
        <div className="transport"><button aria-label="初始帧 (Home)" title="初始帧 (Home)" onClick={() => seek(0)}><Icon name="start" /></button>
          <button aria-label="上一帧 (←)" title="上一帧 (←)" onClick={() => seek(seq - 1)} disabled={seq === 0}><Icon name="previous" /></button>
          <button className="primary play-button" aria-label={playing ? '暂停 (Space)' : '播放 (Space)'} title="播放 / 暂停 (Space)" onClick={() => { if (seq === max && !data.partial) setSeq(0); setFollow(false); setPlaying(p => !p); }}><Icon name={playing ? 'pause' : 'play'} size={20} /></button>
          <button aria-label="下一帧 (→)" title="下一帧 (→)" onClick={() => seek(seq + 1)} disabled={seq === max}><Icon name="next" /></button>
          <button aria-label="最后已接收帧 (End)" title="最后已接收帧 (End)" onClick={() => seek(max)}><Icon name="end" /></button>
        </div><label className="speed-control">速度<select aria-label="播放速度" value={speed} onChange={e => setSpeed(Number(e.target.value))}>{[.25, .5, 1, 2, 4].map(v => <option key={v} value={v}>{v}×</option>)}</select></label>
        <span className="frame-counter mono">{seq.toString().padStart(3, '0')} <span>/ {max}</span></span>
        <button className="quiet" aria-label="全屏 (F)" title="全屏 (F)" onClick={fullscreen}><Icon name="full" /></button>
      </div>
      <div className="timeline"><input aria-label="回放帧" type="range" min="0" max={max || 1} value={seq} onChange={e => seek(Number(e.target.value))} disabled={max === 0} />
        <div className="event-marks" aria-hidden="true">{events.filter(e => e.type === 'death' || e.type === 'fault' || e.type === 'explode').map(e => <span key={e.key} className={e.type} style={{ left: `${e.seq / (max || 1) * 100}%` }} />)}</div>
        <div className="timeline-labels"><span>初始</span><span>{match.data.status === 'running' ? '实时进度' : '结束'}</span></div>
      </div>
      <div className="viewer-options"><label><input type="checkbox" checked={overlay} onChange={e => setOverlay(e.target.checked)} />当前事件叠层</label>
        <button className="text-button" onClick={() => setDetails(d => !d)}>{details ? '收起详情' : '展开详情'}</button>
        {match.data.status === 'running' && <button className="text-button" onClick={() => { setFollow(true); setSeq(max); }}>{follow ? '正在跟随最新' : '回到最新'}</button>}
        <button className="text-button" onClick={image}><Icon name="image" />PNG</button>
      </div>
      {done && <div className={`result-banner ${data.result?.valid ? '' : 'failure'}`}><div><p className="eyebrow">对局结果</p><h2>{outcome}</h2><p>{labels[data.result!.reason]} · {data.result!.ticks} 次结算{data.result?.valid && !winner ? ' · 并列不额外破同分' : ''}</p></div><button onClick={() => seek(0)}><Icon name="refresh" />重新查看</button></div>}
    </section>
    {details && <aside className="inspector"><div className="inspector-tabs"><button className={mode === 'player' ? 'active' : ''} onClick={() => setMode('player')}>玩家</button><button className={mode === 'cell' ? 'active' : ''} onClick={() => setMode('cell')}>格子</button></div>
      <section className="inspector-card"><p className="eyebrow">{mode === 'player' ? '当前玩家状态' : '选中格子'}</p>
        {mode === 'player' ? <><h2 style={{ color: identityColor(data.entrants[player].id) }}>{nameLabel(data.entrants[player].id)}</h2>
          <dl><div><dt>坐标</dt><dd className="mono">{current.x}, {current.y}</dd></div><div><dt>状态</dt><dd>{current.alive ? '存活' : `Tick ${current.death_tick} 淘汰`}</dd></div>
            <div><dt>当前动作</dt><dd>{frame.actions.find(a => a.id === player) ? actionNames[frame.actions.find(a => a.id === player)!.action] : '未调用'}</dd></div>
            <div><dt>fuel 用量</dt><dd className="mono">{(frame.calls.find(c => c.id === player)?.fuel_used ?? data.initialization[player]?.fuel_used ?? 0).toLocaleString()}</dd></div>
            <div><dt>连续 / 累计故障</dt><dd className="mono">{frame.state.fault_counters[player].consecutive} / {frame.state.fault_counters[player].total}</dd></div>
            <div><dt>仍在场的炸弹</dt><dd>{frame.state.bombs.filter(b => b.owner_id === player).length} / {data.rules.bomb_capacity}</dd></div></dl>
          {frame.calls.find(c => c.id === player)?.fault && <Badge status="failed">{labels[frame.calls.find(c => c.id === player)!.fault]}</Badge>}
        </> : <><h2 className="mono">{position[0]}, {position[1]}</h2><div className="coordinate-inputs"><label>x<input aria-label="格子 x" type="number" min="0" max="12" value={cell[0]} onChange={e => setCell([Math.max(0, Math.min(12, Number(e.target.value) || 0)), cell[1]])} /></label><label>y<input aria-label="格子 y" type="number" min="0" max="10" value={cell[1]} onChange={e => setCell([cell[0], Math.max(0, Math.min(10, Number(e.target.value) || 0))])} /></label></div><dl><div><dt>地形</dt><dd>{['道路', '硬墙', '软墙'][frame.state.grid[position[1] * 13 + position[0]]]}</dd></div><div><dt>玩家</dt><dd>{frame.state.players.filter(p => p.alive && p.x === position[0] && p.y === position[1]).map(p => nameLabel(data.entrants[p.id].id)).join(', ') || '无'}</dd></div></dl></>}
        {bomb && <div className="bomb-info"><Icon name="bolt" /><div>炸弹 #{bomb.id}<small>{nameLabel(data.entrants[bomb.owner_id].id)} · Tick {bomb.explode_at_tick} 到期<br />剩余 {Math.max(0, bomb.explode_at_tick - frame.state.tick)} Tick · 范围 {bomb.range}</small></div></div>}
        {frame.visual.blocked_moves.includes(player) && mode === 'player' && <p className="muted">本 Tick 移动未成功；合法受阻动作不算故障。</p>}
      </section>
      <section className="events-panel"><div className="section-heading"><h3>关键事件</h3><span className="mono muted">{events.length}</span></div><div className="event-list">{events.length ? events.map(e => <button key={e.key} className={`event-row ${e.seq === seq ? 'selected' : ''}`} onClick={() => seek(e.seq)}><span className={`event-symbol ${e.type}`} /><span><strong>{labels[e.type]}</strong><small>{e.player !== undefined ? nameLabel(data.entrants[e.player].id) : e.bomb !== undefined ? `炸弹 #${e.bomb}` : ''}{e.fault ? ` · ${labels[e.fault]}` : ''}{e.cause === 'explosion' ? ' · 爆炸' : e.cause === 'runtime' ? ' · 运行故障' : ''}</small></span><span className="mono event-tick">{e.tick}</span></button>) : <p className="muted empty-note">本局尚无放弹、爆炸或淘汰事件。</p>}</div></section>
      <section className="inspector-footer"><p><Icon name="check" />{data.verified ? '已校验世界轨迹' : '结果尚未完成校验'}</p><span className="mono">{data.source_sha256?.slice(0, 16) || '直播记录'}</span><small>事件叠层用于检查当前 Tick，下一 Tick 不保留火焰。</small></section>
    </aside>}
    </div>
  </div>
  <div className="viewer-bottom">{match.data.swap_match_id && <Link className="button" to={`/matches/${match.data.swap_match_id}?frame=${seq}`}><Icon name="swap" />同地图换边局</Link>}{match.data.tournament_id && <Link className="button quiet" to={`/tournaments/${match.data.tournament_id}`}><Icon name="trophy" />查看批次成绩</Link>}<p role="status" className="muted">{hint}</p></div>
  </div>;
}
