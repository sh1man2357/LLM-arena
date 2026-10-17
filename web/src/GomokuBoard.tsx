import { useEffect, useRef } from 'react';
import type { Frame, GomokuWorld } from './types';

export function GomokuBoard({frame, numbers, interactive = false, onMove}: {
  frame: Frame; numbers: boolean; interactive?: boolean; onMove?: (action: number) => void;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const state = frame.state as GomokuWorld;
  useEffect(() => {
    const canvas = ref.current!, context = canvas.getContext('2d')!;
    function draw() {
      const dpr = Math.min(devicePixelRatio || 1, 2), width = Math.round(canvas.clientWidth * dpr);
      canvas.width = width; canvas.height = width;
      const cell = width / 16, radius = cell * .4;
      context.fillStyle = '#bfb1a0'; context.fillRect(0, 0, width, width);
      context.strokeStyle = '#6b6054'; context.lineWidth = dpr;
      for (let i = 1; i <= 15; i++) {
        context.beginPath(); context.moveTo(cell, i * cell); context.lineTo(15 * cell, i * cell); context.stroke();
        context.beginPath(); context.moveTo(i * cell, cell); context.lineTo(i * cell, 15 * cell); context.stroke();
      }
      context.fillStyle = '#554b42'; context.font = `${cell * .3}px system-ui`; context.textAlign = 'center'; context.textBaseline = 'middle';
      for (let i = 0; i < 15; i++) {
        context.fillText(String.fromCharCode(65 + i), (i + 1) * cell, cell * .4);
        context.fillText(String(i + 1), cell * .4, (i + 1) * cell);
      }
      for (const [x,y] of [[3,3],[11,3],[7,7],[3,11],[11,11]]) {
        context.beginPath(); context.arc((x+1)*cell,(y+1)*cell,cell*.07,0,Math.PI*2); context.fill();
      }
      state.moves.forEach((move, index) => {
        const x = (move.x + 1) * cell, y = (move.y + 1) * cell;
        context.fillStyle = move.color === 1 ? '#202226' : '#faf7f0'; context.strokeStyle = '#58534d'; context.lineWidth = dpr;
        context.beginPath(); context.arc(x, y, radius, 0, Math.PI * 2); context.fill(); context.stroke();
        if (numbers) {
          context.fillStyle = move.color === 1 ? '#faf7f0' : '#202226'; context.font = `600 ${cell * .34}px system-ui`;
          context.fillText(String(index + 1), x, y);
        }
        if (index === state.moves.length - 1) {
          context.strokeStyle = '#c74020'; context.lineWidth = Math.max(dpr * 2, cell * .055);
          context.beginPath(); context.arc(x, y, radius * .78, 0, Math.PI * 2); context.stroke();
        }
      });
      if (state.winning_line.length) {
        const first = state.winning_line[0], last = state.winning_line.at(-1)!;
        context.strokeStyle = '#cf4724'; context.lineWidth = cell * .12; context.lineCap = 'round';
        context.beginPath(); context.moveTo((first[0]+1)*cell,(first[1]+1)*cell); context.lineTo((last[0]+1)*cell,(last[1]+1)*cell); context.stroke();
      }
    }
    draw(); const observer = new ResizeObserver(draw); observer.observe(canvas);
    return () => observer.disconnect();
  }, [state, numbers]);
  const last = state.moves.at(-1);
  return <div className="gomoku-surface"><canvas ref={ref} className="board gomoku-board" role="img" aria-label={`五子棋棋盘，已落 ${state.moves.length} 子${last ? `，上一手 ${String.fromCharCode(65+last.x)}${last.y+1}` : ''}。黑白双方状态见棋盘上方。`} />
    {onMove && <div className="gomoku-input" role="group" aria-label="选择落子位置">{state.grid.map((stone, action) => <button
      key={action} type="button" aria-label={`${String.fromCharCode(65+action%15)}${Math.floor(action/15)+1}${stone ? '，已有棋子' : '，落子'}`}
      disabled={!interactive || !!stone} onClick={() => onMove(action)} />)}</div>}
  </div>;
}
