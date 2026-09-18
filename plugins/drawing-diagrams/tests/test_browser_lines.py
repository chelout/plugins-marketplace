"""Browser acceptance test: lines drawn in pixels cross exactly where the router planned.

Test cases (written from the declaration of the change, before the implementation was read):

1. The reported model (a flow: grid `walk wake / write both`, a terminal pill beside a taller step
   card) in page mode and in widget mode: the number of places where a vertical line of one edge
   passes through a horizontal line of another, measured in the browser, equals router.crossings
   on the lattice.
2. The same model: lines that share a lattice row line (odd Y) keep, in pixels, the order of the
   router's offsets there (wake -> write above write -> both), in both modes.
3. Every example whose kind is flow, swimlane, state or blocks, in page mode and in widget mode:
   pixel crossings equal lattice crossings, and row-line order follows the offsets.
4. Harness honesty: every routed edge is drawn and measured; a page that yields no probe output, or
   a line that is not made of horizontal and vertical runs, is a harness failure, never a pass.
5. No browser binary: the test skips, and the skip message says why. DG_CHROME set to a path that
   is not an executable is an error, not a skip.
6. Every model, in both modes: a line whose first (last) run is horizontal leaves (enters) its
   card sideways, and that end lies on the card's left or right edge, CLAMP_IN or more inside its
   top and bottom as measured in the page. A straight line between a tall card and a short one,
   drawn from the tall card's row alone, would meet the short card below its bottom edge.
7. The models in CASES, in both modes, as in 1 and 2: pixel crossings equal lattice crossings
   (except GUTTER_CROSSINGS), and row-line order follows the offsets. The first four hold five or
   more lines along one row line beside a card shorter than the row, where lines saturate the band
   and must merge: straight lines both ways between one pair of cards, and a line clamped at the
   band's upper or lower limit beside an interior run of another line. A clamp that is not the same
   along the whole row line (a two-point line's source card, the card at a line's own end, none on
   an interior run) puts a line past the pill (6) or two lines out of order there.
8. Every model, in both modes: a horizontal run on a row line of cards stays within that row line's
   band (CLAMP_IN inside the cards lines enter or leave sideways there), and two runs there with
   different offsets are drawn exactly their offset difference apart unless one sits at the band's
   limit. "one-pair-both-ways" holds two straight lines between one pair of cards (offsets -4, 4).
9. "pinned-label-row", both modes: the label beside a vertical second segment is pinned (`ly`) to a
   row of cards holding a step card, a shorter pill and a straight line between them; its baseline
   stands LABEL_DROP below that row line's base as drawn, not below the row's middle.
10. "planned-crossing", both modes: two straight lines cross in an empty cell, one crossing on the
    lattice, and the page draws exactly that one.

Each page is rendered through the renderer's own entry points with inline assets, so the script in
the page is built from template/js (not template/dist), and opened once in headless Chrome.
"""
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import support
import render
from diagrams import router
from diagrams.flow import LABEL_DROP

KINDS = ("flow", "swimlane", "state", "blocks")
MODES = ("page", "widget")
EXAMPLES = support.SKILL / "examples"
MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PATH_NAMES = ("google-chrome", "chromium", "chromium-browser")
# pixels: a vertical must pass this far inside a horizontal, and the horizontal this far inside the
# vertical, to count as a crossing, so lines meeting at a card edge or sharing an end do not count
TOL = 1.0
# pixels: a run is horizontal (vertical) when its ends differ by at most this much in y (x)
AXIS_TOL = 0.5
# pixels: template/js/flow.js clamps the y of a line on a row line this far inside a card's top and
# bottom edges (clampY, and the row line's own clamp)
CLAMP_IN = 10
BROWSER_TIMEOUT = 60  # seconds per page; a launch takes about 3 s

