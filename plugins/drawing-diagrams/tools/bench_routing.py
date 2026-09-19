#!/usr/bin/env python3
"""Timings of the routing engine. For the plugin's maintainer; SKILL.md does not mention it.

  bench_routing.py          print the numbers
  bench_routing.py --json   print the same numbers as one JSON object

Two measurements, each the best of five runs. `flow.plan` on every shipped flow-like example in
both modes. And routing plus `assign_offsets` plus `crossings` on the dense scenario of
instances.py for seeds 1-10: the median and the maximum of the time, and the median of the
crossings.

The numbers of a run are the baseline the next stage of the routing work compares with. The budgets
are those of docs/specs/2026-09-19-routing-quality-design.md: an example at or below 25 ms, the
dense median at or below 300 ms. A budget exceeded is printed on stderr and does not fail the run:
the budget holds over the stream, and the base it is measured from sits just under it.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
SKILL = PLUGIN / "skills" / "drawing-diagrams"
sys.path.insert(0, str(SKILL))

import instances  # noqa: E402
from diagrams import flow, router  # noqa: E402

MODES = ("widget", "page")
REPEATS = 5
SEEDS = range(1, 11)
EXAMPLE_BUDGET_MS = 25
DENSE_BUDGET_MS = 300


def examples():
    """The shipped examples `flow.plan` routes: the kinds of flow.MODES, in path order."""
    files = sorted(SKILL.glob("examples/*.json")) + sorted(SKILL.glob("examples/full/*.json"))
    out = []
    for path in files:
        model = json.loads(path.read_text())
        if model.get("kind") in flow.MODES:
            out.append((path, model))
    return out


def route_all(lat, ends, labelled):
    """The routing loop of flow.plan, so that the benchmark times routing without the checks
    around it: one pass in the given order with accumulating traffic, then two rip-up passes; an
    edge with no route stays None and takes no part in them. Task 1 of the routing plan moves this
    loop into router.route_all, and then this becomes one call of it."""
    paths, live = [], []
    traffic = router.Traffic()
    for i, (src, dst) in enumerate(ends):
        p = router.route(lat, src, dst, labelled=labelled[i], traffic=traffic)
        paths.append(p)
        if p is not None:
            traffic.add(p)
            live.append(i)
    for _ in range(2):
        for i in live:
            others = router.Traffic()
            for j in live:
                if j != i:
                    others.add(paths[j])
            p = router.route(lat, ends[i][0], ends[i][1], labelled=labelled[i], traffic=others)
            if p is not None:
                paths[i] = p
    return paths


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


def dense_numbers():
    """Per seed of the dense scenario: the time of routing, offsets and the count together, and
    the crossings counted. The routing is deterministic, so every run of a seed counts the same
    crossings and only the time is taken from the fastest."""
    out = []
    for seed in SEEDS:
        cols, rows, cells, edges = instances.dense_scenario(seed)
        lat = router.Lattice(cols, rows, cells)
        ends = [(router.Lattice.point(*cells[a]), router.Lattice.point(*cells[b])) for a, b in edges]
        labelled = [False] * len(ends)

        def run():
            paths = [p for p in route_all(lat, ends, labelled) if p is not None]
            router.assign_offsets(paths, nodes=frozenset(lat.blocked))
            return len(paths), router.crossings(paths)

        runs = [_timed(run) for _ in range(REPEATS)]
        routed, crossings = runs[0][1]
        out.append({"seed": seed, "ms": round(min(ms for ms, _ in runs), 2),
                    "routed": routed, "crossings": crossings})
    return out


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
    args = ap.parse_args(argv)
    data = report()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        show(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
