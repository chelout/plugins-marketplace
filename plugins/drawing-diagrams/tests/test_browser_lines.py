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
7. The models in CASES, in both modes, as in 1 and 2: pixel crossings equal lattice crossings, and
   row-line order follows the offsets. The first four hold five or more lines along one row line
   beside a card shorter than the row, where lines saturate the band and must merge: straight lines
   both ways between one pair of cards, and a line clamped at the band's upper or lower limit beside
   an interior run of another line. A clamp that is not the same along the whole row line (a
   two-point line's source card, the card at a line's own end, none on an interior run) puts a line
   past the pill (6) or two lines out of order there.
8. Every model, in both modes: a horizontal run on a row line of cards stays within that row line's
   band (CLAMP_IN inside the cards lines enter or leave sideways there), and two runs there with
   different offsets are drawn exactly their offset difference apart unless one sits at the band's
   limit. "one-pair-both-ways" holds two straight lines between one pair of cards (offsets -4, 4).
9. "pinned-label-row", both modes: the label beside a vertical second segment is pinned (`ly`) to a
   row of cards holding a step card, a shorter pill and a straight line between them; its baseline
   stands LABEL_DROP below that row line's base as drawn, not below the row's middle.
10. "planned-crossing", both modes: two straight lines cross in an empty cell, one crossing on the
    lattice, and the page draws exactly that one.
11. "label-over-row-line", both modes: the label over a horizontal second segment that runs along a
    row line of a pill and a taller step card has its baseline LABEL_OVER above that row line's base
    as drawn, not above the row's middle.
12. "gutter-swap", both modes: a -> d and c -> b go corner to opposite corner up one gutter and swap
    sides along it, one crossing on the lattice, and the page draws exactly that one;
    "gutter-no-swap": a -> d and d -> a share a gutter in one order from end to end, no crossing
    on the lattice, and the page draws none.
13. "shared-corner", both modes: d -> a and a -> d share a stretch from a through a corner both turn
    at, and part below it; no crossing on the lattice, and the page draws none.
14. The room of the top and bottom margins, in flow and in swimlane, both modes, with footnotes and
    without: a line drawn along each of them keeps the px that diagrams/flow.py's TOP_ROOM and
    BOTTOM_ROOM claim, from the nearest card edge and from the nearest thing that clips or covers
    it — above the grid box or the section, below the first content the section goes on with, the
    footnote list or the legend's own text. The measurement that set those constants is this test,
    so a change of `.dg-foot`'s margin or of `.dg-legend`'s padding fails it instead of silently
    letting a line run through the text under the diagram. The top room is the same with footnotes
    and without, which is why only BOTTOM_ROOM is keyed by them.
15. "capacity-at-pitch", page: a model holding a group at the capacity of a column gutter (5 lines,
    pitch 6), of a row gutter (8, pitch 5), of a side margin (3, pitch 5) and of the bottom margin
    (1): every line keeps at least CARD_CLEAR from every card it does not end on and stays inside
    the grid box, and the line filling the bottom margin — which lies outside that box by design —
    keeps EDGE_CLEAR from the first content the section goes on with. This is what makes the
    capacity a number a diagram can be refused on: a group drawn as wide as its line allows is
    still a group the page draws clear of everything.
16. An empty row at the foot of the grid, in a flow and in a swimlane, both modes: the page draws a
    line for every edge, they cross as the lattice says and keep the router's order. `tracks()`
    invents a track for an empty row above or between the cards and none for one after the last, so
    a line planned under the last card row is a line `by()` has no y for: the script stops there and
    the page keeps only the lines it had already drawn. The flow's grid has a leading empty row as
    well, which does get a track, and one of its three lines runs along it.
17. The band of an empty row, in flow and in swimlane, both modes, with one leading empty row, with
    one between occupied rows, and with two of each in a row: where the page draws every lattice row
    line of the band — the top margin, the row line of each empty row, the gutters around them — from
    the card edges that bound the band and from one another. The rule the numbers show is the one
    diagrams/flow.py's `Geometry._band` derives the room from: `tracks()` invents one track per empty
    row and fills them in ascending order, so each sees the ones above it, the first row of the grid
    landing `flow.TRACK_LEAD` px over the first cards and every row after it halving what is left of
    the span below it. An empty implicit grid row is 0 px high and both of its row gaps stay, so that
    span is (k + 1) row gaps for k empty rows between two rows of cards. A change of `tracks()` fails
    this instead of letting a line be drawn into a card.
18. "empty-band-at-pitch", page: a flow with a leading empty row and one between its two rows of
    cards, holding a group at the capacity of every line of both bands. Every line keeps at least
    CARD_CLEAR from every card it does not end on and stays inside the grid box, as case 15 asks of
    the gutters and the margins. This is what makes the room of such a band a number a diagram can be
    refused on.

