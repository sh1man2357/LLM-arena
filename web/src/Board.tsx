import { useEffect, useRef } from 'react';
import type { Frame, Entrant, World } from './types';
import { playerTokens } from './ui';

type Props = { frame: Frame; previous?: Frame; entrants: Entrant[]; overlay?: boolean; selected?: [number, number];
  onSelect?: (position: [number, number]) => void; animate?: boolean; compact?: boolean };

export function Board({ frame, previous, entrants, overlay = true, selected, onSelect, animate = false, compact = false }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animation = useRef<{frame: Frame; started: number} | null>(null);
  const entrantIds = entrants.map(e => e.id).join('\n');
  const selectedX = selected?.[0], selectedY = selected?.[1];
  useEffect(() => {
    const state = frame.state as World;
    const canvas = canvasRef.current!;
    const context = canvas.getContext('2d')!;
    const style = getComputedStyle(canvas);
    const color = (token: string) => style.getPropertyValue(token).trim();
    const background = color('--board-bg'), grid = color('--board-grid'), hard = color('--tile-hard');
    const soft = style.getPropertyValue('--tile-soft').trim(), softEdge = style.getPropertyValue('--tile-soft-edge').trim();
    const playerColors = playerTokens.map(token => color(`--player-${token}`));
    const ink = color('--bg'), text = color('--text'), muted = color('--muted'), accent = color('--accent'), blast = color('--blast-fill');
    const motion = matchMedia('(prefers-reduced-motion: reduce)');
    let raf = 0;
    // Metadata/name updates and selection changes must not rewind a confirmed move.
    if (animation.current?.frame !== frame || !animate) {
      animation.current = { frame, started: performance.now() - (animate ? 0 : 160) };
    }
    const started = animation.current.started;
    function draw() {
      const cssWidth = canvas.clientWidth;
      const dpr = Math.min(devicePixelRatio || 1, 2);
      if (canvas.width !== Math.round(cssWidth * dpr)) {
        canvas.width = Math.round(cssWidth * dpr); canvas.height = Math.round(cssWidth * 11 / 13 * dpr);
      }
      const w = canvas.width, h = canvas.height, cell = w / 13;
      context.clearRect(0, 0, w, h);
      context.fillStyle = background; context.fillRect(0, 0, w, h);
      const progress = motion.matches || !animate ? 1 : Math.min(1, (performance.now() - started) / 160);
      for (let y = 0; y < 11; y++) for (let x = 0; x < 13; x++) {
        const type = state.grid[y * 13 + x];
        const px = x * cell, py = y * cell, gap = cell * .065;
        context.setLineDash([]);
        if (type === 0) {
          context.strokeStyle = grid; context.lineWidth = dpr;
          context.strokeRect(px + dpr / 2, py + dpr / 2, cell - dpr, cell - dpr);
        } else if (type === 1) {
          context.fillStyle = hard; context.fillRect(px + gap, py + gap, cell - gap * 2, cell - gap * 2);
        } else {
          context.fillStyle = soft; context.fillRect(px + gap, py + gap, cell - gap * 2, cell - gap * 2);
          context.strokeStyle = softEdge; context.lineWidth = Math.max(dpr, cell * .025);
          context.setLineDash([cell * .11, cell * .07]);
          context.strokeRect(px + gap, py + gap, cell - gap * 2, cell - gap * 2);
        }
      }
      context.setLineDash([]);
      if (overlay) for (const c of frame.visual.coverage) {
        const px = c.x * cell, py = c.y * cell;
        context.fillStyle = blast; context.fillRect(px + dpr, py + dpr, cell - dpr * 2, cell - dpr * 2);
        context.strokeStyle = accent; context.lineWidth = cell * .04;
        context.beginPath(); context.moveTo(px + cell * .25, py + cell * .5); context.lineTo(px + cell * .75, py + cell * .5);
        context.moveTo(px + cell * .5, py + cell * .25); context.lineTo(px + cell * .5, py + cell * .75); context.stroke();
      }
      for (const b of state.bombs) {
        const shared = state.players.some(p => p.x === b.x && p.y === b.y);
        const offset = shared ? .17 : 0;
        const px = (b.x + .5 + offset) * cell, py = (b.y + .5 + offset) * cell;
        const ownerColor = playerColors[b.owner_id];
        context.fillStyle = ink; context.strokeStyle = ownerColor; context.lineWidth = cell * .035;
        context.beginPath(); context.arc(px, py, cell * (shared ? .23 : .29), 0, Math.PI * 2); context.fill(); context.stroke();
        context.beginPath(); context.moveTo(px + cell * .13, py - cell * .25); context.lineTo(px + cell * .23, py - cell * .39); context.stroke();
        context.fillStyle = text; context.font = `500 ${cell * .23}px ui-monospace, monospace`; context.textAlign = 'center'; context.textBaseline = 'middle';
        context.fillText(String(Math.max(0, b.explode_at_tick - state.tick)), px, py);
      }
      for (const p of state.players) {
        const playerColor = playerColors[p.id];
        let x = p.x, y = p.y;
        const move = frame.events.find(e => e.type === 'move' && e.player === p.id);
        if (move && previous && progress < 1) { x = move.origin[0] + (p.x - move.origin[0]) * progress; y = move.origin[1] + (p.y - move.origin[1]) * progress; }
        let px = (x + .5) * cell, py = (y + .5) * cell;
        const footBomb = state.bombs.some(b => b.x === p.x && b.y === p.y);
        if (footBomb) { px -= cell * .17; py -= cell * .17; }
        context.globalAlpha = p.alive ? 1 : .45;
        context.fillStyle = p.alive ? playerColor : muted; context.strokeStyle = background; context.lineWidth = cell * .04;
        context.beginPath();
        if (p.id % 2 === 0) { context.arc(px, py, cell * (footBomb ? .23 : .29), 0, Math.PI * 2); }
        else {
          const radius = cell * (footBomb ? .25 : .34);
          context.moveTo(px, py - radius); context.lineTo(px + radius, py); context.lineTo(px, py + radius); context.lineTo(px - radius, py); context.closePath();
        }
        context.fill(); context.stroke();
        context.fillStyle = ink; context.font = `600 ${cell * .24}px ui-monospace, monospace`; context.textAlign = 'center'; context.textBaseline = 'middle';
        context.fillText(p.alive ? String(p.id) : '×', px, py);
        context.globalAlpha = 1;
      }
      if (selectedX !== undefined && selectedY !== undefined) {
        context.strokeStyle = text; context.lineWidth = Math.max(2, cell * .045);
        context.strokeRect(selectedX * cell + 2, selectedY * cell + 2, cell - 4, cell - 4);
      }
      if (animate && !motion.matches && progress < 1) raf = requestAnimationFrame(draw);
    }
    draw();
    const redraw = () => { cancelAnimationFrame(raf); draw(); };
    const observer = new ResizeObserver(redraw); observer.observe(canvas);
    motion.addEventListener('change', redraw);
    return () => { cancelAnimationFrame(raf); observer.disconnect(); motion.removeEventListener('change', redraw); };
  }, [frame, previous, entrantIds, overlay, selectedX, selectedY, animate]);
  return <canvas ref={canvasRef} role="img" className={`board ${compact ? 'compact' : ''}`} aria-label={`棋盘，${frame.tick === null ? '初始状态' : `回合 ${frame.tick}`}。各 Bot 状态见棋盘上方。`}
    onClick={onSelect ? event => { const r = event.currentTarget.getBoundingClientRect(); onSelect([Math.min(12, Math.floor((event.clientX - r.left) / r.width * 13)), Math.min(10, Math.floor((event.clientY - r.top) / r.height * 11))]); } : undefined} />;
}
