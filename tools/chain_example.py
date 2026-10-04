"""Build and verify a legal, fully scripted chain-explosion demonstration."""
import argparse
from collections import deque
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.maps import generate
from runner.compiler import compile_bot
from runner.io import write_json
from runner.match import qualify, run_match
from runtime.wasm import Backend
from replay.verify import verify_world, verify_bot
from replay.view import frames


def main():
    p = argparse.ArgumentParser(); p.add_argument("--output", required=True); args = p.parse_args()
    folder = Path(args.output); folder.mkdir(parents=True, exist_ok=True)
    m = generate(102); queue = deque([((11, 9), [])]); seen = {(11, 9), (1, 1)}
    route = None
    while queue:
        pos, candidate = queue.popleft()
        if pos in ((2, 1), (1, 2)): route = candidate; break
        for action, (dx, dy) in enumerate(((0, 0), (0, -1), (1, 0), (0, 1), (-1, 0))):
            nxt = pos[0]+dx, pos[1]+dy
            if (action and nxt not in seen and 0 <= nxt[0] < 13 and 0 <= nxt[1] < 11
                    and m["grid"][nxt[1]*13+nxt[0]] == 0):
                seen.add(nxt); queue.append((nxt, candidate+[action]))
    if route is None: raise ValueError("Frozen example map has no demonstration path")
    source_a = ('#include "arena.hpp"\nnamespace bot {void init(uint64_t){} '
                f'Action tick(const GameState& s){{return s.tick=={len(route)-3}?Action::BOMB:Action::WAIT;}}}}\n')
    source_b = ('#include "arena.hpp"\nstatic unsigned route[]={' + ','.join(map(str, route)) + '};\n'
                'namespace bot {void init(uint64_t){} '
                f'Action tick(const GameState& s){{if(s.tick<{len(route)})return Action(route[s.tick]);'
                f'return s.tick=={len(route)}?Action::BOMB:Action::WAIT;}}}}\n')
    for name, source in (("a", source_a), ("b", source_b)):
        (folder/f"{name}.cpp").write_text(source, encoding="utf-8", newline="\n")
        compile_bot(folder/f"{name}.cpp", folder/f"{name}.wasm")
    entrants = [dict(id=f"chain-{name}", wasm=str(folder/f"{name}.wasm")) for name in ("a", "b")]
    with Backend() as backend:
        for e in entrants: qualify(backend, e["wasm"])
        result, records = run_match(backend, entrants, 102, [1, 2], match_id="chain-example", replay_path=folder/"replay.jsonl")
        verify_world(records); verify_bot(backend, records, [e["wasm"] for e in entrants])
    last = records[-2]
    if (result["reason"] != "all_eliminated" or result["ticks"] != len(route)+2 or
            [e["bomb"] for e in last["events"] if e["type"] == "explode"] != [0, 1]):
        raise ValueError("Expected chain explosion did not occur")
    text = "\n".join(frames(records))
    (folder/"replay.txt").write_text(text, encoding="utf-8", newline="\n")
    proof = dict(status="verified", map_seed=102, route=route, a_places_at=len(route)-3,
                 b_places_at=len(route), chain_tick=len(route)+1, b_original_deadline=len(route)+4,
                 ticks=result["ticks"], reason=result["reason"], placement_scores=[.5, .5])
    write_json(folder/"proof.json", proof)
    print(proof)


if __name__ == "__main__": main()