Each page is rendered through the renderer's own entry points with inline assets, so the script in
the page is built from template/js (not template/dist), and opened once in headless Chrome.
"""
import html
import json
import math
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
from diagrams import flow, router
from diagrams.flow import LABEL_DROP, TRACK_LEAD

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
# pixels: template/js/flow.js stands the baseline of a label over a horizontal second segment this far
# above the base of the lattice line that segment runs along
LABEL_OVER = 9
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


# Models drawn next to the reported one (docstring cases 7 to 11).
CASES = {
    # six straight lines between a and the pill b, offsets -20..20: the outer ones saturate
    "two-point-side-miss": {"kind": "flow", "nodes": [step("a", True), pill("b")], "grid": ["a b"],
                            "edges": ["a -> b"] * 3 + ["b -> a"] * 3 + ["a -> b"]},
    # five straight lines, -16..16, the ones at 8 and 16 leaving from different cards
    "two-point-order": {"kind": "flow", "nodes": [step("a", True), pill("b")], "grid": ["a b"],
                        "edges": ["a -> b"] * 3 + ["b -> a", "a -> b", "b -> a"]},
    # row line of e: e -> a (16) at the band's upper limit (its largest y), the interior run of a -> d (8);
    # three lines from e to b keep five on that row line now that the router leaves the top margin alone
    "upper-limit-interior-run": {
        "kind": "flow", "nodes": [pill("d"), pill("b"), pill("e"), pill("c"), step("a", True)],
        "grid": ["d b", "e .", "c a"],
        "edges": ["b -> d", "a -> d", "b -> a", "c -> b", "c -> a", "c -> b", "b -> e", "e -> b", "e -> b",
                  "e -> b", "a -> d", "e -> a"]},
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
    # a -> b leaves a down and runs along the row line of the pill b and the taller c into b's side,
    # b -> c straight between them: that row line's base is b's middle, above the row's middle
    "label-over-row-line": {"kind": "flow", "grid": ["a x .", ". b c"], "edges": ["a -> b : да", "b -> c", "x -> c"],
                            "nodes": [step("a"), step("x"), pill("b"),
                                      {"id": "c", "title": STEP["title"], "text": STEP["text"] + ", и ещё строка"}]},
    # a -> d comes into the gutter between the columns from the left and leaves it to the right,
    # c -> b the other way round: the two lines along it must swap sides
    "gutter-swap": {"kind": "flow", "nodes": [{"id": i, "title": i, "text": "Text"} for i in "bdac"],
                    "grid": ["b d", "a c"], "edges": ["a -> d", "c -> b"]},
    # a -> d and d -> a along the gutter between the rows, d -> a above from end to end
    "gutter-no-swap": {"kind": "flow", "nodes": [{"id": i, "title": i, "text": "Text"} for i in "abcd"],
                       "grid": ["a b .", ". c d"], "edges": ["a -> d", "d -> a"]},
    # d -> a and a -> d share the stretch (1,1)-(2,1)-(2,2) and turn together at (2,1): no crossing
    "shared-corner": {"kind": "flow", "nodes": [step(i) for i in "abcd"], "grid": ["a b", "c d"],
                      "edges": ["d -> a", "a -> d"]},
}
# Five or more lines along one row line (docstring case 7).
SATURATED = ("two-point-side-miss", "two-point-order", "upper-limit-interior-run", "lower-limit-interior-run")

# Docstring case 14. Two cards per row and two rows, so the outer lattice lines are Y = 0 and
# Y = 4, with the paths put in by hand: `route` prices a margin above every inner gutter, so no
# model of its own would draw one, and what is measured is where by() of template/js/flow.js puts
# such a line — a question about the script, not about the router. Titles stay one line high and
# the models carry no title and no scenario, so above the grid box stands nothing but the section:
# the narrowest the top room ever is. Below it the section always goes on, so each kind comes in
# two models — without footnotes, where the legend follows the grid box, and with one, where the
# `.dg-foot` list comes between them — and those are the two bottom rooms.
MARGIN_PATHS = [[(1, 1), (1, 0), (3, 0), (3, 1)],   # a -> b over the top margin
                [(1, 3), (1, 4), (3, 4), (3, 3)]]   # c -> d under the bottom margin
MARGIN_LANES = {"lanes": ["one", "two"],
                "groups": {"one": {"label": "Первый", "ramp": "teal"},
                           "two": {"label": "Второй", "ramp": "blue"}}}


def margin_model(kind, footnotes):
    """A margin model of `kind`; with `footnotes` the top-left card carries the only reference, so
    the two models of a kind differ in the footnote list under the grid and in nothing else the
    bottom margin can see (the card that grows stands in the top row, the line under the bottom)."""
    nodes = [step(i) for i in "abcd"]
    model = {"kind": kind, "nodes": nodes, "grid": ["a b", "c d"], "edges": ["a -> b", "c -> d"]}
    if kind == "swimlane":
        model.update(MARGIN_LANES)
    if footnotes:
        nodes[0] = {**nodes[0], "text": "Сноска [1]"}
        model["footnotes"] = ["Что здесь измеряется"]
    return model


MARGINS = {f"margin-{kind}{'-foot' if foot else ''}": (margin_model(kind, foot), MARGIN_PATHS)
           for kind in ("flow", "swimlane") for foot in (False, True)}
# Which row of the tables of diagrams/flow.py each margin model measures: (kind, footnotes).
MARGIN_CASE = {f"margin-{kind}{'-foot' if foot else ''}": (kind, foot)
               for kind in ("flow", "swimlane") for foot in (False, True)}

# Docstring case 15. A page flow of six columns by four rows, every cell a card, with a group at
# the capacity of each kind of line: eight lines along the row gutter Y = 2 (pitch 5), five along
# the column gutter X = 2 (pitch 6), three along the left margin X = 0 (pitch 5) and one under the
# bottom margin Y = 8, which is all a page holds there. The routes are put in by hand, as the
# margin models' are: the router prices a line that would fill a gutter, so no model of its own
# would draw these, and what is measured is where a group drawn as wide as its line allows ends up.
CAP_COLS, CAP_ROWS = 6, 4
CAP_IDS = [[f"c{r}{c}" for c in range(CAP_COLS)] for r in range(CAP_ROWS)]
CAP_EDGES = [("c00", "c15"), ("c01", "c14"), ("c02", "c13"), ("c03", "c12"), ("c04", "c11"),
             ("c05", "c10"), ("c00", "c14"), ("c05", "c11"),
             ("c10", "c21"), ("c11", "c20"), ("c20", "c31"), ("c21", "c30"), ("c10", "c30"),
             ("c00", "c30"), ("c10", "c20"), ("c30", "c00"),
             ("c30", "c31")]
CAP_PATHS = [[(1, 1), (1, 2), (11, 2), (11, 3)], [(3, 1), (3, 2), (9, 2), (9, 3)],
             [(5, 1), (5, 2), (7, 2), (7, 3)], [(7, 1), (7, 2), (5, 2), (5, 3)],
             [(9, 1), (9, 2), (3, 2), (3, 3)], [(11, 1), (11, 2), (1, 2), (1, 3)],
             [(1, 1), (1, 2), (9, 2), (9, 3)], [(11, 1), (11, 2), (3, 2), (3, 3)],
             [(1, 3), (2, 3), (2, 5), (3, 5)], [(3, 3), (2, 3), (2, 5), (1, 5)],
             [(1, 5), (2, 5), (2, 7), (3, 7)], [(3, 5), (2, 5), (2, 7), (1, 7)],
             [(1, 3), (2, 3), (2, 7), (1, 7)],
             [(1, 1), (0, 1), (0, 7), (1, 7)], [(1, 3), (0, 3), (0, 5), (1, 5)],
             [(1, 7), (0, 7), (0, 1), (1, 1)],
             [(1, 7), (1, 8), (3, 8), (3, 7)]]
CAPACITY = {"capacity-at-pitch": (
    {"kind": "flow", "nodes": [{"id": i, "title": i.upper()} for row in CAP_IDS for i in row],
     "grid": ["  ".join(row) for row in CAP_IDS],
     "edges": [f"{a} -> {b}" for a, b in CAP_EDGES]},
    CAP_PATHS)}
# pixels: a line keeps LINE_CLEAR from a card edge by construction; the browser is asked for this
# much, which leaves a pixel for the layout's own rounding
CARD_CLEAR = 3.0

# Docstring case 16. Three lines that have to leave the row of cards they run between: a flow's top
# margin holds none, so they went down, and the empty row at the foot of the grid is where they went
# — into its own cells or along the margin under it, neither of which the page has a track for. The
# flow's leading empty row is the other half of the rule: that one does get a track, and the third
# line runs along it. The models are the branch gate's, with the room a page needs to hold three
# lines that all go around.
TRAILING_LANES = {"lanes": ["one", "two", "three"],
                  "groups": {**MARGIN_LANES["groups"], "three": {"label": "Третий", "ramp": "purple"}}}
TRAILING = {
    "trailing-row-flow": {"kind": "flow", "nodes": [step(i) for i in "abc"],
                          "grid": [". . .", "a b c", ". . ."], "edges": ["a -> c"] * 3},
    "trailing-row-swimlane": {"kind": "swimlane", "nodes": [step(i) for i in "abc"],
                              "grid": ["a b c", ". . ."], "edges": ["a -> c"] * 3, **TRAILING_LANES},
}

# Docstring case 17. Two grids, each holding two runs of empty rows — a leading one and one between
# two rows of cards — so that four shapes are measured on two pages per kind and mode: a run of one
# of each in "empty-band-1" and a run of two of each in "empty-band-2". The routes are put in by
# hand, as the margin models' are: what is measured is where by() of template/js/flow.js puts a line
# on each lattice row line of a band, which is a question about the script and not about the router.
# One line per row line, so each is a group of one and is drawn on the line's own base, and the
# columns the lines leave and enter are the outer ones, whose cells below and above hold no card.
EMPTY_BAND_LANES = {"lanes": ["one", "two", "three"], "groups": TRAILING_LANES["groups"]}
EMPTY_BAND_SHAPES = {
    # name: (grid, node ids, the runs as (band lines, the row line the lines leave, the one they enter))
    "empty-band-1": ([". . .", "a b c", ". . .", "d e f"], "abcdef",
                     [((0, 1, 2), 3, 3), ((4, 5, 6), 3, 7)]),
    "empty-band-2": ([". . .", ". . .", "a b c", ". . .", ". . .", "d e f"], "abcdef",
                     [((0, 1, 2, 3, 4), 5, 5), ((6, 7, 8, 9, 10), 5, 11)]),
}


def empty_band_paths(runs):
    """One hand-made path per lattice row line of every band: out of the card in the first column,
    along that row line, into the card in the last one."""
    return [[(1, src), (1, Y), (5, Y), (5, dst)] for band, src, dst in runs for Y in band]


def empty_band_page(kind, name):
    """(model, paths) of one shape in one kind."""
    grid, ids, runs = EMPTY_BAND_SHAPES[name]
    paths = empty_band_paths(runs)
    model = {"kind": kind, "nodes": [step(i) for i in ids], "grid": grid,
             "edges": [f"{ids[0]} -> {ids[2]}"] * len(paths)}
    if kind == "swimlane":
        model.update(EMPTY_BAND_LANES)
    return model, paths


EMPTY_BANDS = {f"{name}-{kind}": empty_band_page(kind, name)
               for name in EMPTY_BAND_SHAPES for kind in ("flow", "swimlane")}
# Which shape and kind each of those pages measures, so a test can name the runs it has to find.
EMPTY_BAND_CASE = {f"{name}-{kind}": (name, kind)
                   for name in EMPTY_BAND_SHAPES for kind in ("flow", "swimlane")}

# Docstring case 18. A page flow of four columns with a leading empty row and one between its two
# rows of cards, holding a group at the capacity of every line of the two bands: three along the row
# line of the leading empty row (Y = 1, pitch 5) and three along the gutter under it (Y = 2), then
# five along each of the three lines of the interior band (Y = 4, 5 and 6, pitch 5). The top margin
# above the leading row and the bottom margin hold 0 and 1, so neither carries a group here. The
# routes are put in by hand, as the capacity model's are.
BAND_CAP_IDS = ["abcd", "efgh"]
BAND_CAP_LINES = ((1, 3), (2, 3), (4, 5), (5, 5), (6, 5))  # (lattice row line, lines along it)
BAND_CAP_PATHS = [[(1, 3), (1, Y), (7, Y), (7, 3 if Y < 3 else 7)]
                  for Y, count in BAND_CAP_LINES for _ in range(count)]
BAND_CAPACITY = {"empty-band-at-pitch": (
    {"kind": "flow", "nodes": [step(i) for row in BAND_CAP_IDS for i in row],
     "grid": [". . . .", "  ".join(BAND_CAP_IDS[0]), ". . . .", "  ".join(BAND_CAP_IDS[1])],
     "edges": [f"{BAND_CAP_IDS[0][0]} -> {BAND_CAP_IDS[0][3] if Y < 3 else BAND_CAP_IDS[1][3]}"
               for Y, count in BAND_CAP_LINES for _ in range(count)]},
    BAND_CAP_PATHS)}

# Written after the page has drawn (draw() runs at load, on fonts ready and at 300 ms): `lines`, the
# `d` of the line of every edge group in the svg, in drawing order, which is the order of the edges
# the renderer handed to the page; `texts`, in the same order, the [x, y] of the group's label text
# or null; `cards`, the box [left, top, right, bottom] of every card, taken from the page layout and
# mapped into the svg's own coordinates, the ones `d` is written in; `boxes`, the same for the grid
# box (`grid`), the section that clips what leaves it (`sec`), every swimlane header (`heads`), the
# footnote list (`foot`, absent when the model has none) and the legend (`legend`, with `legendpad`,
# its computed padding-top in those same units, the gap between its box top and its first text).
# Whatever bounds a line drawn along an outer margin stands among them.
PROBE = ("<script>setTimeout(function(){var o={lines:[],texts:[],cards:{},boxes:{heads:[]}},"
         "s=document.querySelector('.dg-svg');"
         "document.querySelectorAll('.dg-svg > g').forEach(function(g){var p=g.querySelector('path'),"
         "t=g.querySelector('text');o.lines.push([g.getAttribute('data-e'),p?p.getAttribute('d'):null]);"
         "o.texts.push(t?[+t.getAttribute('x'),+t.getAttribute('y')]:null)});"
         "if(s){var m=s.getScreenCTM().inverse(),q=s.createSVGPoint();"
         "var u=function(x,y){q.x=x;q.y=y;var w=q.matrixTransform(m);return[w.x,w.y]};"
         "var b=function(el){var r=el.getBoundingClientRect();return u(r.left,r.top).concat(u(r.right,r.bottom))};"
         "document.querySelectorAll('.dg-grid [data-t]').forEach(function(c){var t=c.getAttribute('data-t');"
         "if(!o.cards[t])o.cards[t]=b(c)});"
         "var gr=document.querySelector('.dg-grid'),sc=document.querySelector('.dg');"
         "if(gr)o.boxes.grid=b(gr);if(sc)o.boxes.sec=b(sc);"
         "document.querySelectorAll('.dg-lanehead').forEach(function(h){o.boxes.heads.push(b(h))});"
         "var ft=document.querySelector('.dg-foot'),lg=document.querySelector('.dg-legend');"
         "if(ft)o.boxes.foot=b(ft);"
         "if(lg){o.boxes.legend=b(lg);"
         "o.boxes.legendpad=u(0,parseFloat(getComputedStyle(lg).paddingTop)||0)[1]-u(0,0)[1]}}"
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


def render_page(model, mode, path, paths=None):
    """Write the page of `model` in `mode` to `path` through the renderer's own entry points, with
    the probe appended; returns the layout the page was drawn from. With `paths`, the routing of
    this one page is those lattice paths instead of the router's: everything after routing —
    offsets, the edge JSON, the script — is the renderer's own, except that the capacity check is
    silenced. A hand-made route is put where the router would not put one — along a margin that
    holds no line at all — precisely to measure what stands there, and the check exists to stop
    the router doing that."""
    argv = [str(path), "--mode", mode, "--assets", "inline"] + (["--harness"] if mode == "widget" else [])
    args = render.parse_args(argv)
    assets_mode, note = render.resolve_assets(args)
    if assets_mode != "inline":
        raise HarnessError(f"assets mode {assets_mode!r} instead of inline: {note}")
    model = json.loads(json.dumps(model))  # the planner may annotate the model it is given
    mod = render.KINDS[model["kind"]]
    if paths is None:
        out, _, layout = render.produce(model, mod, args, {}, assets_mode)
    else:
        given = [[tuple(pt) for pt in p] for p in paths]
        with mock.patch.object(router, "route_all", lambda lat, ends, labelled: given), \
                mock.patch.object(router, "overfull", lambda paths, nodes, room: []):
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


def second_run_label_misses(layout, names, lines, texts, cards):
    """(misses, checked): labels over a horizontal second segment on a lattice row line (odd Y) whose
    baseline does not stand LABEL_OVER above that row line's base as drawn: the y, less its offset,
    of that second segment, away from the band's limits."""
    bands = row_bands(layout, cards)
    misses, checked = [], 0
    for i, e in enumerate(layout["edges"]):
        path = e["path"]
        if not e["label"] or len(path) < 3 or path[1][1] != path[2][1] or path[1][1] % 2 == 0:
            continue
        if len(path) != len(lines[i]) + 1 or lines[i][1][0] != "h":
            continue  # the page merged points of this line; its runs cannot be matched to the lattice
        Y, y = path[1][1], lines[i][1][1]
        if at_limit(y, bands.get(Y)):
            continue
        if texts[i] is None:
            raise HarnessError(f"{names[i]} has a label over its second segment and no text in the page")
        checked += 1
        base = y - path[1][3]
        if abs(texts[i][1] + LABEL_OVER - base) > AXIS_TOL:
            misses.append(f"{names[i]}: label over its second segment on row line {Y} has its baseline at y "
                          f"{texts[i][1]:.2f}; the row line's base, from that segment, is {base:.2f}")
    return misses, checked


