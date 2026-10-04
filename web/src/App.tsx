import { createContext, useContext, useEffect, useState } from 'react';
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { useResource } from './api';
import { Icon } from './ui';
import { Hall, Batch, Entrants, EntrantPage, Manage, Batches } from './pages';
import { Viewer } from './Viewer';

const Revision = createContext(0);
export function useRevision() { return useContext(Revision); }

export function App() {
  const [revision, setRevision] = useState(0);
  const [connected, setConnected] = useState(false);
  const health = useResource<{status: string; app_version: string}>('/health', revision);
  const location = useLocation();
  useEffect(() => {
    const events = new EventSource('/api/v1/events');
    let last = 0;
    events.onopen = () => setConnected(true);
    events.onerror = () => setConnected(false);
    events.onmessage = () => { if (performance.now() - last > 350) { last = performance.now(); setRevision(r => r + 1); } };
    return () => events.close();
  }, []);
  useEffect(() => { window.scrollTo(0, 0); }, [location.pathname]);
  return <Revision.Provider value={revision}><div className="app-shell">
    <aside className="rail"><Link to="/" className="brand" aria-label="LLM Arena 比赛大厅"><span /><span /><span /><span /></Link>
      <nav aria-label="主要页面">
        <NavLink to="/" end title="比赛大厅"><Icon name="grid" /><span>大厅</span></NavLink>
        <NavLink to="/tournaments" title="批次与成绩"><Icon name="trophy" /><span>赛程</span></NavLink>
        <NavLink to="/entrants" title="参赛者"><Icon name="people" /><span>参赛</span></NavLink>
        <NavLink to="/manage" title="主办方工作台"><Icon name="sliders" /><span>管理</span></NavLink>
      </nav><div className="rail-footer"><span className={`connection-dot ${connected ? 'online' : ''}`} /><span>本地</span></div>
    </aside>
    <div className="workspace"><header className="topbar"><Link to="/" className="wordmark">LLM <strong>ARENA</strong><span className="version-tag">02</span></Link>
      <span className="topbar-center">策略竞技 · 确定性实验</span><span className="topbar-status"><span className={`connection-dot ${connected ? 'online' : ''}`} />{connected ? '本地服务已连接' : '正在恢复连接'}</span>
    </header>
    {!connected && !health.loading && <div className="connection-banner" role="status">事件连接暂时中断，正在重连。已加载的回放仍可操作。</div>}
    <main><Routes>
      <Route path="/" element={<Hall />} /><Route path="/matches/:id" element={<Viewer />} />
      <Route path="/tournaments" element={<Batches />} /><Route path="/tournaments/:id" element={<Batch />} />
      <Route path="/entrants" element={<Entrants />} /><Route path="/entrants/:id" element={<EntrantPage />} />
      <Route path="/manage" element={<Manage />} /><Route path="*" element={<div className="state-panel"><h1>页面不存在</h1><Link to="/">回到比赛大厅</Link></div>} />
    </Routes></main>
    <footer className="site-footer"><span>LLM Arena <span className="mono">v{health.data?.app_version || '0.2.0'}</span></span><span>双人规则 1 · C++20 / WASM · 可复现比赛</span><span>观赛速度不影响比赛</span></footer>
    </div></div></Revision.Provider>;
}
