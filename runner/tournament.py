from dataclasses import asdict
from itertools import combinations
from pathlib import Path
import re
from engine.maps import generate
from engine.model import Rules, digest
from replay.verify import read, verify_scheduled
from runner.io import ROOT, read_json, sha_file, write_json, write_lines
from runner.match import components, qualify, run_match
from runtime.wasm import Backend, INIT_FUEL, TICK_FUEL


def load_entrants(path):
    rows = read_json(path)
    if not isinstance(rows, list) or len(rows) < 2:
        raise ValueError("At least two entrants are required")
    result = []
    for row in rows:
        if set(row) != {"id", "wasm"} or not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", row["id"]):
            raise ValueError("Entrants require safe unique IDs and WASM paths")
        wasm = Path(row["wasm"])
        if not wasm.is_absolute():
            wasm = ROOT / wasm
        result.append(dict(id=row["id"], wasm=str(wasm.resolve())))
    if len({e["id"] for e in result}) != len(result):
        raise ValueError("Duplicate entrant ID")
    return sorted(result, key=lambda e: e["id"])


def validate_cases(cases):
    if not isinstance(cases, list) or not cases:
        raise ValueError("Nonempty case list required")
    hashes, map_seeds = set(), set()
    for case in cases:
        if set(case) != {"map_seed", "bot_seeds"} or len(case["bot_seeds"]) != 2:
            raise ValueError("Each case requires one map seed and two Bot seeds")
        if any(not isinstance(s, str) or not re.fullmatch(r"[0-9a-f]{16}", s) for s in case["bot_seeds"]):
            raise ValueError("Bot seeds must be 16 lowercase hex characters")
        m = generate(case["map_seed"])
        if m["map_hash"] in hashes or case["map_seed"] in map_seeds:
            raise ValueError("Duplicate map or map seed")
        hashes.add(m["map_hash"]); map_seeds.add(case["map_seed"])
    return cases


def schedule(entrants, cases):
    result = []
    for a, b in combinations(entrants, 2):
        for index, case in enumerate(cases):
            for swapped in (False, True):
                ids = [a["id"], b["id"]]
                seeds = case["bot_seeds"].copy()
                if swapped:
                    ids.reverse(); seeds.reverse()
                pair_key = digest([a["id"], b["id"]])[:16]
                result.append(dict(match_id=f"p{pair_key}-c{index:04d}-s{int(swapped)}",
                                   pair=[a["id"], b["id"]], case_index=index, swapped=swapped,
                                   map_seed=case["map_seed"], entrants=ids, bot_seeds=seeds))
    if len({item["match_id"] for item in result}) != len(result):
        raise ValueError("Schedule match ID collision")
    return result


def run_tournament(entrants, cases, output, resume=False, retry_failures=False):
    cases = validate_cases(cases)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    plan = schedule(entrants, cases)
    manifest = dict(schema_version=1, components=components(), rules=asdict(Rules()),
                    budget=dict(init_fuel=INIT_FUEL, tick_fuel=TICK_FUEL),
                    entrants=[dict(id=e["id"], wasm_sha256=sha_file(e["wasm"])) for e in entrants],
                    cases_sha256=digest(cases), schedule_sha256=digest(plan), expected_matches=len(plan))
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        if not resume:
            raise ValueError("Run directory already exists; use --resume or a new directory")
        if read_json(manifest_path) != manifest or read_json(output / "schedule.json") != plan:
            raise ValueError("Frozen manifest or schedule differs; cannot resume")
    else:
        if resume:
            raise ValueError("Cannot resume without a frozen manifest")
        write_json(manifest_path, manifest)
        write_json(output / "schedule.json", plan)
        write_json(output / "cases.json", cases)
    by_id = {e["id"]: e for e in entrants}
    results = []
    with Backend() as backend:
        qualifications = []
        for e in entrants:
            qualifications.append(dict(id=e["id"], **qualify(backend, e["wasm"])))
        write_json(output / "qualification.json", qualifications)
        for index, item in enumerate(plan):
            rp = output / "replays" / f"{item['match_id']}.jsonl"
            result_path = output / "matches" / f"{item['match_id']}.json"
            cached = read_json(result_path) if result_path.exists() else None
            if cached is not None and cached.get("valid"):
                records = read(rp)
                verify_scheduled(records, item, manifest)
                if (records[0]["components"] != manifest["components"] or
                        dict(records[-1], replay_sha256=sha_file(rp)) != cached):
                    raise ValueError("Cached result/version differs from Replay")
                if (records[0]["map_seed"] != item["map_seed"] or records[0]["bot_seeds"] != item["bot_seeds"] or
                        [e["id"] for e in records[0]["entrants"]] != item["entrants"]):
                    raise ValueError("Cached Replay differs from scheduled case")
                if [e["wasm_sha256"] for e in records[0]["entrants"]] != [sha_file(by_id[e]["wasm"]) for e in item["entrants"]]:
                    raise ValueError("Cached Replay uses different entrant artifacts")
                result = cached
            elif cached is not None and not retry_failures:
                result = cached
            else:
                if cached is not None:
                    prior = output / "failed_attempts" / item["match_id"]
                    prior.mkdir(parents=True, exist_ok=True)
                    attempt = len(list(prior.glob("*.result.json")))
                    write_json(prior / f"{attempt}.result.json", cached)
                    if rp.exists():
                        (prior / f"{attempt}.replay.jsonl").write_bytes(rp.read_bytes())
                result, _ = run_match(backend, [by_id[i] for i in item["entrants"]], item["map_seed"],
                                      [int(s, 16) for s in item["bot_seeds"]], item["match_id"],
                                      replay_path=rp, version=manifest["components"])
                result["replay_sha256"] = sha_file(rp)
                write_json(result_path, result)
            results.append(result)
            if (index + 1) % 25 == 0 or index == 0:
                print(f"Matches {index+1}/{len(plan)}", flush=True)
        write_lines(output / "results.jsonl", results)
    return manifest, plan, results
