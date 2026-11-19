import { createContext, useContext, useEffect, useState } from 'react';
import { Link, NavLink, Route, Routes } from 'react-router-dom';
import { Home } from './Home';
import { BotLibrary } from './BotLibrary';
import { History } from './History';
import { Viewer } from './Viewer';
import { Leaderboard } from './Leaderboard';

const Revision = createContext(0);
export function useRevision() { return useContext(Revision); }

export function App() {
  const [revision, setRevision] = useState(0);
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    const events = new EventSource('/api/v1/events');
    let trailing: ReturnType<typeof setTimeout> | undefined;
    const refresh = () => setRevision(r => r + 1);
    events.onopen = () => { setConnected(true); refresh(); };
    events.onerror = () => setConnected(false);
    events.onmessage = event => {
      const notice = JSON.parse(event.data);
      if (notice.type === 'frame') return; // Viewer reads frames; other pages need terminal changes.
      clearTimeout(trailing); trailing = setTimeout(refresh, 100);
    };
    // Snapshot refresh also recovers a missed final notification.
    const timer = setInterval(refresh, 3000);
    return () => { clearInterval(timer); clearTimeout(trailing); events.close(); };
  }, []);
  return <Revision.Provider value={revision}><a className="skip-link" href="#main-content">跳到主要内容</a>
    <header className="topbar"><Link className="brand" to="/" aria-label="LLM Arena 首页"><span className="brand-mark" aria-hidden="true"><i /><i /><i /><i /></span>LLM ARENA</Link>
      <nav aria-label="主要页面"><NavLink to="/" end>对战</NavLink><NavLink to="/history">录像</NavLink><NavLink to="/bots">Bot 库</NavLink><NavLink to="/leaderboard">榜单</NavLink></nav></header>
    {!connected && <div className="connection-banner" role="status">正在连接服务…</div>}
    <main id="main-content"><Routes><Route path="/" element={<Home />} />
      <Route path="/bots" element={<BotLibrary />} /><Route path="/history" element={<History />} />
      <Route path="/matches/:id" element={<Viewer />} /><Route path="/leaderboard" element={<Leaderboard />} />
      <Route path="*" element={<div className="state-panel"><h1>页面不存在</h1><Link to="/">返回首页</Link></div>} />
    </Routes></main>
  </Revision.Provider>;
}
