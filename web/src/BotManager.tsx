import { useEffect, useRef, useState } from 'react';
import { ChevronDown, Pencil, RotateCcw, Trash2 } from 'lucide-react';
import { useRevision } from './App';
import { api, useResource } from './api';
import { Badge, ErrorPanel, labels } from './ui';
import type { Bot, GameId } from './types';
import { gameNames } from './games';

const protectedBot = (bot: Bot) => bot.baseline || bot.status === 'processing' || bot.in_use;

export function BotManager({game, bots, loading, refresh, onChanged}: {
  game: GameId; bots?: Bot[]; loading: boolean; refresh: number; onChanged: () => void;
}) {
  const [trashed, setTrashed] = useState(false), [q, setQuery] = useState(''), [status, setStatus] = useState('');
  const [page, setPage] = useState(0), [selected, setSelected] = useState<string[]>([]);
  const [editing, setEditing] = useState<string>(), [name, setName] = useState(''), [description, setDescription] = useState('');
  const [working, setWorking] = useState(false), [message, setMessage] = useState(''), [error, setError] = useState('');
  const guard = useRef(false);
  const bin = useResource<{items: Bot[]}>(trashed ? `/api/v1/bots?trashed=true&game_id=${game}` : null, useRevision() + refresh);
  const source = trashed ? bin.data?.items : bots;
  const pending = trashed ? bin.loading : loading;
  const query = q.trim().toLocaleLowerCase();
  const filtered = (source || []).filter(bot => (!status || bot.status === status)
    && (!query || [bot.name, bot.description || '', bot.id, bot.baseline ? '基准 BOT' : ''].join(' ').toLocaleLowerCase().includes(query)));
  const total = filtered.length, offset = page * 20;
  const items = filtered.slice(offset, offset + 20);
  const selectable = items.filter(bot => trashed || !protectedBot(bot)).map(bot => bot.id);
  const allSelected = selectable.length > 0 && selectable.every(id => selected.includes(id));
  useEffect(() => {
    if (!source) return;
    setSelected(previous => previous.filter(id => selectable.includes(id)));
    if (offset >= total && page) setPage(Math.max(0, Math.ceil(total / 20) - 1));
    if (editing && !source.some(bot => bot.id === editing)) setEditing(undefined);
  }, [source, page, q, status]);
  function reset() { setPage(0); setSelected([]); setEditing(undefined); setError(''); setMessage(''); }
  async function mutate(work: () => Promise<string>) {
    if (guard.current) return;
    guard.current = true; setWorking(true); setError(''); setMessage('');
    try { setMessage(await work()); setEditing(undefined); setSelected([]); onChanged(); bin.retry(); }
    catch (reason) { setError((reason as Error).message); }
    finally { guard.current = false; setWorking(false); }
  }
  function manage(ids: string[]) {
    if (!trashed && !window.confirm(`将 ${ids.length} 个 Bot 移入回收站？源码与历史对局保留，可随时恢复。`)) return;
    void mutate(async () => {
      const result = await api<{changed: number}>('/api/v1/bots/manage', {method: 'POST', headers: {'X-Arena-Local': '1'},
        body: JSON.stringify({action: trashed ? 'restore' : 'trash', ids})});
      return trashed ? `已恢复 ${result.changed} 个 Bot。` : `已将 ${result.changed} 个 Bot 移入回收站。`;
    });
  }
  return <div className="bot-manager">
    <div className="history-tabs" aria-label="Bot 范围">
      <button aria-pressed={!trashed} disabled={working} onClick={() => {setTrashed(false); reset();}}>可用列表</button>
      <button aria-pressed={trashed} disabled={working} onClick={() => {setTrashed(true); reset();}}><Trash2 aria-hidden="true" />Bot 回收站</button>
    </div>
    <div className="history-filters">
      <label>搜索 Bot<input type="search" value={q} maxLength={100} placeholder="名称、备注或 Bot ID" disabled={working} onChange={e => {setQuery(e.target.value); reset();}} /></label>
      <label>Bot 状态<select aria-label="Bot 状态" value={status} disabled={working} onChange={e => {setStatus(e.target.value); reset();}}>
        <option value="">全部状态</option>{['ready', 'processing', 'failed'].map(value => <option value={value} key={value}>{labels[value]}</option>)}
      </select></label>
    </div>
    <p className="history-hint">{trashed ? '恢复后可重新选择参赛。历史对局和统计保留。' : '可编辑名称和备注；删除移入回收站。内置基准只读，编译中或参赛中的 Bot 暂不可删除。'}</p>
    {bin.error && <ErrorPanel message={bin.error} onRetry={bin.retry} />}
    {error && <p className="notice error" role="alert">{error}</p>}
    {message && <p className="notice" role="status">{message}</p>}
    <div className="history-toolbar">
      <label className="history-check"><input type="checkbox" checked={allSelected} disabled={working || pending || !selectable.length} onChange={() => setSelected(allSelected ? [] : selectable)} />选择本页 Bot</label>
      <span className="muted">已选 {selected.length} 个</span>
      <button disabled={working || pending || !selected.length} onClick={() => manage(selected)}>{trashed ? <RotateCcw aria-hidden="true" /> : <Trash2 aria-hidden="true" />}{trashed ? '恢复所选 Bot' : '删除所选 Bot'}</button>
    </div>
    {pending && <p role="status">正在读取 Bot…</p>}
    {source && !total && <p className="empty">{q || status ? '没有符合筛选条件的 Bot' : trashed ? 'Bot 回收站为空' : `暂无${gameNames[game]} Bot`}</p>}
    <ul className="bot-list">{items.map(bot => <li key={bot.id} data-bot-id={bot.id}>
      <div className="bot-manager-row">
        <label className="history-check"><input type="checkbox" aria-label={`选择 Bot ${bot.name}`} checked={selected.includes(bot.id)} disabled={working || (!trashed && !!protectedBot(bot))}
          onChange={e => setSelected(previous => e.target.checked ? [...previous, bot.id] : previous.filter(id => id !== bot.id))} /></label>
        <div className="bot-summary"><div className="bot-row"><strong>{bot.baseline ? '基准 BOT · 0 分' : bot.name}</strong><Badge status={bot.status} /></div>
          {bot.description && <p className="bot-description">{bot.description}</p>}
          <span className="run-meta">{gameNames[game]} · {new Date(bot.created).toLocaleString()}{bot.in_use ? ' · 使用中' : ''}{trashed ? ' · 已删除' : ''}</span>
        </div>
        {!bot.baseline && <div className="bot-actions">
          {!trashed && <button className="icon-button" aria-label={`编辑 Bot ${bot.name}`} title={bot.status === 'processing' ? '编译完成后可编辑' : '编辑信息'} disabled={working || bot.status === 'processing'} onClick={() => {setEditing(bot.id); setName(bot.name); setDescription(bot.description || ''); setError('');}}><Pencil aria-hidden="true" /></button>}
          <button className="icon-button" aria-label={`${trashed ? '恢复' : '删除'} Bot ${bot.name}`} title={trashed ? '恢复 Bot' : protectedBot(bot) ? '编译或对局完成后可删除' : '移入回收站'} disabled={working || (!trashed && !!protectedBot(bot))} onClick={() => manage([bot.id])}>{trashed ? <RotateCcw aria-hidden="true" /> : <Trash2 aria-hidden="true" />}</button>
        </div>}
      </div>
      {editing === bot.id && !trashed && <form className="bot-edit" onSubmit={e => {e.preventDefault(); void mutate(async () => {
        await api<Bot>(`/api/v1/bots/${bot.id}`, {method: 'PATCH', headers: {'X-Arena-Local': '1'}, body: JSON.stringify({name: name.trim(), description: description.trim()})});
        return 'Bot 信息已更新。';
      });}}>
        <label>Bot 名称<input autoFocus required maxLength={100} value={name} disabled={working} onChange={e => setName(e.target.value)} /></label>
        <label>Bot 备注<textarea rows={3} maxLength={1000} value={description} disabled={working} onChange={e => setDescription(e.target.value)} placeholder="记录模型、版本或策略说明" /></label>
        <div className="bot-actions"><button disabled={working || !name.trim()}>保存 Bot 信息</button><button type="button" disabled={working} onClick={() => setEditing(undefined)}>取消编辑</button></div>
      </form>}
      {bot.diagnostic && <p className="error-text">{bot.diagnostic}</p>}
      <details className="bot-details"><summary>Bot 详情<ChevronDown className="disclosure-chevron" aria-hidden="true" /></summary><p className="run-meta">ID：{bot.id}</p></details>
      {(bot.compile_log?.stderr || bot.compile_log?.stdout) && <details><summary>编译日志<ChevronDown className="disclosure-chevron" aria-hidden="true" /></summary><pre>{bot.compile_log.stderr}{bot.compile_log.stdout}</pre></details>}
    </li>)}</ul>
    {!!total && <div className="pagination"><button disabled={working || !page} onClick={() => {setPage(value => value - 1); setSelected([]); setEditing(undefined);}}>上一页 Bot</button><span>{offset + 1}～{Math.min(offset + 20, total)} / {total}</span><button disabled={working || offset + 20 >= total} onClick={() => {setPage(value => value + 1); setSelected([]); setEditing(undefined);}}>下一页 Bot</button></div>}
  </div>;
}
