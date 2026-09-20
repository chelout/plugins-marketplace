#!/usr/bin/env python3
"""Timings of the routing engine. For the plugin's maintainer; SKILL.md does not mention it.

  bench_routing.py          print the numbers
  bench_routing.py --json   print the same numbers as one JSON object
  bench_routing.py --advice time the rearrangement advice instead of the routing

Two measurements, each the best of five runs. `flow.plan` on every shipped flow-like example in
both modes. And routing plus `place` — the offsets and the capacity check together — plus
`crossings` on the dense scenario of instances.py for seeds 1-10: the median and the maximum of the
time, and the median of the crossings.

`--advice` measures `advice.search` instead, on three populations: the dense scenario, the twelve
seeded models `tests/test_advice.py` holds the search to, and the shipped flow-like examples. See
`advice_numbers` for what it reports and for the lever it measures beside the full verification.

The dense scenario is planned the way `flow.plan` plans a page flow: its lattice states the
capacity of every line, its routing and its offsets are given the room those capacities come from,
and its paths are placed in the order the search priced them in. Timed without the room the run
would leave out the one term of the objective that is not pairwise additive — a routing against a
room pays for `overflow` on every proposal — and report a budget nothing in production ever meets.

The numbers of a run are the baseline the next stage of the routing work compares with. The budgets
are those of docs/specs/2026-09-19-routing-quality-design.md: an example at or below 25 ms, the
dense median at or below 300 ms. A budget exceeded is printed on stderr and does not fail the run:
the budget holds over the stream, and the base it is measured from sits just under it.
"""
import argparse
import contextlib
import copy
import functools
import json
import statistics
import sys
import time
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
SKILL = PLUGIN / "skills" / "drawing-diagrams"
sys.path.insert(0, str(SKILL))

import instances  # noqa: E402
from diagrams import advice, flow, router  # noqa: E402
from diagrams.common import ModelError  # noqa: E402

MODES = ("widget", "page")
REPEATS = 5
SEEDS = range(1, 11)
EXAMPLE_BUDGET_MS = 25
DENSE_BUDGET_MS = 300

# The configuration the dense scenario is planned under, as (kind, mode, footnotes): a page flow,
# the shape most of the shipped examples have.
DENSE_CONFIG = ("flow", "page", ())

# The advice measurement, and the population `tests/test_advice.py` holds the search to. A seeded
# instance becomes a model; the twelve the search is measured and tested on are the first twelve of
# that stream whose plan crosses at least three times, which is what makes `render.main` ask for
# advice at all (spec 6).
ADVICE_MODE = "page"          # 6 columns and 30 nodes: every instance of `instances.small` fits
ADVICE_SEED = 20260920
ADVICE_MODELS = 12
ADVICE_SCAN = 40              # instances drawn to find them; raising it leaves the first ones where they are
ADVICE_CROSSINGS = 3          # the crossings warning of flow.plan, which is what triggers the advice
ADVICE_BUDGET_MS = 3000       # what spec 6 asked the search to be reported against
ADVICE_SEEDS = range(1, 6)    # seeds of the dense scenario the advice is measured on


def model_from(cols, rows, cells, edges):
    """A flow model on the grid of one seeded instance: every node a card titled by its id, every
    pair of `instances.py` an edge, and the map written cell by cell.

    The grid is the naive reading order an author writes before thinking about the lines: the ids of
    an instance run in reading order over its cells (`instances.py`), so the map carries them as
    they come. Every row is written out in full, the empty cells at its end included, so the grid is
    as wide as the instance whatever stands in the last column."""
    width = max(len(nid) for nid in cells)
    at = {rc: nid for nid, rc in cells.items()}
    grid = ["  ".join(at.get((r, c), ".").ljust(width) for c in range(cols)).rstrip()
            for r in range(rows)]
    return {"kind": "flow", "id": "seeded",
            "nodes": [{"id": nid, "title": nid.upper()} for nid in sorted(cells)],
            "grid": grid,
            "edges": [f"{a} -> {b}" for a, b in edges]}


@functools.lru_cache(maxsize=None)
def _seeded():
    out = []
    for k, instance in enumerate(instances.small(ADVICE_SEED, ADVICE_SCAN)):
        model = model_from(*instance)
        try:
            layout, _ = flow.plan(copy.deepcopy(model), ADVICE_MODE, None, draft=True)
        except ModelError:
            continue  # a model the renderer refuses outright is never advised about
        if layout["crossings"] >= ADVICE_CROSSINGS:
            out.append((k, model))
        if len(out) == ADVICE_MODELS:
            break
    return tuple(out)


