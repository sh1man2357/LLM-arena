import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Pencil, RotateCcw, Trash2 } from 'lucide-react';
import { api, useResource } from './api';
import { useRevision } from './App';
import { Badge, ErrorPanel, labels, outcome } from './ui';
import type { Match, GameId } from './types';
import { gameNames } from './games';

const active = (run: Match) => ['pending', 'running'].includes(run.status);

export function History({game = 'bomberman'}: {game?: GameId}) {
  const [refresh, setRefresh] = useState(0), [offset, setOffset] = useState(0);
  const [q, setQuery] = useState(''), [status, setStatus] = useState(''), [trashed, setTrashed] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [editing, setEditing] = useState<string>(), [title, setTitle] = useState('');
  const [working, setWorking] = useState(false), [message, setMessage] = useState(''), [error, setError] = useState('');
  const guard = useRef(false);
  const params = new URLSearchParams({offset: String(offset), limit: '20', q, trashed: String(trashed), game_id: game});
  useEffect(() => {setOffset(0);setSelected([]);setEditing(undefined);}, [game]);
  if (status) params.set('status', status);
  const runs = useResource<{items: Match[]; total: number}>(`/api/v1/matches?${params}`, useRevision() + refresh);
  const items = runs.data?.items || [];
  const selectable = items.filter(run => trashed || !active(run)).map(run => run.id);
  const allSelected = selectable.length > 0 && selectable.every(id => selected.includes(id));
  useEffect(() => {
    if (!runs.data) return;
    setSelected(previous => previous.filter(id => runs.data!.items.some(run => run.id === id && (trashed || !active(run)))));
    if (offset >= runs.data.total && offset > 0) setOffset(Math.max(0, Math.floor((runs.data.total - 1) / 20) * 20));
  }, [runs.data, offset, trashed]);
  function resetView() { setOffset(0); setSelected([]); setEditing(undefined); setMessage(''); setError(''); }
  async function mutate(work: () => Promise<string>) {
    if (guard.current) return;
    guard.current = true; setWorking(true); setError(''); setMessage('');
    try { setMessage(await work()); setSelected([]); setEditing(undefined); setRefresh(r => r + 1); }
    catch (reason) { setError((reason as Error).message); }
    finally { guard.current = false; setWorking(false); }
  }
  function manage(ids: string[], allFinished = false) {
    if (!trashed && !window.confirm(allFinished
      ? '将当前筛选范围内所有已结束的对局移入回收站？正在执行的对局会保留。榜单将重新统计，可在回收站恢复。'
      : `将 ${ids.length} 条对局记录移入回收站？榜单将重新统计，可在回收站恢复。`)) return;
    void mutate(async () => {
      const result = await api<{changed: number}>('/api/v1/matches/manage', {
        method: 'POST', headers: {'X-Arena-Local': '1'},
        body: JSON.stringify({action: trashed ? 'restore' : 'trash', ids, all_finished: allFinished, q, game_id: game, ...(status ? {status} : {})}),
      });
      return trashed ? `已恢复 ${result.changed} 条对局记录。` : `已将 ${result.changed} 条对局记录移入回收站。`;
    });
  }
  function changePage(next: number) { setOffset(next); setSelected([]); setEditing(undefined); }
  return <section className="content-section history" id="history" aria-labelledby="history-title">
    <div className="section-heading"><h2 id="history-title">对局记录</h2></div>
    <div className="section-body">
      <div className="history-tabs" aria-label="记录范围">
        <button aria-pressed={!trashed} disabled={working} onClick={() => {setTrashed(false); resetView();}}>全部记录</button>
        <button aria-pressed={trashed} disabled={working} onClick={() => {setTrashed(true); resetView();}}><Trash2 aria-hidden="true" />回收站</button>
      </div>
      <div className="history-filters">
        <label>搜索对局<input type="search" value={q} maxLength={100} placeholder="名称、Bot、Seed 或记录 ID" disabled={working} onChange={e => {setQuery(e.target.value); resetView();}} /></label>
        <label>对局状态<select aria-label="对局状态" value={status} disabled={working} onChange={e => {setStatus(e.target.value); resetView();}}>
          <option value="">全部状态</option>{['pending', 'running', 'completed', 'failed', 'interrupted'].map(value => <option key={value} value={value}>{labels[value]}</option>)}
        </select></label>
      </div>
      <p className="history-hint">{trashed ? '恢复后可重新观看录像，并重新计入榜单。' : '删除的对局进入回收站，不计入榜单；准备中和运行中的对局不可删除。'}</p>
      {runs.error && <ErrorPanel message={runs.error} onRetry={runs.retry} />}
      {error && <div className="notice error" role="alert">{error}</div>}
      {message && <div className="notice" role="status">{message}</div>}
      <div className="history-toolbar">
        <label className="history-check"><input type="checkbox" checked={allSelected} disabled={working || !selectable.length || runs.loading} onChange={() => setSelected(allSelected ? [] : selectable)} />选择本页</label>
        <span className="muted">已选 {selected.length} 条</span>
        <button disabled={working || !selected.length} onClick={() => manage(selected)}>{trashed ? <RotateCcw aria-hidden="true" /> : <Trash2 aria-hidden="true" />}{trashed ? '恢复所选' : '删除所选'}</button>
        {!trashed && <button disabled={working || !runs.data?.total || runs.loading} onClick={() => manage([], true)}>清空已结束记录</button>}
      </div>
      {runs.loading && <p role="status">正在读取对局记录…</p>}
      {runs.data && !items.length && <p className="empty">{q || status ? '没有符合筛选条件的对局' : trashed ? '回收站为空' : '暂无对局'}</p>}
      <ul className="run-list managed-runs">{items.map(run => <li key={run.id} data-run-id={run.id}>
        <div className="history-row">
          <label className="history-check"><input type="checkbox" aria-label={`选择对局 ${run.title}`} disabled={working || (!trashed && active(run))} checked={selected.includes(run.id)} onChange={e => setSelected(previous => e.target.checked ? [...previous, run.id] : previous.filter(id => id !== run.id))} /></label>
          {trashed ? <div className="run-info"><div><strong>{run.title}</strong><span className="run-meta">{new Date(run.created).toLocaleString()}</span></div><Badge status={run.status} /></div>
            : <Link className="run-info" to={`/matches/${run.id}`}><div><strong>{run.title}</strong><span className="run-meta">{new Date(run.created).toLocaleString()}{run.status === 'completed' && run.result?.valid ? ` · ${outcome(run)}` : ''}<br />{gameNames[run.game_id || 'bomberman']}{run.game_id === 'gomoku' ? ` · 第 ${(run.pair_index || 0)+1} 盘` : ''} · Seed {run.map_seed}</span></div><Badge status={run.status} /><ArrowRight className="row-arrow" aria-hidden="true" /></Link>}
          <div className="history-row-actions">
            {!trashed && <button className="icon-button" aria-label={`重命名对局 ${run.title}`} title="重命名" disabled={working} onClick={() => {setEditing(run.id); setTitle(run.title); setError('');}}><Pencil aria-hidden="true" /></button>}
            <button className="icon-button" aria-label={`${trashed ? '恢复' : '删除'}对局 ${run.title}`} title={trashed ? '恢复' : active(run) ? '对局结束后可删除' : '移入回收站'} disabled={working || (!trashed && active(run))} onClick={() => manage([run.id])}>{trashed ? <RotateCcw aria-hidden="true" /> : <Trash2 aria-hidden="true" />}</button>
          </div>
        </div>
        {editing === run.id && <form className="history-rename" onSubmit={e => {e.preventDefault(); void mutate(async () => {
          await api<Match>(`/api/v1/matches/${run.id}`, {method: 'PATCH', headers: {'X-Arena-Local': '1'}, body: JSON.stringify({title: title.trim()})});
          return '对局名称已更新。';
        });}}>
          <label>对局名称<input autoFocus value={title} maxLength={100} required disabled={working} onChange={e => setTitle(e.target.value)} onKeyDown={e => {if (e.key === 'Escape' && !working) setEditing(undefined);}} /></label>
          <button disabled={working || !title.trim()}>保存名称</button><button type="button" disabled={working} onClick={() => setEditing(undefined)}>取消</button>
        </form>}
      </li>)}</ul>
      {runs.data && runs.data.total > 0 && <div className="pagination"><button disabled={working || !offset || runs.loading} onClick={() => changePage(Math.max(0, offset - 20))}>上一页</button><span>{offset + 1}～{Math.min(offset + 20, runs.data.total)} / {runs.data.total}</span><button disabled={working || offset + 20 >= runs.data.total || runs.loading} onClick={() => changePage(offset + 20)}>下一页</button></div>}
    </div>
  </section>;
}