def runs_on_row_lines(layout, lines, wanted):
    """{Y: [pixel y]} of every horizontal run drawn on one of the lattice row lines `wanted`, matched
    to its lattice segment."""
    out = {}
    for i, e in enumerate(layout["edges"]):
        path = e["path"]
        if len(path) != len(lines[i]) + 1:
            continue  # the page merged points of this line; its runs cannot be matched to the lattice
        for k, (a, b) in enumerate(zip(path, path[1:])):
            if a[1] == b[1] and a[1] in wanted and lines[i][k][0] == "h":
                out.setdefault(a[1], []).append(lines[i][k][1])
    return out


def margin_runs(layout, lines):
    """{Y: [pixel y]} of every horizontal run drawn along an outer lattice margin — Y = 0, the top,
    or Y = 2 * rows, the bottom."""
    return runs_on_row_lines(layout, lines, {0, 2 * layout["grid_rows"]})


def card_rows(layout, cards):
    """{grid row: (top, bottom)} of every row that holds cards, as the page lays them out: the extent
    tracks() of template/js/head.js takes such a row's track from."""
    out = {}
    for nid, box in cards.items():
        r = layout["cells"][nid][0]
        t, b = box[1], box[3]
        out[r] = (min(out[r][0], t), max(out[r][1], b)) if r in out else (t, b)
    return out


