"""Browser acceptance for the uniform explicit grid, derived before implementation.

1. Empty first, several leading, internal and trailing columns still occupy equal
   CSS tracks. Real card edges and routed gutter centrelines agree with Python
   Geometry, in flow/swimlane, widget/page and at a non-default width.
2. Label anchors attached to those routed lines have the same x coordinate as
   Geometry and the rendered SVG; every edge and label must actually be drawn.
3. An occupied-column control and an empty-row combination retain their geometry.
4. Browser absence may skip; failed launches and browser errors fail the test.
"""
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import support
import render
import test_browser_lines as browser
from diagrams import flow, router


# name, column count, source column, target column, source row, target row,
# total rows, lattice x coordinates to measure. Odd x is a column centre;
# even x is a gutter or an outer margin. Leading/trailing empty rows accompany
# an empty column in the final case, so preserving rows is exercised too.
CASES = (
    ("first", 2, 1, 1, 0, 1, 2, (0, 1, 2)),
    ("leading", 3, 2, 2, 0, 1, 2, (0, 1, 2, 3, 4)),
    ("internal", 3, 0, 2, 0, 1, 2, (2, 3, 4)),
    ("trailing", 2, 0, 0, 0, 1, 2, (2, 3, 4)),
    ("occupied", 2, 0, 1, 0, 1, 2, (2,)),
    ("empty-rows", 2, 1, 1, 1, 3, 5, (0, 1, 2)),
)
TOL = 0.1  # CSS subpixel rounding, in SVG user units (CSS px)

ERROR_CAPTURE = """<script>
window.columnErrors=[];
window.addEventListener('error',function(e){columnErrors.push(e.message||'resource error')},true);
window.addEventListener('unhandledrejection',function(e){columnErrors.push(String(e.reason))});
var columnConsoleError=console.error;
console.error=function(){columnErrors.push(Array.from(arguments).join(' '));
  columnConsoleError.apply(console,arguments)};
</script>"""

# Observe only the rendered DOM. No renderer functions are exposed or replaced.
PROBE = """<script>setTimeout(function(){
var result={errors:window.columnErrors,diagrams:{}};
document.querySelectorAll('.dg').forEach(function(sec){
  var grid=sec.querySelector('.dg-grid'),svg=sec.querySelector('.dg-svg');
  var r=grid.getBoundingClientRect(),css=getComputedStyle(grid);
  var o={tracks:css.gridTemplateColumns.split(' ').map(parseFloat),
    gap:parseFloat(css.columnGap),padding:parseFloat(css.paddingLeft),cards:{},lines:[],texts:[]};
  sec.querySelectorAll('.dg-c[data-t]').forEach(function(card){
    var b=card.getBoundingClientRect();
    o.cards[card.getAttribute('data-t')]=[b.left-r.left,b.top-r.top,b.right-r.left,b.bottom-r.top];
  });
  svg.querySelectorAll(':scope > g').forEach(function(g){
    var p=g.querySelector('path'),t=g.querySelector('text');
    o.lines.push([g.getAttribute('data-e'),p?p.getAttribute('d'):null]);
    o.texts.push(t?[+t.getAttribute('x'),+t.getAttribute('y'),t.getAttribute('text-anchor')]:null);
  });
  result.diagrams[sec.getAttribute('data-dg')]=o;
});
var pre=document.createElement('pre');pre.id='probe';pre.textContent=JSON.stringify(result);
document.body.appendChild(pre);
},800)</script>"""


def fixture(kind, case, x):
    name, cols, ac, bc, ar, br, rows, _ = case
    cells = [["."] * cols for _ in range(rows)]
    cells[ar][ac], cells[br][bc] = "a", "b"
    groups = {f"g{c}": {"label": f"Lane {c}", "ramp": "teal"} for c in range(cols)}
    model = {"kind": kind, "id": f"{name}-{x}", "groups": groups,
             "nodes": [{"id": "a", "title": "A", "group": f"g{ac}"},
                       {"id": "b", "title": "B", "group": f"g{bc}"}],
             "grid": [" ".join(row) for row in cells], "edges": ["a -> b : x"]}
    if kind == "swimlane":
        model["lanes"] = list(groups)
    path = [(2 * ac + 1, 2 * ar + 1), (x, 2 * ar + 1),
            (x, 2 * br + 1), (2 * bc + 1, 2 * br + 1)]
    return model, path


def render_cases(kind, mode, width, page):
    args = render.parse_args([str(page), "--mode", mode, "--assets", "inline"])
    overrides = {} if width is None else {"total": width}
    layouts, fragments = {}, []
    for case in CASES:
        for x in case[-1]:
            model, path = fixture(kind, case, x)
            # Hand routes measure every empty track even where route_all would
            # choose a nearer gutter. The production planner still computes
            # offsets, labels and the serialized drawing instructions.
            with mock.patch.object(router, "route_all", return_value=[path]):
                out, _, layout = render.produce(model, flow, args, overrides, "inline")
            layouts[model["id"]] = layout
            fragments.append(out)
    page.write_text("<!doctype html><html><head><meta charset='utf-8'></head><body>"
                    + ERROR_CAPTURE + "\n".join(fragments) + PROBE + "</body></html>")
    return layouts


class EmptyColumnsBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        chrome, reason = browser.find_chrome()
        if chrome is None:
            raise unittest.SkipTest(reason)
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.layouts, cls.results, jobs = {}, {}, {}
        for kind in ("flow", "swimlane"):
            for mode in ("widget", "page"):
                for width in (None, 913):
                    key = kind, mode, width
                    page = Path(tmp.name) / f"{kind}-{mode}-{width}.html"
                    cls.layouts[key] = render_cases(kind, mode, width, page)
                    jobs[key] = page
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {key: pool.submit(browser.run_chrome, chrome, page) for key, page in jobs.items()}
            for key, future in futures.items():
                try:
                    cls.results[key] = future.result()
                except Exception as exc:  # a blocked browser is a failure, never a skip
                    cls.results[key] = exc

    def measured(self):
        for key, layouts in self.layouts.items():
            result = self.results[key]
            with self.subTest(configuration=key):
                self.assertNotIsInstance(result, Exception, f"browser unavailable: {result}")
                self.assertEqual(result["errors"], [], "browser errors during drawing")
                self.assertEqual(set(result["diagrams"]), set(layouts))
            if isinstance(result, Exception) or set(result["diagrams"]) != set(layouts):
                continue
            for name, layout in layouts.items():
                yield key, name, layout, result["diagrams"][name]

    def test_css_cards_and_routed_columns_agree_with_geometry(self):
        for key, name, layout, got in self.measured():
            with self.subTest(configuration=key, diagram=name):
                geo = flow.Geometry(layout["mode"], layout["card_w"], layout["grid_cols"])
                self.assertEqual(len(got["tracks"]), geo.cols)
                for track in got["tracks"]:
                    self.assertAlmostEqual(track, geo.w, delta=TOL)
                self.assertAlmostEqual(got["padding"], geo.pad_l, delta=TOL)
                self.assertAlmostEqual(got["gap"], geo.gap, delta=TOL)
                self.assertEqual(set(got["cards"]), {"a", "b"})
                for nid, box in got["cards"].items():
                    col = layout["cells"][nid][1]
                    self.assertAlmostEqual(box[0], geo.left(col), delta=TOL)
                    self.assertAlmostEqual(box[2], geo.right(col), delta=TOL)
                self.assertEqual([n for n, _ in got["lines"]], ["a b"])
                points = browser.polyline(got["lines"][0][1] or "")
                self.assertEqual(len(points), 4, "missing or collapsed routed segment")
                self.assertEqual(len(browser.runs(points)), 3)
                edge = layout["edges"][0]
                for index in (1, 2):
                    x, _, ox, _ = edge["path"][index]
                    self.assertAlmostEqual(points[index][0], geo.x(x) + ox, delta=TOL,
                                           msg=f"lattice x={x} disagrees with CSS/Python")
                # These side exits are centred on their real cards. This also
                # guards empty rows without duplicating the row-band algorithm.
                for index, nid in ((0, "a"), (3, "b")):
                    card = got["cards"][nid]
                    self.assertAlmostEqual(points[index][1], (card[1] + card[3]) / 2, delta=TOL)

    def test_label_anchors_agree_with_geometry_and_drawn_path(self):
        for key, name, layout, got in self.measured():
            with self.subTest(configuration=key, diagram=name):
                self.assertEqual([n for n, _ in got["lines"]], ["a b"])
                self.assertEqual(len(got["texts"]), 1)
                text = got["texts"][0]
                self.assertIsNotNone(text, "missing label")
                points = browser.polyline(got["lines"][0][1] or "")
                self.assertEqual(len(points), 4)
                edge = layout["edges"][0]
                pt, ref, row, dx, dy, anchor = edge["la"]
                self.assertIn(pt, (1, 2), "fixture must anchor on the measured empty track")
                geo = flow.Geometry(layout["mode"], layout["card_w"], layout["grid_cols"])
                x, _, ox, _ = edge["path"][pt]
                self.assertAlmostEqual(text[0], geo.x(x) + ox + dx, delta=TOL)
                self.assertAlmostEqual(text[0], points[pt][0] + dx, delta=TOL)
                bases = {edge["path"][i][1]: points[i][1] - edge["path"][i][3] for i in (1, 2)}
                ar, br = layout["cells"]["a"][0], layout["cells"]["b"][0]
                if br == ar + 1:
                    bases[2 * br] = (got["cards"]["a"][3] + got["cards"]["b"][1]) / 2
                expected = browser.anchor_point(edge["la"], points, bases)
                self.assertIsNotNone(expected, f"unmeasured label row {row}, reference {ref}")
                self.assertAlmostEqual(text[1], expected[1], delta=TOL)
                self.assertEqual(text[2], anchor)


if __name__ == "__main__":
    unittest.main()