# The reported case: `write -> both` leaves the step card `write` straight sideways into the
# shorter terminal pill `both`, while `wake -> write` comes down the gutter and enters `write` from
# the right on the same lattice row line. The router puts `wake -> write` above (oy -4) and
# `write -> both` below (oy +4); a browser that draws the straight line from another base than the
# rest of the row line swaps them and draws a crossing the lattice does not have.
REPORTED = {
    "kind": "flow",
    "groups": {"ok": {"label": "есть", "ramp": "teal"}, "gap": {"label": "нет", "ramp": "coral"}},
    "nodes": [
        {"id": "prev", "group": "ok", "title": "Вход"},
        {"id": "walk", "group": "ok", "title": "Обход графа", "text": "без изменений"},
        {"id": "wake", "group": "ok", "title": "Пробуждение", "text": "якорь времени по виду чека уже есть"},
        {"id": "write", "group": "gap", "title": "Запись результата", "text": "схема готова, SQL живого пути нет"},
        {"id": "both", "kind": "terminal", "group": "ok", "title": "история: оба вида есть"},
        {"id": "next", "group": "ok", "title": "Дальше"},
    ],
    "grid": ["prev   .", "walk   wake", "write  both", "next   ."],
    "edges": ["prev -> walk", "walk -> write", "walk -> wake | dashed", "wake -> write",
              "write -> both | dashed", "write -> next"],
}
REPORTED_NAME = "reported-row-line"

STEP = {"title": "Запись результата", "text": "схема готова, SQL живого пути нет"}  # taller than a pill


def step(i, text=False):
    return {"id": i, **STEP} if text else {"id": i, "title": i.upper()}


def pill(i):
    return {"id": i, "kind": "terminal", "title": "итог " + i}


# Models drawn next to the reported one (docstring cases 7 to 10).
CASES = {
    # six straight lines between a and the pill b, offsets -20..20: the outer ones saturate
    "two-point-side-miss": {"kind": "flow", "nodes": [step("a", True), pill("b")], "grid": ["a b"],
                            "edges": ["a -> b"] * 3 + ["b -> a"] * 3 + ["a -> b"]},
    # five straight lines, -16..16, the ones at 8 and 16 leaving from different cards
    "two-point-order": {"kind": "flow", "nodes": [step("a", True), pill("b")], "grid": ["a b"],
                        "edges": ["a -> b"] * 3 + ["b -> a", "a -> b", "b -> a"]},
    # row line of e: e -> a (16) at the band's upper limit (its largest y), the interior run of a -> d (8)
    "upper-limit-interior-run": {
        "kind": "flow", "nodes": [pill("d"), pill("b"), pill("e"), pill("c"), step("a", True)],
        "grid": ["d b", "e .", "c a"],
        "edges": ["b -> d", "a -> d", "b -> a", "c -> b", "c -> a", "c -> b", "b -> e", "e -> b", "e -> b",
                  "a -> d", "e -> a"]},
    # row line of f: f -> a (-16) at the band's lower limit (its smallest y), the interior run of a -> c (-8)
    "lower-limit-interior-run": {
        "kind": "flow", "nodes": [pill(i) for i in "beafcd"], "grid": ["b e a", "f . .", ". c d"],
        "edges": ["d -> b", "b -> d", "d -> e", "a -> f", "d -> f", "a -> e", "d -> f", "f -> a", "f -> d",
                  "e -> c", "c -> f", "d -> e", "a -> b", "a -> c"]},
    "one-pair-both-ways": {"kind": "flow", "grid": ["s .", "t p"], "edges": ["s -> t", "t -> p", "p -> t"],
                           "nodes": [step("s"), {"id": "t", "title": STEP["title"],
                                                 "text": STEP["text"] + ", и ещё строка текста"}, pill("p")]},
    "pinned-label-row": {"kind": "flow", "grid": ["s . a", "t p .", ". b ."],
                         "nodes": [step("s"), step("t", True), pill("p"), step("a"), step("b")],
                         "edges": ["s -> t", "t -> p", "a -> b : да"]},
    "planned-crossing": {"kind": "flow", "nodes": [step(i) for i in "abcd"], "grid": [". a .", "b . c", ". d ."],
                         "edges": ["a -> d", "b -> c"]},
}
# The gutters of these two also hold crossings that the router's offsets make where a line turns
# off a shared lattice line and that router.crossings does not count; that is not a row line's
# drawing, so their crossings are not compared.
GUTTER_CROSSINGS = ("upper-limit-interior-run", "lower-limit-interior-run")