def band_bases(margin, run, above, below):
    """{lattice row line: pixel y} the rule of docstring case 17 gives for one run of empty rows:
    `run` its row indices in order, `above` the bottom of the cards over it or None where the run
    leads the grid, `below` the top of the cards under it.

    tracks() of template/js/head.js invents the tracks of the run in ascending order, so each of them
    sees the one above it: a leading run starts TRACK_LEAD px over the first cards and every row after
    it halves what is left of the way down to them, and an interior run halves the span between the
    two card edges the same way. by() then puts a row line on its own track, a gutter halfway between
    two tracks, and the top margin `margin` px over the first track."""
    if above is None:
        ys = [below - TRACK_LEAD / 2 ** j for j in range(len(run))]
        first = ys[0] - margin
    else:
        ys = [below - (below - above) / 2 ** (j + 1) for j in range(len(run))]
        first = (above + ys[0]) / 2
    out = {2 * run[0]: first, 2 * (run[-1] + 1): (ys[-1] + below) / 2}
    for j, y in enumerate(ys):
        out[2 * (run[0] + j) + 1] = y
        if j:
            out[2 * (run[0] + j)] = (ys[j - 1] + y) / 2
    return out


def margin_room(y, top, boxes, cards):
    """((lower, higher), what bounds the line on the far side from the cards): the raw px a line
    drawn at pixel `y` along an outer margin keeps on each side, lower coordinate first.

    The cards lie below a top margin and above a bottom one. On the other side stands whatever
    clips or covers the line. Above: the grid box, the section, which scrolls and so clips what
    leaves it, or a swimlane header. Below: the section again, and the content the section goes on
    with — the footnote list when the model has one, then the legend, whose own text starts a
    padding-top inside its box. The grid box is not among them below, because `.dg-svg` is drawn
    with `overflow:visible` and the section, not the box, is what clips. The nearest bound is the
    one taken, and a negative number says the line is drawn past it already."""
    if top:
        cardward = min(c[1] for c in cards.values()) - y
        bounds = [("grid box", y - boxes["grid"][1]), ("section", y - boxes["sec"][1])]
        bounds += [("swimlane header", y - h[3]) for h in boxes["heads"]]
    else:
        cardward = y - max(c[3] for c in cards.values())
        bounds = [("section", boxes["sec"][3] - y)]
        if "foot" in boxes:
            bounds.append(("footnote list", boxes["foot"][1] - y))
        if "legend" in boxes:
            bounds.append(("legend text", boxes["legend"][1] + boxes["legendpad"] - y))
    name, edgeward = min(bounds, key=lambda b: b[1])
    return ((edgeward, cardward) if top else (cardward, edgeward)), name


