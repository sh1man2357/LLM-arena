import { useState } from 'react';
import { gameNames, savedGame } from './games';
import type { GameId } from './types';

export function useGame() {
  const [game, setGame] = useState<GameId>(savedGame);
  function chooseGame(next: GameId) {
    sessionStorage.setItem('arena.game', next);
    setGame(next);
  }
  return {game, chooseGame};
}

export function GamePicker({game, chooseGame, label = '游戏', disabled}: ReturnType<typeof useGame> & {label?: string; disabled?: boolean}) {
  return <label className="game-picker">{label}
    <select aria-label={label} disabled={disabled} value={game} onChange={e => chooseGame(e.target.value as GameId)}>
      {Object.entries(gameNames).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
    </select>
  </label>;
}
