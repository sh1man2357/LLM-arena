import type { GameId } from './types';
export const gameNames: Record<GameId, string> = {bomberman: '炸弹人', gomoku: '五子棋'};
export function savedGame(): GameId { return sessionStorage.getItem('arena.game') === 'gomoku' ? 'gomoku' : 'bomberman'; }