def gap_to_box(run, box):
    """How far a drawn run lies from the rectangle `box` = [left, top, right, bottom], in px: 0
    when it touches or enters it."""
    axis, coord, lo, hi = run
    x1, x2, y1, y2 = (lo, hi, coord, coord) if axis == "h" else (coord, coord, lo, hi)
    dx = max(box[0] - x2, x1 - box[2], 0.0)
    dy = max(box[1] - y2, y1 - box[3], 0.0)
    return math.hypot(dx, dy)


def card_clearance_misses(layout, names, lines, cards):
    """(misses, checked): drawn runs that come nearer than CARD_CLEAR to a card their line does not
    end on. A line meets the two cards of its own edge, so those two are its own; every other card
    is what LINE_CLEAR keeps a group away from, whatever pitch the group was drawn at."""
    misses, checked = [], 0
    for e, name, runs_of in zip(layout["edges"], names, lines):
        own = {e["a"], e["b"]}
        for run in runs_of:
            for card, box in sorted(cards.items()):
                if card in own:
                    continue
                checked += 1
                gap = gap_to_box(run, box)
                if gap < CARD_CLEAR - AXIS_TOL:
                    misses.append(f"{name} {run[0]} at {run[1]:.2f} spanning {run[2]:.2f}..{run[3]:.2f} "
                                  f"is {gap:.2f} px from {card}")
    return misses, checked


