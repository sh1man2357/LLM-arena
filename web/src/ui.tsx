import { createContext, useContext, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

const paths: Record<string, ReactNode> = {
  play: <path d="m9 5 11 7-11 7Z" />,
  pause: <><path d="M8 5v14M16 5v14" /></>,
  next: <><path d="m6 5 10 7-10 7ZM19 5v14" /></>,
  previous: <><path d="m18 5-10 7 10 7ZM5 5v14" /></>,
  end: <><path d="m4 6 8 6-8 6Zm9 0 8 6-8 6Z" /></>,
  start: <><path d="m20 6-8 6 8 6Zm-9 0-8 6 8 6Z" /></>,
  arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
  back: <path d="M20 12H4m6-6-6 6 6 6" />,
  grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
  trophy: <><path d="M7 3h10v7a5 5 0 0 1-10 0ZM7 5H3v3a4 4 0 0 0 4 4m10-7h4v3a4 4 0 0 1-4 4M12 15v6m-4 0h8" /></>,
  sliders: <path d="M3 6h18M3 12h18M3 18h18M8 3v6m8 0v6m-5 0v6" />,
  people: <><circle cx="9" cy="8" r="3" /><path d="M3 21v-3a6 6 0 0 1 12 0v3m1-17a3 3 0 0 1 0 6m2 4a5 5 0 0 1 3 5v2" /></>,
  full: <path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5" />,
  share: <><path d="M12 16V3m-5 5 5-5 5 5M5 13v8h14v-8" /></>,
  image: <><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8" cy="8" r="1" /><path d="m3 17 6-6 4 4 3-3 5 5" /></>,
  check: <path d="m5 12 4 4 10-11" />,
  refresh: <path d="M20 9a8 8 0 1 0 0 6M20 3v6h-6" />,
  swap: <path d="M3 7h18m-4-4 4 4-4 4M21 17H3m4-4-4 4 4 4" />,
  close: <path d="m5 5 14 14M19 5 5 19" />,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6m0-10v1" /></>,
  bolt: <path d="m13 2-9 12h7l-1 8 10-12h-7Z" />,
};

export function Icon({ name, size = 18 }: {name: string; size?: number}) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.info}</svg>;
}
export const labels: Record<string, string> = {
  completed: '已结束', complete: '完整批次', running: '进行中', queued: '排队中', failed: '运行失败', stopped: '已停止调度',
  stop_requested: '等待当前局结束', interrupted: '已中断', succeeded: '已完成', incomplete: '未完成', qualified: '资格通过', historical: '历史提交',
  submitted: '已交卷', open: '开发中', late: '逾期', missing: '未交卷', sealed: '封存', disclosed: '已披露', archived: '已归档',
  compiling: '编译与检查中', qualification_failed: '资格失败',
  last_survivor: '最后存活者', all_eliminated: '全部淘汰', tick_limit: '时间上限', initialization_end: '初始化结束', infrastructure_failure: '基础设施失败',
  fuel: 'fuel 耗尽', invalid_action: '非法动作', trap: '运行崩溃', move: '移动', place: '放置炸弹', explode: '爆炸', destroy: '软墙销毁', death: '淘汰', fault: '动作故障',
};
export function Badge({ status, children }: {status?: string; children?: ReactNode}) {
  return <span className={`badge ${status || ''}`}><span className="status-dot" />{children || labels[status || ''] || status}</span>;
}
export function State({ title, detail, children }: {title: string; detail?: string; children?: ReactNode}) {
  return <div className="state-panel"><Icon name="info" size={26} /><h2>{title}</h2>{detail && <p>{detail}</p>}{children}</div>;
}
export function ErrorPanel({ message }: {message: string}) {
  return <State title="暂时无法读取数据" detail={message}><button onClick={() => location.reload()}><Icon name="refresh" />重新连接</button></State>;
}
export function PageTitle({ eyebrow, title, children, detail }: {eyebrow: string; title: string; detail?: string; children?: ReactNode}) {
  return <div className="page-title"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{detail && <p className="muted">{detail}</p>}</div>{children}</div>;
}
export function BackLink() { return <Link className="back-link" to="/"><Icon name="back" />比赛大厅</Link>; }
export const actionNames = ['等待', '向上', '向右', '向下', '向左', '放弹'];
export function identityColor(id: string) {
  const colors = ['#69DCC9', '#EFB95B', '#A9ACF2', '#EFA7BE', '#91BDEB', '#BACE8B'];
  const known: Record<string, number> = { heuristic: 0, safe: 1, random: 2 };
  let hash = 0; for (const c of id) hash = ((hash * 31) + c.charCodeAt(0)) >>> 0;
  return colors[known[id] ?? hash % colors.length];
}
export function nameLabel(id: string) {
  const names: Record<string, string> = { heuristic: 'Heuristic', safe: 'Safe', random: 'Random' };
  return names[id] || id;
}
export const IdentityNames = createContext<Record<string, string>>({});
export function useNameLabel() {
  const names = useContext(IdentityNames);
  return (id: string) => names[id] || nameLabel(id);
}