# Written after the page has drawn (draw() runs at load, on fonts ready and at 300 ms): `lines`, the
# `d` of the line of every edge group in the svg, in drawing order, which is the order of the edges
# the renderer handed to the page; `texts`, in the same order, the [x, y] of the group's label text
# or null; `cards`, the box [left, top, right, bottom] of every card, taken from the page layout and
# mapped into the svg's own coordinates, the ones `d` is written in.
PROBE = ("<script>setTimeout(function(){var o={lines:[],texts:[],cards:{}},s=document.querySelector('.dg-svg');"
         "document.querySelectorAll('.dg-svg > g').forEach(function(g){var p=g.querySelector('path'),"
         "t=g.querySelector('text');o.lines.push([g.getAttribute('data-e'),p?p.getAttribute('d'):null]);"
         "o.texts.push(t?[+t.getAttribute('x'),+t.getAttribute('y')]:null)});"
         "if(s){var m=s.getScreenCTM().inverse(),q=s.createSVGPoint();"
         "var u=function(x,y){q.x=x;q.y=y;var w=q.matrixTransform(m);return[w.x,w.y]};"
         "document.querySelectorAll('.dg-grid [data-t]').forEach(function(c){var t=c.getAttribute('data-t'),r;"
         "if(o.cards[t])return;r=c.getBoundingClientRect();o.cards[t]=u(r.left,r.top).concat(u(r.right,r.bottom))})}"
         "var pre=document.createElement('pre');pre.id='probe';pre.textContent=JSON.stringify(o);"
         "document.body.appendChild(pre)},800)</script>")
PROBE_RE = re.compile(r'<pre id="probe">(.*?)</pre>', re.S)


class HarnessError(Exception):
    """The page could not be measured; says nothing about the lines."""


def find_chrome():
    """(path, None) of the browser to use, or (None, reason) when there is none."""
    env = os.environ.get("DG_CHROME")
    if env:
        if not (os.path.isfile(env) and os.access(env, os.X_OK)):
            raise RuntimeError(f"DG_CHROME={env!r} is not an executable file")
        return env, None
    if os.path.isfile(MAC_CHROME) and os.access(MAC_CHROME, os.X_OK):
        return MAC_CHROME, None
    for name in PATH_NAMES:
        found = shutil.which(name)
        if found:
            return found, None
    return None, (f"no browser binary: DG_CHROME is not set, {MAC_CHROME} does not exist, "
                  f"and none of {', '.join(PATH_NAMES)} is on PATH")


def flow_like_examples():
    """(name, model) of every example whose kind is drawn with lines by the flow renderer."""
    out = []
    for path in sorted(EXAMPLES.rglob("*.json")):
        model = json.loads(path.read_text())
        if model.get("kind") in KINDS:
            out.append((path.stem, model))
    return out


def render_page(model, mode, path):
    """Write the page of `model` in `mode` to `path` through the renderer's own entry points, with
    the probe appended; returns the layout the page was drawn from."""
    argv = [str(path), "--mode", mode, "--assets", "inline"] + (["--harness"] if mode == "widget" else [])
    args = render.parse_args(argv)
    assets_mode, note = render.resolve_assets(args)
    if assets_mode != "inline":
        raise HarnessError(f"assets mode {assets_mode!r} instead of inline: {note}")
    model = json.loads(json.dumps(model))  # the planner may annotate the model it is given
    mod = render.KINDS[model["kind"]]
    out, _, layout = render.produce(model, mod, args, {}, assets_mode)
    out = out.replace("</body>", PROBE + "</body>", 1) if "</body>" in out else out + PROBE
    path.write_text(out)
    return layout


def run_chrome(chrome, page):
    """The probe output of `page` after it has drawn, as {"lines": [(data-e, d), ...], "texts":
    [[x, y] or None, ...], "cards": {id: [left, top, right, bottom]}}. No --user-data-dir:
    on macOS a fresh profile directory keeps headless Chrome from exiting after --dump-dom."""
    cmd = [chrome, "--headless=new", "--disable-gpu", "--window-size=1300,1200",
           "--virtual-time-budget=3000", "--dump-dom", page.as_uri()]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=BROWSER_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise HarnessError(f"{page.name}: browser did not finish in {BROWSER_TIMEOUT} s")
    m = PROBE_RE.search(proc.stdout)
    if not m:
        raise HarnessError(f"{page.name}: no probe output (exit {proc.returncode}); "
                           f"stderr tail: {proc.stderr[-400:]!r}")
    return json.loads(html.unescape(m.group(1)))