def seeded_models():
    """The twelve seeded models, as (instance number, model). Fresh copies: a caller that plans one
    of them hands `flow.plan` a model it writes `_note` and `_text` into."""
    return [(k, copy.deepcopy(model)) for k, model in _seeded()]


def examples():
    """The shipped examples `flow.plan` routes: the kinds of flow.MODES, in path order."""
    files = sorted(SKILL.glob("examples/*.json")) + sorted(SKILL.glob("examples/full/*.json"))
    out = []
    for path in files:
        model = json.loads(path.read_text())
        if model.get("kind") in flow.MODES:
            out.append((path, model))
    return out


def best_of(fn, repeats=REPEATS):
    """Milliseconds of the fastest of `repeats` runs: the machine's noise only ever adds."""
    return min(_timed(fn) for _ in range(repeats))[0]


def _timed(fn):
    start = time.perf_counter()
    value = fn()
    return (time.perf_counter() - start) * 1000, value


def example_numbers():
    out = []
    for path, model in examples():
        for mode in MODES:
            ms = best_of(lambda: flow.plan(model, mode))
            out.append({"file": path.name, "kind": model["kind"], "mode": mode, "ms": round(ms, 2)})
    return out


def planned(cols, cells):
    """The geometry and the lattice `flow.plan` builds for an instance under DENSE_CONFIG: the
    extent ends at the last occupied row, the rows of it without a card carry their band, and every
    lattice line states the capacity of the room the geometry gives it."""
    kind, mode_name, footnotes = DENSE_CONFIG
    used = {r for r, _ in cells.values()}
    extent = max(used) + 1
    mode = flow.mode_for(kind, mode_name, None)
    card_w = (mode["total"] - mode["pad_l"] - mode["pad_r"] - mode["gap"] * (cols - 1)) / cols
    geo = flow.Geometry(mode, card_w, cols, extent, *flow.margin_room(kind, mode_name, footnotes),
                        empty=[r for r in range(extent) if r not in used])

    def line_capacity(axis, line):
        room = geo.room(axis, line)
        return None if room is None else router.capacity(room)

    return geo, router.Lattice(cols, extent, cells, capacity=line_capacity)


def dense_numbers():
    """Per seed of the dense scenario: the time of routing, offsets and the count together, and
    the crossings counted. The routing is deterministic, so every run of a seed counts the same
    crossings and only the time is taken from the fastest."""
    out = []
    for seed in SEEDS:
        cols, _, cells, edges = instances.dense_scenario(seed)
        geo, lat = planned(cols, cells)
        ends = [(router.Lattice.point(*cells[a]), router.Lattice.point(*cells[b])) for a, b in edges]
        labelled = [False] * len(ends)
        nodes = frozenset(lat.blocked)

        def run():
            found = [(end, lab, p) for end, lab, p
                     in zip(ends, labelled, router.route_all(lat, ends, labelled, room=geo.room))
                     if p is not None]
            paths = [p for _, _, p in found]
            router.place([end for end, _, _ in found], [lab for _, lab, _ in found],
                         paths, nodes, geo.room)
            return len(paths), router.crossings(paths)

        runs = [_timed(run) for _ in range(REPEATS)]
        routed, crossings = runs[0][1]
        out.append({"seed": seed, "ms": round(min(ms for ms, _ in runs), 2),
                    "routed": routed, "crossings": crossings})
    return out


# ------------------------------------------------------------------ the advice


@contextlib.contextmanager
def _counted():
    """`flow.plan` with a counter in front of it: the advice reaches the planner through the module,
    so what this counts is every plan the search makes and nothing else."""
    calls = [0]
    real = flow.plan

    def spy(*a, **kw):
        calls[0] += 1
        return real(*a, **kw)

    flow.plan = spy
    try:
        yield calls
    finally:
        flow.plan = real


@contextlib.contextmanager
def _route_budget(budget):
    """The calls of `route` a plan's routing may spend, for the length of the block. `budget=0`
    stops `route_all` at the better of its two starts — the first lever of spec 6 as amended, which
    this tool prices and does not adopt."""
    was = flow._ROUTE_BUDGET
    flow._ROUTE_BUDGET = budget
    try:
        yield
    finally:
        flow._ROUTE_BUDGET = was


