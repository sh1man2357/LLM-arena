def frames(records):
    header = records[0]
    width, height = header["map"]["width"], header["map"]["height"]
    states = [("initial", header["initial_state"], [], [], [])]
    states += [(f"tick {r['tick']}", r["state"], r["events"], r["actions"], r["calls"])
               for r in records if r["type"] == "tick"]
    for label, state, events, actions, calls in states:
        cells = [".#+"[v] for v in state["grid"]]
        for b in state["bombs"]:
            cells[b["y"] * width + b["x"]] = "*"
        for p in state["players"]:
            if p["alive"]:
                cells[p["y"] * width + p["x"]] = str(p["id"])
        text = "\n".join("".join(cells[y*width:(y+1)*width]) for y in range(height))
        yield (f"{label}\n{text}\nactions: {actions}\ncalls: {calls}\n"
               f"players: {state['players']}\nbombs: {state['bombs']}\nevents: {events}\n")
    yield f"result: {records[-1]}\n"