def polyline(d):
    """Corner points of a line drawn by template/js/head.js roundPath: it writes `M p0`, then per
    corner `L p1 Q corner p2`, then `L last`, so the corners are M, every Q control point, and the
    last L."""
    tokens = re.findall(r"[MLQZ]|-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?", d)
    pts, last_l, i = [], None, 0
    while i < len(tokens):
        cmd = tokens[i]
        if cmd == "M":
            pts.append((float(tokens[i + 1]), float(tokens[i + 2])))
            i += 3
        elif cmd == "L":
            last_l = (float(tokens[i + 1]), float(tokens[i + 2]))
            i += 3
        elif cmd == "Q":
            pts.append((float(tokens[i + 1]), float(tokens[i + 2])))
            last_l = None
            i += 5
        else:
            raise HarnessError(f"unexpected token {cmd!r} in path {d!r}")
    if last_l is not None:
        pts.append(last_l)
    return pts


def runs(pts):
    """('h', y, x1, x2) or ('v', x, y1, y2) per segment of a polyline; raises HarnessError on a
    segment that is neither."""
    out = []
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if abs(y2 - y1) <= AXIS_TOL:
            out.append(("h", (y1 + y2) / 2, min(x1, x2), max(x1, x2)))
        elif abs(x2 - x1) <= AXIS_TOL:
            out.append(("v", (x1 + x2) / 2, min(y1, y2), max(y1, y2)))
        else:
            raise HarnessError(f"segment ({x1}, {y1}) -> ({x2}, {y2}) is neither horizontal nor vertical")
    return out


def pixel_crossings(names, lines):
    """[(vertical edge, horizontal edge, x, y)] for every place where a vertical run of one edge
    passes strictly through a horizontal run of another."""
    found = []
    for i, vi in enumerate(lines):
        for j, hj in enumerate(lines):
            if i == j:
                continue
            for axis, x, y1, y2 in vi:
                if axis != "v":
                    continue
                for axis2, y, x1, x2 in hj:
                    if axis2 == "h" and x1 + TOL < x < x2 - TOL and y1 + TOL < y < y2 - TOL:
                        found.append((names[i], names[j], x, y))
    return found


def side_misses(layout, names, polys, cards):
    """(misses, checked): ends of lines that meet their card sideways (the first or last run
    horizontal) anywhere but on that card's left or right edge, between CLAMP_IN below its top and
    CLAMP_IN above its bottom, where template/js/flow.js keeps them, and the number of sideways ends
    looked at."""
    out, checked = [], 0
    for e, name, pts in zip(layout["edges"], names, polys):
        for how, card, end, nxt in (("leaves", e["a"], pts[0], pts[1]), ("enters", e["b"], pts[-1], pts[-2])):
            if abs(end[1] - nxt[1]) > AXIS_TOL:
                continue  # a vertical run: the line meets the card at its top or bottom edge
            if card not in cards:
                raise HarnessError(f"card {card!r} of {name} has no box in the page")
            checked += 1
            l, t, r, b = cards[card]
            on_side = min(abs(end[0] - l), abs(end[0] - r)) <= AXIS_TOL
            if not (on_side and t + CLAMP_IN - AXIS_TOL <= end[1] <= b - CLAMP_IN + AXIS_TOL):
                out.append(f"{name} {how} {card} sideways at ({end[0]:.2f}, {end[1]:.2f}); "
                           f"the card spans x {l:.2f}..{r:.2f}, y {t:.2f}..{b:.2f}")
    return out, checked


def row_runs(layout, lines):
    """[(Y, lattice lo, lattice hi, oy, edge index, pixel y)] of every horizontal run drawn on a
    lattice row line (odd Y), matched to its lattice segment."""
    rows = []
    for i, e in enumerate(layout["edges"]):
        path = e["path"]
        if len(path) != len(lines[i]) + 1:
            continue  # the page merged points of this line; its runs cannot be matched to the lattice
        for k, (a, b) in enumerate(zip(path, path[1:])):
            if a[1] == b[1] and a[1] % 2 == 1 and lines[i][k][0] == "h":
                rows.append((a[1], min(a[0], b[0]), max(a[0], b[0]), a[3], i, lines[i][k][1]))
    return rows