def _one_search(model, mode_name, budget=None):
    """One `advice.search` of a model: what it advised, how long it took, and how many plans it
    made. `budget` is `_route_budget`'s; with one, the score the search itself answers is the cheap
    routing's, so the caller prices the advised grid again in full."""
    with _counted() as calls:
        with _route_budget(flow._ROUTE_BUDGET if budget is None else budget):
            ms, found = _timed(lambda: advice.search(model, mode_name))
    return found, ms, calls[0]


def _run(model, mode_name):
    """Both readings of one model: the search as it is built, with every verifying plan routed in
    full, and the lever — verifying plans that stop at the better start, with the advised grid
    planned in full once at the end.

    Reported per reading: the whole time and the time per plan, the plans spent, and the score
    before and after. `before` is the full plan's score of the author's own grid in both readings,
    and the lever's `after` is that one full plan of the grid it advised, so the two answers are
    read off one scale — a lever that advises a worse picture says so in that number. `moves` are
    the texts, which is what says whether the two advised the same thing."""
    out = {}
    found, ms, plans = _one_search(model, mode_name)
    before, _ = advice.evaluate(model, mode_name)
    out["full"] = _reading(found, ms, plans, before, found[-1][2] if found else before)
    found, ms, plans = _one_search(model, mode_name, budget=0)
    advised = model
    for move, _, _ in found:
        advised = move.apply(advised)
    lever_ms, (after, _) = _timed(lambda: advice.evaluate(advised, mode_name))
    out["start"] = _reading(found, ms + lever_ms, plans + 1, before, after)
    out["same_moves"] = out["full"]["moves"] == out["start"]["moves"]
    out["same_after"] = out["full"]["after"] == out["start"]["after"]
    return out


def _reading(found, ms, plans, before, after):
    return {"ms": round(ms, 1), "plans": plans, "ms_per_plan": round(ms / max(plans, 1), 1),
            "moves": [move.text() for move, _, _ in found],
            "before": list(before), "after": list(after)}


def advice_numbers():
    """`advice.search` on the three populations of task 15: the dense scenario of the performance
    budget, the twelve seeded models the tests hold the search to, and the shipped flow-like
    examples in both modes."""
    out = []
    for seed in ADVICE_SEEDS:
        model = model_from(*instances.dense_scenario(seed))
        out.append({"population": "dense", "name": f"сид {seed}", "mode": ADVICE_MODE,
                    **_run(model, ADVICE_MODE)})
    for k, model in seeded_models():
        out.append({"population": "seeded", "name": f"#{k}", "mode": ADVICE_MODE,
                    **_run(model, ADVICE_MODE)})
    for path, model in examples():
        for mode in MODES:
            out.append({"population": "examples", "name": path.name, "mode": mode,
                        **_run(copy.deepcopy(model), mode)})
    return out


def advice_report():
    rows = advice_numbers()
    data = {"advice": rows, "advice_budget_ms": ADVICE_BUDGET_MS,
            "advice_mode": ADVICE_MODE, "advice_seeds": list(ADVICE_SEEDS),
            "dense_scenario": list(instances.DENSE_SCENARIO)}
    for population in ("dense", "seeded", "examples"):
        here = [r for r in rows if r["population"] == population]
        for reading in ("full", "start"):
            times = [r[reading]["ms"] for r in here]
            data[f"{population}_{reading}_median_ms"] = round(statistics.median(times), 1)
            data[f"{population}_{reading}_max_ms"] = max(times)
            data[f"{population}_{reading}_median_ms_per_plan"] = round(
                statistics.median(r[reading]["ms_per_plan"] for r in here), 1)
        data[f"{population}_same_moves"] = sum(1 for r in here if r["same_moves"])
        data[f"{population}_same_after"] = sum(1 for r in here if r["same_after"])
        data[f"{population}_count"] = len(here)
    data["over_budget"] = [name for name in ("dense", "seeded", "examples")
                           if data[f"{name}_full_median_ms"] > ADVICE_BUDGET_MS]
    return data


