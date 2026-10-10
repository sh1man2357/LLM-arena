import { useEffect, useRef } from 'react';
import { slotColor } from './ui';
import type { Frame, Entrant } from './types';

type Props = { frame: Frame; previous?: Frame; entrants: Entrant[]; overlay?: boolean; selected?: [number, number];
  onSelect?: (position: [number, number]) => void; animate?: boolean; compact?: boolean };

export function Board({ frame, previous, entrants, overlay = true, selected, onSelect, animate = false, compact = false }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animation = useRef<{frame: Frame; started: number} | null>(null);
  const entrantIds = entrants.map(e => e.id).join('\n');
  const selectedX = selected?.[0], selectedY = selected?.[1];
  useEffect(() => {
    const canvas = canvasRef.current!;
    const context = canvas.getContext('2d')!;
    const style = getComputedStyle(canvas);
    const hard = style.getPropertyValue('--tile-hard').trim(), hardEdge = style.getPropertyValue('--tile-hard-edge').trim();
    const soft = style.getPropertyValue('--tile-soft').trim(), softEdge = style.getPropertyValue('--tile-soft-edge').trim();
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
      context.fillStyle = '#0E161C'; context.fillRect(0, 0, w, h);
      const progress = motion.matches || !animate ? 1 : Math.min(1, (performance.now() - started) / 160);
      for (let y = 0; y < 11; y++) for (let x = 0; x < 13; x++) {
        const type = frame.state.grid[y * 13 + x];
        const px = x * cell, py = y * cell, gap = cell * .075;
        if (type === 0) {
          context.fillStyle = (x + y) % 2 ? '#172129' : '#151F27'; context.fillRect(px + 1, py + 1, cell - 2, cell - 2);
          context.fillStyle = '#22313A'; context.fillRect(px + cell / 2 - 1, py + cell / 2 - 1, 2, 2);
        } else if (type === 1) {
          context.fillStyle = '#0A1116'; context.fillRect(px + gap, py + gap + cell * .055, cell - gap * 2, cell - gap * 2);
          context.fillStyle = hard; context.fillRect(px + gap, py + gap, cell - gap * 2, cell - gap * 2 - cell * .055);
          context.fillStyle = hardEdge; context.fillRect(px + gap, py + gap, cell - gap * 2, cell * .06);
          context.strokeStyle = '#28353D'; context.lineWidth = cell * .035;
          context.strokeRect(px + gap * 2, py + gap * 2, cell - gap * 4, cell - gap * 4);
        } else {
          context.fillStyle = soft; context.fillRect(px + gap, py + gap, cell - gap * 2, cell - gap * 2);
          context.fillStyle = softEdge; context.fillRect(px + gap, py + gap, cell - gap * 2, cell * .08);
          context.strokeStyle = '#344B43'; context.lineWidth = cell * .055;
          context.beginPath(); context.moveTo(px + gap, py + cell * .5); context.lineTo(px + cell - gap, py + cell * .5);
          context.moveTo(px + cell * .5, py + gap); context.lineTo(px + cell * .5, py + cell * .5);
          context.moveTo(px + cell * .33, py + cell * .5); context.lineTo(px + cell * .33, py + cell - gap); context.stroke();
        }
      }
      if (overlay) for (const c of frame.visual.coverage) {
        const px = c.x * cell, py = c.y * cell;
        context.fillStyle = '#EFB95B40'; context.fillRect(px + 2, py + 2, cell - 4, cell - 4);
        context.fillStyle = '#FFE2AA'; context.fillRect(px + cell * .18, py + cell * .39, cell * .64, cell * .22);
        context.fillRect(px + cell * .39, py + cell * .18, cell * .22, cell * .64);
      }
      for (const b of frame.state.bombs) {
        const px = (b.x + .5) * cell, py = (b.y + .5) * cell;
        const color = slotColor(b.owner_id);
        context.fillStyle = '#091015'; context.strokeStyle = color; context.lineWidth = cell * .055;
        context.beginPath(); context.arc(px, py, cell * .29, 0, Math.PI * 2); context.fill(); context.stroke();
        context.beginPath(); context.moveTo(px + cell * .13, py - cell * .25); context.lineTo(px + cell * .23, py - cell * .39); context.stroke();
        context.fillStyle = '#F3F1E9'; context.font = `600 ${cell * .23}px ui-monospace, monospace`; context.textAlign = 'center'; context.textBaseline = 'middle';
        context.fillText(String(Math.max(0, b.explode_at_tick - frame.state.tick)), px, py);
      }
      for (const p of frame.state.players) {
        const color = slotColor(p.id);
        let x = p.x, y = p.y;
        const move = frame.events.find(e => e.type === 'move' && e.player === p.id);
        if (move && previous && progress < 1) { x = move.origin[0] + (p.x - move.origin[0]) * progress; y = move.origin[1] + (p.y - move.origin[1]) * progress; }
        let px = (x + .5) * cell, py = (y + .5) * cell;
        const footBomb = frame.state.bombs.some(b => b.x === p.x && b.y === p.y);
        if (footBomb) { px -= cell * .14; py -= cell * .14; }
        context.globalAlpha = p.alive ? 1 : .45;
        context.fillStyle = p.alive ? color : '#79858B'; context.strokeStyle = '#10151C'; context.lineWidth = cell * .075;
        context.beginPath();
        if (p.id === 0) { context.arc(px, py, cell * .29, 0, Math.PI * 2); }
        else { context.moveTo(px, py - cell * .34); context.lineTo(px + cell * .32, py); context.lineTo(px, py + cell * .34); context.lineTo(px - cell * .32, py); context.closePath(); }
        context.fill(); context.stroke();
        context.fillStyle = '#10151C'; context.font = `800 ${cell * .24}px ui-monospace, monospace`; context.textAlign = 'center'; context.textBaseline = 'middle';
        context.fillText(p.alive ? String(p.id) : '×', px, py);
        context.globalAlpha = 1;
      }
      if (selectedX !== undefined && selectedY !== undefined) {
        context.strokeStyle = '#F3F1E9'; context.lineWidth = Math.max(2, cell * .045);
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
  return <canvas ref={canvasRef} role="img" className={`board ${compact ? 'compact' : ''}`} aria-label={`比赛棋盘，${frame.tick === null ? '初始状态' : `Tick ${frame.tick} 已结算`}。双方状态见棋盘上方。`}
    onClick={onSelect ? event => { const r = event.currentTarget.getBoundingClientRect(); onSelect([Math.min(12, Math.floor((event.clientX - r.left) / r.width * 13)), Math.min(10, Math.floor((event.clientY - r.top) / r.height * 11))]); } : undefined} />;
}