def row_bands(layout, cards):
    """{Y: (lo, hi)}: per lattice row line (odd Y), the band template/js/flow.js clamps every point
    on it into, from the cards that lines enter or leave sideways there, as measured in the page:
    CLAMP_IN below the lowest top and above the highest bottom. A row line whose cards overlap by
    less than 2 * CLAMP_IN has no band."""
    ov = {}
    for e in layout["edges"]:
        for side, card, Y in ((e["sa"], e["a"], e["path"][0][1]), (e["sb"], e["b"], e["path"][-1][1])):
            if side not in ("L", "R"):
                continue
            if card not in cards:
                raise HarnessError(f"card {card!r} has no box in the page")
            t, b = cards[card][1], cards[card][3]
            o = ov.get(Y)
            ov[Y] = (max(o[0], t), min(o[1], b)) if o else (t, b)
    return {Y: (t + CLAMP_IN, b - CLAMP_IN) for Y, (t, b) in ov.items() if Y % 2 == 1 and b - t >= 2 * CLAMP_IN}


def at_limit(y, band):
    return band is not None and min(abs(y - band[0]), abs(y - band[1])) <= AXIS_TOL


def row_spacing_misses(layout, names, lines, cards):
    """(misses, compared): horizontal runs on a lattice row line (odd Y) drawn outside its band, and
    pairs of runs of different edges there with different router offsets not drawn exactly their
    offset difference apart, with neither at the band's limit (where clamping may merge them)."""
    bands, rows = row_bands(layout, cards), row_runs(layout, lines)
    misses, compared = [], 0
    for Y, _, _, oy, i, y in rows:
        band = bands.get(Y)
        if band and not band[0] - AXIS_TOL <= y <= band[1] + AXIS_TOL:
            misses.append(f"row line Y={Y}: {names[i]} (oy {oy}) drawn at y {y:.2f}, outside the row line's "
                          f"band {band[0]:.2f}..{band[1]:.2f}")
    for n, (Y, _, _, oy, i, y) in enumerate(rows):
        for Y2, _, _, oy2, j, y2 in rows[n + 1:]:
            if Y2 != Y or j == i or oy2 == oy or at_limit(y, bands.get(Y)) or at_limit(y2, bands.get(Y)):
                continue
            compared += 1
            if abs((y2 - y) - (oy2 - oy)) > AXIS_TOL:
                misses.append(f"row line Y={Y}: {names[i]} (oy {oy}) at y {y:.2f} and {names[j]} (oy {oy2}) at "
                              f"y {y2:.2f} are {y2 - y:.2f} apart, their offsets {oy2 - oy}")
    return misses, compared


def pinned_label_misses(layout, names, lines, texts, cards):
    """(misses, checked): labels pinned to a lattice row of cards (`ly` odd) whose baseline does not
    stand LABEL_DROP below that row line's base as drawn: the y, less its offset, of a horizontal
    run on that row line away from the band's limits."""
    bands, rows = row_bands(layout, cards), row_runs(layout, lines)
    misses, checked = [], 0
    for i, e in enumerate(layout["edges"]):
        Y = e.get("ly")
        if Y is None or Y % 2 == 0 or not e["label"]:
            continue
        if texts[i] is None:
            raise HarnessError(f"{names[i]} has a label pinned to row line {Y} and no text in the page")
        free = [(y - oy, names[j]) for Y2, _, _, oy, j, y in rows if Y2 == Y and not at_limit(y, bands.get(Y))]
        if not free:
            continue
        checked += 1
        base, by = free[0]
        if abs(texts[i][1] - LABEL_DROP - base) > AXIS_TOL:
            misses.append(f"{names[i]}: label pinned to row line {Y} has its baseline at y {texts[i][1]:.2f}; "
                          f"the row line's base, from {by}, is {base:.2f}")
    return misses, checked


def row_order_swaps(layout, names, lines):
    """(swaps, compared): pairs of horizontal runs of different edges on one lattice row line (odd
    Y) whose lattice spans overlap and whose router offsets differ, drawn in the opposite order of
    those offsets. Equal pixels (a merge by clamping into a card) are not a swap."""
    rows = row_runs(layout, lines)
    swaps, compared = [], 0
    for n, (Y, lo, hi, oy, i, y) in enumerate(rows):
        for Y2, lo2, hi2, oy2, j, y2 in rows[n + 1:]:
            if Y2 != Y or j == i or oy2 == oy or max(lo, lo2) >= min(hi, hi2):
                continue
            compared += 1
            (above, ya), (below, yb) = sorted([((oy, i), y), ((oy2, j), y2)])
            if ya > yb + AXIS_TOL:
                swaps.append(f"row line Y={Y}: {names[above[1]]} (oy {above[0]}) drawn at y {ya:.2f}, "
                             f"below {names[below[1]]} (oy {below[0]}) at y {yb:.2f}")
    return swaps, compared