def show_advice(data):
    print(f"advice.search, полная проверка и рычаг «до лучшего старта» "
          f"(режим {data['advice_mode']}, бюджет {data['advice_budget_ms']} мс)")
    cols, rows, n_nodes, n_edges = data["dense_scenario"]
    print(f"  dense: плотный сценарий {cols}x{rows}, узлов {n_nodes}, связей {n_edges}, "
          f"сиды {min(data['advice_seeds'])}-{max(data['advice_seeds'])}; "
          f"seeded: {data['seeded_count']} засеянных моделей тестов; examples: поставляемые примеры")
    head = f"  {'модель':26} {'реж':7} {'ходов':>5} {'планов':>6} {'мс':>8} {'мс/план':>8}"
    for population in ("dense", "seeded", "examples"):
        here = [r for r in data["advice"] if r["population"] == population]
        print(f"\n{population}: {len(here)}   слева полная проверка, справа рычаг")
        print(head + "   " + f"{'ходов':>5} {'планов':>6} {'мс':>8} {'мс/план':>8}  счёт")
        for r in here:
            f, s = r["full"], r["start"]
            print(f"  {r['name']:26} {r['mode']:7} {len(f['moves']):5} {f['plans']:6} {f['ms']:8.1f} "
                  f"{f['ms_per_plan']:8.1f}   {len(s['moves']):5} {s['plans']:6} {s['ms']:8.1f} "
                  f"{s['ms_per_plan']:8.1f}  {tuple(f['before'])} -> {tuple(f['after'])} / {tuple(s['after'])}")
        print(f"  медиана: полная {data[f'{population}_full_median_ms']:.1f} мс "
              f"({data[f'{population}_full_median_ms_per_plan']:.1f} мс/план), "
              f"рычаг {data[f'{population}_start_median_ms']:.1f} мс "
              f"({data[f'{population}_start_median_ms_per_plan']:.1f} мс/план)")
        print(f"  максимум: полная {data[f'{population}_full_max_ms']:.1f} мс, "
              f"рычаг {data[f'{population}_start_max_ms']:.1f} мс")
        print(f"  рычаг советует то же: ходы {data[f'{population}_same_moves']}/{data[f'{population}_count']}, "
              f"счёт {data[f'{population}_same_after']}/{data[f'{population}_count']}")
    for name in data["over_budget"]:
        print(f"бюджет превышен: {name}", file=sys.stderr)


def report():
    ex = example_numbers()
    dense = dense_numbers()
    times = [d["ms"] for d in dense]
    data = {
        "examples": ex,
        "example_max_ms": max(d["ms"] for d in ex),
        "example_budget_ms": EXAMPLE_BUDGET_MS,
        "dense_scenario": list(instances.DENSE_SCENARIO),
        "dense": dense,
        "dense_median_ms": round(statistics.median(times), 2),
        "dense_max_ms": max(times),
        "dense_median_crossings": statistics.median(d["crossings"] for d in dense),
        "dense_budget_ms": DENSE_BUDGET_MS,
    }
    data["over_budget"] = [
        name for name, value, budget in (("examples", data["example_max_ms"], EXAMPLE_BUDGET_MS),
                                         ("dense", data["dense_median_ms"], DENSE_BUDGET_MS))
        if value > budget]
    return data


def show(data):
    print(f"flow.plan на примерах (лучшее из {REPEATS}), мс")
    for d in data["examples"]:
        print(f"  {d['file']:26} {d['kind']:9} {d['mode']:7} {d['ms']:8.2f}")
    print(f"  максимум {data['example_max_ms']:.2f} при бюджете {data['example_budget_ms']}")
    cols, rows, n_nodes, n_edges = data["dense_scenario"]
    print(f"\nплотный сценарий ({cols}x{rows}, узлов {n_nodes}, связей {n_edges}), "
          f"сиды {min(SEEDS)}-{max(SEEDS)}, лучшее из {REPEATS}")
    for d in data["dense"]:
        print(f"  сид {d['seed']:2} {d['ms']:9.2f} мс, пересечений {d['crossings']:3}, "
              f"маршрутов {d['routed']}")
    print(f"  маршрутизация + смещения + подсчёт, мс: медиана {data['dense_median_ms']:.2f}, "
          f"максимум {data['dense_max_ms']:.2f} при бюджете медианы {data['dense_budget_ms']}")
    print(f"  пересечений: медиана {data['dense_median_crossings']}")
    for name in data["over_budget"]:
        print(f"бюджет превышен: {name}", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="печатать числа одним объектом JSON")
    ap.add_argument("--advice", action="store_true", help="мерить советчика, а не маршрутизацию")
    args = ap.parse_args(argv)
    data = advice_report() if args.advice else report()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.advice:
        show_advice(data)
    else:
        show(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