def outside_box_misses(layout, names, lines, box):
    """(misses, checked): drawn runs that leave the grid box, of the lines that stay inside it. A
    line along an outer row margin is drawn outside the box by design — `.dg-svg` does not clip —
    and is measured against what stands there instead (margin_room), so it is left out here."""
    misses, checked = [], 0
    last = 2 * layout["grid_rows"]
    for e, name, runs_of in zip(layout["edges"], names, lines):
        if any(pt[1] in (0, last) for pt in e["path"]):
            continue
        for axis, coord, lo, hi in runs_of:
            checked += 1
            xs, ys = ((lo, hi), (coord, coord)) if axis == "h" else ((coord, coord), (lo, hi))
            if (min(xs) < box[0] - AXIS_TOL or max(xs) > box[2] + AXIS_TOL
                    or min(ys) < box[1] - AXIS_TOL or max(ys) > box[3] + AXIS_TOL):
                misses.append(f"{name} {axis} at {coord:.2f} spanning {lo:.2f}..{hi:.2f} leaves the grid "
                              f"box {box[0]:.2f}..{box[2]:.2f} x {box[1]:.2f}..{box[3]:.2f}")
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
        cls.models = [(REPORTED_NAME, REPORTED)] + list(CASES.items()) + list(TRAILING.items()) + cls.examples
        # the margin and capacity models are routed by hand, so they stand beside the models the
        # router routed; the capacity one is a page's, and its groups are over a widget's capacity
        drawn = [(name, model, None, MODES) for name, model in cls.models]
        drawn += [(name, model, paths, MODES) for name, (model, paths) in MARGINS.items()]
        drawn += [(name, model, paths, MODES) for name, (model, paths) in EMPTY_BANDS.items()]
        drawn += [(name, model, paths, ("page",)) for name, (model, paths) in CAPACITY.items()]
        drawn += [(name, model, paths, ("page",)) for name, (model, paths) in BAND_CAPACITY.items()]
        jobs, cls.layouts, cls.results = [], {}, {}
        for name, model, paths, modes in drawn:
            for mode in modes:
                page = root / f"{name}-{mode}.html"
                try:
                    cls.layouts[name, mode] = render_page(model, mode, page, paths)
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
                    self.check_crossings(name, mode)
                    self.check_row_order(name, mode)
                    if name in SATURATED:
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

    def test_label_over_second_run(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                layout, names, lines = self.measured("label-over-row-line", mode)
                got = self.results["label-over-row-line", mode]
                try:
                    misses, checked = second_run_label_misses(layout, names, lines, got["texts"], got["cards"])
                except HarnessError as exc:
                    self.fail(f"harness: label-over-row-line {mode}: {exc}")
                self.assertEqual(misses, [], f"label-over-row-line {mode}: a label over a second segment off its base")
                # the case exists only if a -> b runs its second segment along the row line of b and c
                self.assertEqual(checked, 1, f"harness: {mode}: no label over a second segment on a row line was checked")

    def test_planned_crossing(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                layout, _, _ = self.measured("planned-crossing", mode)
                self.assertEqual(router.crossings(layout["paths"]), 1, f"harness: {mode}: the crossing is not planned")
                self.check_crossings("planned-crossing", mode)

    def test_shared_gutter(self):
        for name, drawn in (("gutter-swap", 1), ("gutter-no-swap", 0)):
            for mode in MODES:
                with self.subTest(model=name, mode=mode):
                    layout, names, lines = self.measured(name, mode)
                    p, q = (router.segments(x) for x in layout["paths"])
                    shared = [(a, n) for a, n, lo, hi in p for b, m, lo2, hi2 in q
                              if (a, n) == (b, m) and max(lo, lo2) < min(hi, hi2)]
                    # the case exists only if the two lines run along one lattice segment and the page
                    # draws them crossing there as many times as their ends demand
                    self.assertTrue(shared, f"harness: {name} {mode}: the lines share no lattice segment")
                    self.assertEqual(len(pixel_crossings(names, lines)), drawn,
                                     f"harness: {name} {mode}: the page draws another number of crossings")
                    self.check_crossings(name, mode)

    def measure_margins(self):
        """One line per (kind, mode, footnotes, margin): the room the page shows, what bounds it
        away from the cards, and the constant diagrams/flow.py carries for it. Only the bottom
        table is keyed by the footnotes as well — above the grid box nothing changes with them."""
        out = []
        for name, (kind, foot) in sorted(MARGIN_CASE.items()):
            for mode in MODES:
                layout, _, lines = self.measured(name, mode)
                got = self.results[name, mode]
                self.assertEqual("foot" in got["boxes"], foot,
                                 f"harness: {name} {mode}: the page's footnote list does not match the model")
                found = margin_runs(layout, lines)
                for where, Y, top in (("top", 0, True), ("bottom", 2 * layout["grid_rows"], False)):
                    ys = found.get(Y, [])
                    self.assertEqual(len(ys), 1, f"harness: {name} {mode}: {len(ys)} lines drawn along "
                                                 f"the {where} margin, one was put there")
                    room, by = margin_room(ys[0], top, got["boxes"], got["cards"])
                    want = flow.TOP_ROOM.get((kind, mode)) if top else flow.BOTTOM_ROOM.get((kind, mode, foot))
                    out.append((kind, mode, foot, where, ys[0], room, by, want))
        return out

    def test_margin_room_matches_the_constants(self):
        measured = self.measure_margins()
        shown = "\n".join(f"  {kind:8} {mode:6} footnotes {str(foot):5} {where:6} line at y {y:8.2f}, room "
                          f"({room[0]:6.2f}, {room[1]:6.2f}) against the {by}, constant {want}"
                          for kind, mode, foot, where, y, room, by, want in measured)
        off = [f"{kind} {mode} footnotes {foot} {where}" for kind, mode, foot, where, _, room, _, want in measured
               if want is None or max(abs(a - b) for a, b in zip(room, want)) > AXIS_TOL]
        self.assertEqual(off, [], "the page does not show the room the constants claim:\n" + shown)

    def test_the_top_room_does_not_change_with_the_footnotes(self):
        """A footnote list goes under the grid box, so it moves the bottom margin's bound and not
        the top's — which is why only BOTTOM_ROOM is keyed by it."""
        rooms = {}
        for kind, mode, foot, where, _, room, by, _ in self.measure_margins():
            if where == "top":
                rooms.setdefault((kind, mode), []).append((foot, room, by))
        for key, seen in sorted(rooms.items()):
            with self.subTest(kind=key[0], mode=key[1]):
                self.assertEqual({(room, by) for _, room, by in seen}, {(seen[0][1], seen[0][2])},
                                 f"the top margin of {key[0]} {key[1]} differs with the footnotes: {seen}")

    def capacity_layout(self):
        """The layout of the capacity model, with what the offsets came out as: the four groups it
        is built from, each as wide as its line holds. `render_page` silences the capacity check
        for a hand-made routing, so the check is run here instead — this model is at capacity, not
        over it, and a group that grew past it would be measuring something else."""
        layout = self.layouts["capacity-at-pitch", "page"]
        geo = flow.Geometry(layout["mode"], layout["card_w"], layout["grid_cols"], layout["grid_rows"],
                            *flow.margin_room(layout["kind"], "page", layout["footnotes"]))
        self.assertEqual(router.overfull(layout["paths"], frozenset(layout["lattice"].blocked), geo.room), [],
                         "harness: the model is over its capacity, not at it")
        spread = {}
        for e in layout["edges"]:
            for x, y, ox, oy in e["path"]:
                if x % 2 == 0:
                    spread.setdefault(("v", x), set()).add(ox)
                if y % 2 == 0:
                    spread.setdefault(("h", y), set()).add(oy)
        return {key: sorted(offs) for key, offs in spread.items()}

    def test_the_capacity_model_fills_each_line(self):
        # the case exists only while each of the four groups is drawn as wide as its line holds:
        # five at 6 px in a column gutter, eight at 5 px in a row gutter, three at 5 px on the
        # left margin, and the one line a page's bottom margin has room for
        spread = self.capacity_layout()
        self.assertEqual(spread[("v", 2)], [-12.0, -6.0, 0.0, 6.0, 12.0])
        self.assertEqual(spread[("h", 2)], [-17.5, -12.5, -7.5, -2.5, 2.5, 7.5, 12.5, 17.5])
        self.assertEqual(spread[("v", 0)], [-5.0, 0.0, 5.0])
        self.assertEqual(spread[("h", 8)], [0.0])

    def test_lines_at_capacity_keep_clear_of_the_cards(self):
        """Docstring case 15, criterion B2: with a group at the capacity of a column gutter, a row
        gutter and a side margin, every line still keeps its distance from every card it does not
        end on and stays inside the grid box — the room the capacity is computed from is the room
        the page gives."""
        name = "capacity-at-pitch"
        layout, names, lines = self.measured(name, "page")
        got = self.results[name, "page"]
        misses, checked = card_clearance_misses(layout, names, lines, got["cards"])
        self.assertEqual(misses, [], f"{name}: a line at capacity comes too near a card")
        self.assertGreater(checked, 0, "harness: no line was measured against a card")
        misses, checked = outside_box_misses(layout, names, lines, got["boxes"]["grid"])
        self.assertEqual(misses, [], f"{name}: a line at capacity leaves the grid box")
        self.assertGreater(checked, 0, "harness: no line was measured against the grid box")

    def test_a_full_bottom_margin_clears_what_follows_the_grid(self):
        """The bottom margin lies outside the grid box, so what bounds a line there is the first
        content the section goes on with: a group filling that margin keeps EDGE_CLEAR from it."""
        name = "capacity-at-pitch"
        layout, _, lines = self.measured(name, "page")
        got = self.results[name, "page"]
        ys = margin_runs(layout, lines).get(2 * layout["grid_rows"], [])
        self.assertEqual(len(ys), 1, f"harness: {len(ys)} lines under the bottom margin, one fills it")
        (lower, higher), by = margin_room(ys[0], False, got["boxes"], got["cards"])
        self.assertGreaterEqual(higher, flow.EDGE_CLEAR - AXIS_TOL,
                                f"{name}: the line under the grid is {higher:.2f} px from the {by}")
        self.assertGreaterEqual(lower, CARD_CLEAR - AXIS_TOL,
                                f"{name}: the line under the grid is {lower:.2f} px from the cards")

    def measure_bands(self):
        """One record per (page, mode, run of empty rows): the lattice row lines of that band as the
        page drew them, and the y the rule of docstring case 17 gives for each, from the card edges
        that bound the run and from nothing else."""
        out = []
        for name, (shape, kind) in sorted(EMPTY_BAND_CASE.items()):
            runs = EMPTY_BAND_SHAPES[shape][2]
            for mode in MODES:
                layout, _, lines = self.measured(name, mode)
                cards = card_rows(layout, self.results[name, mode]["cards"])
                margin = max(8, layout["mode"]["pad_l"] - 6)
                drawn = runs_on_row_lines(layout, lines, {Y for band, _, _ in runs for Y in band})
                for band, _, _ in runs:
                    for Y in band:
                        self.assertEqual(len(drawn.get(Y, [])), 1,
                                         f"harness: {name} {mode}: {len(drawn.get(Y, []))} lines drawn "
                                         f"on the row line Y={Y}, one was put there")
                    run = [r for r in range(layout["grid_rows"]) if r not in cards and 2 * r + 1 in band]
                    above = cards[run[0] - 1][1] if run[0] else None
                    below = cards[run[-1] + 1][0]
                    out.append((name, mode, tuple(run), above, below, layout["mode"]["row_gap"],
                                {Y: drawn[Y][0] for Y in band}, band_bases(margin, run, above, below)))
        return out

    def test_the_band_of_an_empty_row_is_drawn_where_the_rule_says(self):
        """Docstring case 17: every lattice row line of the band — the top margin, the row line of each
        empty row, the gutters around them — stands where `tracks()` and `by()` put it, which is what
        `Geometry._band` of diagrams/flow.py takes the room of those lines from."""
        measured = self.measure_bands()
        self.assertTrue(measured, "harness: no band was measured")
        shown, off = [], []
        for name, mode, run, above, below, _, got, want in measured:
            where = "leading" if above is None else "interior"
            for Y in sorted(want):
                shown.append(f"  {name:22} {mode:6} {where} run {run} line Y={Y:<2} drawn at "
                             f"{got[Y]:8.2f}, the rule says {want[Y]:8.2f}")
                if abs(got[Y] - want[Y]) > AXIS_TOL:
                    off.append(f"{name} {mode} run {run} Y={Y}")
        self.assertEqual(off, [], "the page draws the band elsewhere than the rule says:\n"
                         + "\n".join(shown))

    def test_the_cards_around_an_interior_run_stand_one_row_gap_per_row_apart(self):
        """The halving of an interior run is measured from the span between the card edges, so the span
        is measured too: an empty implicit grid row is 0 px high and both of its row gaps stay, which
        puts the edges (k + 1) row gaps apart for k empty rows."""
        seen = 0
        for name, mode, run, above, below, row_gap, _, _ in self.measure_bands():
            if above is None:
                continue
            with self.subTest(page=name, mode=mode, run=run):
                self.assertAlmostEqual(below - above, (len(run) + 1) * row_gap, delta=AXIS_TOL)
                seen += 1
        self.assertGreater(seen, 0, "harness: no interior run of empty rows was measured")

    def test_the_top_margin_over_a_leading_empty_row_keeps_more_room_than_the_constant(self):
        """A leading empty row lifts the top margin a row gap and TRACK_LEAD px further from whatever
        clips or covers it, so TOP_ROOM — measured over a first row of cards — understates that side.
        diagrams/flow.py keeps the constant there rather than measuring a second table, and this is
        what makes keeping it the conservative choice. Towards the cards the nearest thing is no longer
        a card but the row line of the empty row, and the room is half the way to it instead."""
        for name, (_, kind) in sorted(EMPTY_BAND_CASE.items()):
            for mode in MODES:
                with self.subTest(page=name, mode=mode):
                    layout, _, lines = self.measured(name, mode)
                    got = self.results[name, mode]
                    ys = runs_on_row_lines(layout, lines, {0}).get(0, [])
                    self.assertEqual(len(ys), 1, f"harness: {len(ys)} lines along the top margin")
                    (away, _), by = margin_room(ys[0], True, got["boxes"], got["cards"])
                    want = flow.TOP_ROOM[kind, mode][0]
                    self.assertGreaterEqual(away, want, f"{name} {mode}: the line is {away:.2f} px from "
                                                       f"the {by}, less than the constant's {want}")

    def band_capacity_layout(self):
        """The layout of the empty-band capacity model, with what the offsets came out as: five groups,
        each as wide as its line of the two bands holds. `render_page` silences the capacity check for
        a hand-made routing, so the check runs here — this model is at capacity, not over it, and a
        group that grew past it would be measuring something else."""
        layout = self.layouts["empty-band-at-pitch", "page"]
        geo = flow.Geometry(layout["mode"], layout["card_w"], layout["grid_cols"], layout["grid_rows"],
                            *flow.margin_room(layout["kind"], "page", layout["footnotes"]),
                            layout["empty_rows"])
        self.assertEqual(router.overfull(layout["paths"], frozenset(layout["lattice"].blocked), geo.room), [],
                         "harness: the model is over its capacity, not at it")
        spread = {}
        for e in layout["edges"]:
            for _, y, _, oy in e["path"]:
                spread.setdefault(y, set()).add(oy)
        return {y: sorted(offs) for y, offs in spread.items()}

    def test_the_empty_band_model_fills_each_line_of_both_bands(self):
        # the case exists only while each of the five groups is drawn as wide as its line holds:
        # three at 5 px on the row line of the leading empty row and on the gutter under it, five at
        # 5 px on each of the three lines of the interior band
        spread = self.band_capacity_layout()
        self.assertEqual([spread[1], spread[2]], [[-5.0, 0.0, 5.0]] * 2)
        self.assertEqual([spread[Y] for Y in (4, 5, 6)], [[-10.0, -5.0, 0.0, 5.0, 10.0]] * 3)

    def test_lines_at_the_capacity_of_an_empty_band_keep_clear_of_the_cards(self):
        """Docstring case 18, criterion B2 on the band of an empty row: with a group at the capacity of
        every line of a leading band and an interior one, every line still keeps its distance from
        every card it does not end on and stays inside the grid box."""
        name = "empty-band-at-pitch"
        layout, names, lines = self.measured(name, "page")
        got = self.results[name, "page"]
        misses, checked = card_clearance_misses(layout, names, lines, got["cards"])
        self.assertEqual(misses, [], f"{name}: a line at capacity comes too near a card")
        self.assertGreater(checked, 0, "harness: no line was measured against a card")
        misses, checked = outside_box_misses(layout, names, lines, got["boxes"]["grid"])
        self.assertEqual(misses, [], f"{name}: a line at capacity leaves the grid box")
        self.assertGreater(checked, 0, "harness: no line was measured against the grid box")

    def test_a_trailing_empty_row_leaves_every_line_drawn(self):
        """Docstring case 16: an empty row under the last card row is no part of the lattice, so
        every line is drawn where the page has a track for it. A line planned under that row stops
        the script at the row it cannot read, and the page then holds only the lines before it."""
        for name, model in TRAILING.items():
            for mode in MODES:
                with self.subTest(model=name, mode=mode):
                    got = self.results[name, mode]
                    if isinstance(got, Exception):
                        self.fail(f"harness: {name} {mode}: {got}")
                    layout = self.layouts[name, mode]
                    want = [f"{e['a']} {e['b']}" for e in layout["edges"]]
                    drawn = [n for n, d in got["lines"] if d]
                    self.assertEqual(drawn, want, f"{name} {mode}: the page draws {len(drawn)} of "
                                                  f"{len(want)} lines; one was planned where it has no row")
                    # the case exists only if the grid's last row is the empty one that is left out
                    self.assertEqual(layout["grid_rows"], len(model["grid"]) - 1,
                                     f"harness: {name}: the grid's last row is not an empty one")
                    self.check_crossings(name, mode)
                    self.check_row_order(name, mode)

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
