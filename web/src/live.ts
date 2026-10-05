import type { Replay } from './types';

export function completeSnapshot(value: Replay): boolean {
  return value.frames.every((frame, index) => frame.seq === index && frame.tick === (index ? index - 1 : null))
    && (value.last_seq === undefined || value.last_seq === value.frames.length - 1);
}

/** A gap/conflict/attempt change requires the durable full snapshot. */
export function appendConfirmed(current: Replay | undefined, incoming: Replay): Replay | undefined {
  if (!current) return completeSnapshot(incoming) ? incoming : undefined;
  if (current.attempt_id !== incoming.attempt_id || incoming.resync_required) return undefined;
  const frames = [...current.frames];
  for (const frame of incoming.frames) {
    if (!Number.isInteger(frame.seq) || frame.seq < 0 || frame.tick !== (frame.seq ? frame.seq - 1 : null)) return undefined;
    if (frame.seq < frames.length) {
      if (JSON.stringify(frame) !== JSON.stringify(frames[frame.seq])) return undefined;
    } else {
      if (frame.seq !== frames.length) return undefined;
      frames.push(frame);
    }
  }
  if (incoming.last_seq !== undefined && incoming.last_seq !== frames.length - 1) return undefined;
  return { ...current, ...incoming, frames };
}
