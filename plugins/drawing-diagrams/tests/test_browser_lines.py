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
6. The reported model and every example, in both modes: a line whose first (last) run is horizontal
   leaves (enters) its card sideways, and that end lies on the card's left or right edge, between
   its top and bottom as measured in the page. A straight line between a tall card and a short one,
   drawn from the tall card's row alone, would meet the short card below its bottom edge.

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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import support
import render
from diagrams import router

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

# Written after the page has drawn (draw() runs at load, on fonts ready and at 300 ms): `lines`, the
# `d` of the line of every edge group in the svg, in drawing order, which is the order of the edges
# the renderer handed to the page; `cards`, the box [left, top, right, bottom] of every card, taken
# from the page layout and mapped into the svg's own coordinates, the ones `d` is written in.
PROBE = ("<script>setTimeout(function(){var o={lines:[],cards:{}},s=document.querySelector('.dg-svg');"
         "document.querySelectorAll('.dg-svg > g').forEach(function(g){var p=g.querySelector('path');"
         "o.lines.push([g.getAttribute('data-e'),p?p.getAttribute('d'):null])});"
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
    """The probe output of `page` after it has drawn, as {"lines": [(data-e, d), ...], "cards":
    {id: [left, top, right, bottom]}}. No --user-data-dir:
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
    horizontal) anywhere but on that card's left or right edge between its top and bottom, and the
    number of sideways ends looked at."""
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
            if not (on_side and t - AXIS_TOL <= end[1] <= b + AXIS_TOL):
                out.append(f"{name} {how} {card} sideways at ({end[0]:.2f}, {end[1]:.2f}); "
                           f"the card spans x {l:.2f}..{r:.2f}, y {t:.2f}..{b:.2f}")
    return out, checked


def row_order_swaps(layout, names, lines):
    """(swaps, compared): pairs of horizontal runs of different edges on one lattice row line (odd
    Y) whose lattice spans overlap and whose router offsets differ, drawn in the opposite order of
    those offsets. Equal pixels (a merge by clamping into a card) are not a swap."""
    rows = []  # (Y, lattice lo, lattice hi, oy, edge index, pixel y)
    for i, e in enumerate(layout["edges"]):
        path = e["path"]
        if len(path) != len(lines[i]) + 1:
            continue  # the page merged points of this line; its runs cannot be matched to the lattice
        for k, (a, b) in enumerate(zip(path, path[1:])):
            if a[1] == b[1] and a[1] % 2 == 1 and lines[i][k][0] == "h":
                rows.append((a[1], min(a[0], b[0]), max(a[0], b[0]), a[3], i, lines[i][k][1]))
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
        models = [(REPORTED_NAME, REPORTED)] + cls.examples
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
        for name, _ in [(REPORTED_NAME, REPORTED)] + self.examples:
            for mode in MODES:
                with self.subTest(model=name, mode=mode):
                    checked = self.check_sides(name, mode)
                    if name == REPORTED_NAME:
                        # the case exists only if write -> both meets the pill `both` sideways
                        self.assertGreater(checked, 0, f"harness: {mode}: no line meets a card sideways")

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
