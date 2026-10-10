import type { ReactNode } from 'react';
import { RotateCcw } from 'lucide-react';

export const labels: Record<string, string> = {
  pending: '准备中', processing: '编译中', ready: '可运行', running: '运行中',
  completed: '已结束', failed: '失败', interrupted: '已中断',
  last_survivor: '对手出局', all_eliminated: '双方出局', tick_limit: '回合上限',
  initialization_end: '初始化结束', infrastructure_failure: '运行失败',
  fuel: '计算预算耗尽', invalid_action: '非法动作', trap: 'Bot 崩溃',
};
export const slotColor = (slot: number) => `var(--player-${slot === 0 ? 'zero' : 'one'})`;
export function playerStateLabel(player: {alive: boolean; death_tick: number | null}) {
  return player.alive ? '存活' : player.death_tick === -1 ? '初始化出局' : `第 ${player.death_tick} 回合出局`;
}
export function Badge({status}: {status: string}) {
  return <span className={`badge ${status}`}>{labels[status] || status}</span>;
}
export function State({title, children}: {title: string; children?: ReactNode}) {
  return <div className="state-panel" role="status"><h2>{title}</h2>{children}</div>;
}
export function ErrorPanel({message, onRetry}: {message: string; onRetry: () => void}) {
  return <div className="notice error" role="alert"><p>{message}</p><button onClick={onRetry}><RotateCcw aria-hidden="true" />重试</button></div>;
}
export function outcome(match: MatchLike) {
  if (match.status !== 'completed' || !match.result?.valid) return labels[match.status] || match.status;
  const winner = match.result.players.find((p: any) => p.placement_score === 1);
  return winner ? `${match.entrants.find(e => e.slot === winner.id)?.name || 'Bot'} 获胜` : '平局';
}
type MatchLike = {status: string; result: any; entrants: {slot: number; name?: string}[]};
