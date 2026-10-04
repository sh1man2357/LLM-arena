import struct


def encode(world, self_id):
    if self_id not in range(len(world.players)) or len(world.bombs) > 8:
        raise ValueError("Invalid observation")
    r = world.rules
    parts = [struct.pack("<12I", 1, world.tick, world.width, world.height, self_id,
                         len(world.players), len(world.bombs), len(world.grid),
                         r.max_ticks, r.bomb_fuse_ticks, r.bomb_capacity, r.blast_range), bytes(world.grid)]
    parts.extend(struct.pack("<4I", p.id, p.x, p.y, int(p.alive))
                 for p in sorted(world.players, key=lambda p: p.id))
    parts.extend(struct.pack("<6I", b.id, b.owner_id, b.x, b.y, b.explode_at_tick, b.range)
                 for b in sorted(world.bombs, key=lambda b: b.id))
    return b"".join(parts)
