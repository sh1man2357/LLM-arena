import type { ReactNode } from 'react';
import { RotateCcw } from 'lucide-react';

export const labels: Record<string, string> = {
  pending: '准备中', processing: '编译中', ready: '可运行', running: '运行中',
  completed: '已结束', failed: '失败', interrupted: '已中断',
  last_survivor: '仅剩一名存活者', all_eliminated: '全部出局', tick_limit: '回合上限',
  initialization_end: '初始化结束', infrastructure_failure: '运行失败',
  fuel: '计算预算耗尽', invalid_action: '非法动作', trap: 'Bot 崩溃',
  five_in_row: '连成五子', board_full: '棋盘已满', resignation: '主动认输',
  illegal_move: '非法落子', bot_fault: 'Bot 故障判负', initialization_failure: '初始化故障', occupied: '落在已有棋子的位置',
};
export const playerTokens = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven'];
export const slotColor = (slot: number) => `var(--player-${playerTokens[slot]})`;
export function playerStateLabel(player: {alive: boolean; death_tick: number | null}) {
  return player.alive ? '存活' : player.death_tick === -1 ? '初始化出局' : `第 ${player.death_tick} 回合出局`;
}
export function Badge({status}: {status: string}) {
  return <span className={`badge ${status}`}>{labels[status] || status}</span>;
}
export function BaselineMark() {
  return <span className="baseline-mark" title="实力基准，固定为 0 分；可编辑名称和备注，不可删除。">基准 BOT · 0 分</span>;
}
export const botLabel = (bot: {name: string; baseline: boolean}) => `${bot.name}${bot.baseline ? ' · 基准 BOT · 0 分' : ''}`;
export function State({title, children}: {title: string; children?: ReactNode}) {
  return <div className="state-panel" role="status"><h2>{title}</h2>{children}</div>;
}
export function ErrorPanel({message, onRetry}: {message: string; onRetry: () => void}) {
  return <div className="notice error" role="alert"><p>{message}</p><button onClick={onRetry}><RotateCcw aria-hidden="true" />重试</button></div>;
}
export function outcome(match: MatchLike) {
  if (match.status !== 'completed' || !match.result?.valid) return labels[match.status] || match.status;
  const top = Math.max(...match.result.players.map((p: any) => p.placement_score));
  const winners = match.result.players.filter((p: any) => p.placement_score === top);
  const name = (id: number) => match.entrants.find(e => e.slot === id)?.name || `Bot ${id}`;
  if (winners.length === 1) return `${name(winners[0].id)} 获胜`;
  return winners.length === match.entrants.length ? '平局' : `${winners.map((p: any) => `${name(p.id)}（${p.id}）`).join('、')} 并列第一`;
}
type MatchLike = {status: string; result: any; entrants: {slot: number; name?: string}[]};
