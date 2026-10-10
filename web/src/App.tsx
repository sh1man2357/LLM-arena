import { createContext, useContext, useEffect, useState } from 'react';
import { Link, NavLink, Route, Routes } from 'react-router-dom';
import { Grid2X2, Swords, Trophy } from 'lucide-react';
import { Home } from './Home';
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
    <header className="topbar"><Link className="brand" to="/" aria-label="LLM Arena 首页"><Grid2X2 aria-hidden="true" /><span>LLM ARENA</span></Link>
      <nav aria-label="主要页面"><NavLink to="/" end><Swords aria-hidden="true" />对战</NavLink><NavLink to="/leaderboard"><Trophy aria-hidden="true" />榜单</NavLink></nav></header>
    {!connected && <div className="connection-banner" role="status">正在连接服务…</div>}
    <main id="main-content"><Routes><Route path="/" element={<Home />} />
      <Route path="/matches/:id" element={<Viewer />} /><Route path="/leaderboard" element={<Leaderboard />} />
      <Route path="*" element={<div className="state-panel"><h1>页面不存在</h1><Link to="/">返回首页</Link></div>} />
    </Routes></main>
  </Revision.Provider>;
}