class BrowserLines(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        chrome, reason = find_chrome()
        if chrome is None:
            raise unittest.SkipTest(reason)
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        root = Path(tmp.name)
        cls.examples = flow_like_examples()
        cls.models = [(REPORTED_NAME, REPORTED)] + list(CASES.items()) + cls.examples
        models = cls.models
        jobs, cls.layouts, cls.results = [], {}, {}
        for name, model in models:
            for mode in MODES:
                page = root / f"{name}-{mode}.html"
                try:
                    cls.layouts[name, mode] = render_page(model, mode, page)
                except Exception as exc:  # noqa: BLE001 - reported per case, as a harness error
                    cls.results[name, mode] = HarnessError(f"render failed: {exc!r}")
                    continue
                jobs.append(((name, mode), page))
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {key: pool.submit(run_chrome, chrome, page) for key, page in jobs}
            for key, fut in futures.items():
                try:
                    cls.results[key] = fut.result()
                except Exception as exc:  # noqa: BLE001 - reported per case, as a harness error
                    cls.results[key] = exc if isinstance(exc, HarnessError) else HarnessError(repr(exc))

    def measured(self, name, mode):
        """(layout, edge names, runs per edge) of one page; fails as a harness error, never passes,
        when the page could not be measured."""
        got = self.results[name, mode]
        if isinstance(got, Exception):
            self.fail(f"harness: {name} {mode}: {got}")
        layout = self.layouts[name, mode]
        want = [f"{e['a']} {e['b']}" for e in layout["edges"]]
        drawn = [n for n, _ in got["lines"]]
        self.assertEqual(drawn, want, f"harness: {name} {mode}: edges drawn differ from edges routed")
        try:
            lines = [runs(polyline(d or "")) for _, d in got["lines"]]
        except HarnessError as exc:
            self.fail(f"harness: {name} {mode}: {exc}")
        for n, line in zip(drawn, lines):
            self.assertTrue(line, f"harness: {name} {mode}: edge {n} has no drawn segment")
        return layout, [n.replace(" ", " -> ") for n in drawn], lines

    def check_crossings(self, name, mode):
        layout, names, lines = self.measured(name, mode)
        lattice = router.crossings(layout["paths"])
        found = pixel_crossings(names, lines)
        self.assertEqual(len(found), lattice,
                         f"{name} {mode}: {len(found)} crossing(s) in pixels, {lattice} on the lattice: "
                         + "; ".join(f"{v} vertical x={x:.2f} through {h} horizontal y={y:.2f}"
                                     for v, h, x, y in found))

    def check_row_order(self, name, mode):
        layout, names, lines = self.measured(name, mode)
        swaps, compared = row_order_swaps(layout, names, lines)
        self.assertEqual(swaps, [], f"{name} {mode}: lines on a row line drawn out of the router's order")
        return compared

    def check_spacing(self, name, mode):
        layout, names, lines = self.measured(name, mode)
        try:
            misses, compared = row_spacing_misses(layout, names, lines, self.results[name, mode]["cards"])
        except HarnessError as exc:
            self.fail(f"harness: {name} {mode}: {exc}")
        self.assertEqual(misses, [], f"{name} {mode}: lines on a row line not drawn from one base and one band")
        return compared

    def check_sides(self, name, mode):
        layout, names, _ = self.measured(name, mode)
        got = self.results[name, mode]
        try:
            misses, checked = side_misses(layout, names, [polyline(d) for _, d in got["lines"]], got["cards"])
        except HarnessError as exc:
            self.fail(f"harness: {name} {mode}: {exc}")
        self.assertEqual(misses, [], f"{name} {mode}: a line meets a card sideways off that card's side")
        return checked

    def test_reported_model_crossings_page(self):
        self.check_crossings(REPORTED_NAME, "page")

    def test_reported_model_crossings_widget(self):
        self.check_crossings(REPORTED_NAME, "widget")

    def test_reported_model_row_order(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                compared = self.check_row_order(REPORTED_NAME, mode)
                # the case exists only if wake -> write and write -> both share the row line
                self.assertGreater(compared, 0, f"harness: {mode}: no two lines share a row line to compare")

    def test_sideways_ends_meet_the_card(self):
        for name, _ in self.models:
            for mode in MODES:
                with self.subTest(model=name, mode=mode):
                    checked = self.check_sides(name, mode)
                    if name == REPORTED_NAME:
                        # the case exists only if write -> both meets the pill `both` sideways
                        self.assertGreater(checked, 0, f"harness: {mode}: no line meets a card sideways")

    def test_row_line_cases(self):
        for name in CASES:
            for mode in MODES:
                with self.subTest(model=name, mode=mode):
                    if name not in GUTTER_CROSSINGS:
                        self.check_crossings(name, mode)
                    self.check_row_order(name, mode)
                    if name in GUTTER_CROSSINGS or name.startswith("two-point"):
                        # the case exists only if five or more lines are drawn along one row line
                        layout, _, lines = self.measured(name, mode)
                        most = max(Counter(r[0] for r in row_runs(layout, lines)).values())
                        self.assertGreaterEqual(most, 5, f"harness: {name} {mode}: too few lines share a row line")

    def test_row_line_spacing(self):
        for name, _ in self.models:
            for mode in MODES:
                with self.subTest(model=name, mode=mode):
                    compared = self.check_spacing(name, mode)
                    if name == "one-pair-both-ways":
                        # the case exists only if t -> p and p -> t are compared, away from the band's limits
                        self.assertEqual(compared, 1, f"harness: {mode}: the two straight lines not compared")

    def test_pinned_label_row(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                layout, names, lines = self.measured("pinned-label-row", mode)
                got = self.results["pinned-label-row", mode]
                try:
                    misses, checked = pinned_label_misses(layout, names, lines, got["texts"], got["cards"])
                except HarnessError as exc:
                    self.fail(f"harness: pinned-label-row {mode}: {exc}")
                self.assertEqual(misses, [], f"pinned-label-row {mode}: a label pinned to a row off its base")
                # the case exists only if a -> b pins its label to the row line of t and p
                self.assertEqual(checked, 1, f"harness: {mode}: no label pinned to a row of cards was checked")

    def test_planned_crossing(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                layout, _, _ = self.measured("planned-crossing", mode)
                self.assertEqual(router.crossings(layout["paths"]), 1, f"harness: {mode}: the crossing is not planned")
                self.check_crossings("planned-crossing", mode)

    def test_examples_found(self):
        self.assertTrue(self.examples, f"no example of kind {', '.join(KINDS)} under {EXAMPLES}")

    def test_examples_crossings(self):
        for name, _ in self.examples:
            for mode in MODES:
                with self.subTest(example=name, mode=mode):
                    self.check_crossings(name, mode)

    def test_examples_row_order(self):
        for name, _ in self.examples:
            for mode in MODES:
                with self.subTest(example=name, mode=mode):
                    self.check_row_order(name, mode)


class FindChrome(unittest.TestCase):
    """The browser lookup behind the skip: a skip happens only when there is no browser, and says so."""

    def test_no_browser_gives_the_reason(self):
        with mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch(f"{__name__}.MAC_CHROME", "/nonexistent/Google Chrome"), \
                mock.patch("shutil.which", return_value=None):
            os.environ.pop("DG_CHROME", None)
            chrome, reason = find_chrome()
        self.assertIsNone(chrome)
        self.assertIn("no browser binary", reason)
        self.assertIn("DG_CHROME", reason)

    def test_dg_chrome_comes_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "chrome"
            fake.write_text("#!/bin/sh\n")
            fake.chmod(0o755)
            with mock.patch.dict(os.environ, {"DG_CHROME": str(fake)}):
                self.assertEqual(find_chrome(), (str(fake), None))

    def test_dg_chrome_not_executable_is_an_error(self):
        with mock.patch.dict(os.environ, {"DG_CHROME": "/nonexistent/chrome"}):
            with self.assertRaisesRegex(RuntimeError, "DG_CHROME"):
                find_chrome()


if __name__ == "__main__":
    unittest.main()
