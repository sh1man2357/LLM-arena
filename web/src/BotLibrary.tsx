import { useRef, useState, type FormEvent } from 'react';
import { ChevronDown, Upload } from 'lucide-react';
import { BotManager } from './BotManager';
import { useRevision } from './App';
import { api, useResource } from './api';
import { GamePicker, useGame } from './GamePicker';
import { ErrorPanel } from './ui';
import type { Bot } from './types';

export function BotLibrary() {
  const {game, chooseGame} = useGame();
  const [refresh, setRefresh] = useState(0);
  const revision = useRevision() + refresh;
  const bots = useResource<{items: Bot[]}>('/api/v1/bots', revision);
  const status = useResource<{busy: boolean}>('/api/v1/status', revision);
  const [file, setFile] = useState<File>(), [name, setName] = useState('');
  const [working, setWorking] = useState(false), [error, setError] = useState('');
  const guard = useRef(false), importKey = useRef(crypto.randomUUID());
  const gameBots = bots.data?.items.filter(b => (b.game_id || 'bomberman') === game);
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (guard.current || !file) return;
    const form = event.currentTarget;
    guard.current = true; setWorking(true); setError('');
    try {
      if (file.size > 1024 * 1024) throw new Error('源码超过 1 MiB。');
      const body = new FormData();
      body.append('file', file); body.append('name', name.trim()); body.append('game_id', game);
      await api<Bot>('/api/v1/bots', {method: 'POST', headers: {'X-Arena-Local': '1', 'Idempotency-Key': importKey.current}, body});
      form.reset(); setFile(undefined); setName(''); importKey.current = crypto.randomUUID();
      setRefresh(r => r + 1);
    } catch (err) { setError((err as Error).message); }
    finally { guard.current = false; setWorking(false); }
  }
  const readError = bots.error || status.error;
  return <section id="bots">
    <header className="library-heading"><h1>Bot 库</h1><GamePicker game={game} disabled={working} chooseGame={next => {
      chooseGame(next); importKey.current = crypto.randomUUID(); setError('');
    }} /></header>
    {readError && <ErrorPanel message={readError} onRetry={() => {bots.retry(); status.retry();}} />}
    <details className="import-disclosure"><summary><Upload aria-hidden="true" />导入 Bot<ChevronDown className="disclosure-chevron" aria-hidden="true" /></summary>
      <form className="import-form" onSubmit={upload}>
        <label>Bot 文件<input type="file" required accept=".cpp" disabled={working} onChange={e => {
          const chosen = e.target.files?.[0]; setFile(chosen); setName(chosen?.name.replace(/\.cpp$/i, '') || '');
          importKey.current = crypto.randomUUID();
        }} /></label>
        <label>名称<input value={name} maxLength={100} disabled={working} placeholder="默认使用文件名" onChange={e => {
          setName(e.target.value); importKey.current = crypto.randomUUID();
        }} /></label>
        <button className="primary" disabled={working || !status.data || status.data.busy || !file}><Upload aria-hidden="true" />导入 Bot</button>
      </form>
      {error && <p className="notice error" role="alert">{error}</p>}
    </details>
    <BotManager key={game} game={game} bots={gameBots} loading={bots.loading} refresh={refresh} onChanged={() => setRefresh(r => r + 1)} />
  </section>;
}
