"""Kinds `flow` (algorithm with decisions) and `swimlane` (steps by participant)."""
import json
import math
import re

from . import assets, router
from .common import (BASE_MODES, ID_RE, RAMPS, ModelError, esc, fit_prefix, label_width, labels_for, text_width,
                     too_wide_word, wrap_lines)
from .grid import check_placement, empty_lines, parse_grid

MODES = {
    "state": {
        "widget": {"gap": 28, "row_gap": 40, "char": 7.5, "tchar": 6.6, "max_cols": 4, "max_nodes": 16},
        "page": {"gap": 32, "row_gap": 44, "char": 7.6, "tchar": 6.7, "max_cols": 6, "max_nodes": 30},
    },
    "blocks": {
        "widget": {"gap": 28, "row_gap": 40, "char": 7.5, "tchar": 6.6, "max_cols": 3, "max_nodes": 12},
        "page": {"gap": 32, "row_gap": 44, "char": 7.6, "tchar": 6.7, "max_cols": 5, "max_nodes": 20},
    },
    "flow": {
        "widget": {"gap": 28, "row_gap": 40, "char": 7.5, "tchar": 6.6, "max_cols": 4, "max_nodes": 16},
        "page": {"gap": 32, "row_gap": 44, "char": 7.6, "tchar": 6.7, "max_cols": 6, "max_nodes": 30},
    },
    "swimlane": {
        "widget": {"gap": 18, "row_gap": 40, "char": 7.5, "tchar": 6.6, "max_cols": 5, "max_nodes": 16, "max_lanes": 5},
        "page": {"gap": 28, "row_gap": 44, "char": 7.6, "tchar": 6.7, "max_cols": 7, "max_nodes": 30, "max_lanes": 7},
    },
}
NODE_KINDS = ("step", "decision", "terminal", "note", "state", "block")
DEFAULT_KIND = {"state": "state", "blocks": "block"}
LABEL_MAX_CHARS, LABEL_MAX_WORDS = 24, 3
FOOT_RE = re.compile(r"\s*\[(\d+)\]\s*$")
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

# Where drawFlow in template/js/flow.js puts a label, in px; keep the two in step
# (tests/test_label_lines.py reads the script's numbers).
LABEL_BEND = 6    # from a bend: beside a vertical second segment, before the end of a horizontal one
LABEL_SIDE = 3    # from the card edge at a straight sideways exit
LABEL_BESIDE = 5  # from the line at a straight exit down or up
LABEL_BELOW = 14  # from the card's bottom edge to the baseline at a straight exit down
LABEL_ABOVE = 6   # from the baseline to the card's top edge at a straight exit up
LABEL_DROP = 4    # from the middle of the text down to its baseline
LABEL_CLEAR = 2   # the text box keeps this far from a card edge or a line
LINE_REACH = 7.5  # a horizontal line nearer than this to the middle of the text runs through it
LABEL_WORD = 8    # two labels in one row keep this much more apart, or they read as one phrase

# What a line on an even lattice line keeps clear, in px, and so cannot spend on the lines beside
# it: LINE_CLEAR from the nearest card edge, EDGE_CLEAR from the bound on the other side — the edge
# that clips or covers it, or the nearest content beyond the grid box.
LINE_CLEAR = 4
EDGE_CLEAR = 1

# The raw px an unoffset line on an outer margin has on each side, lower coordinate first: for the
# top margin towards whatever bounds it away from the cards and then towards the cards, for the
# bottom margin the other way round. The side margins follow from `pad_l`, `pad_r` and `margin`,
# and these do not: .dg-grid pads 8 px above and below the cards while by() of template/js/flow.js
# puts a margin line `margin` px outside them, so in a flow both margin lines fall outside the grid
# box. The two ends of that box are not alike, though.
#
# Above it the bound is the box's own top edge, because whatever stands directly above it is either
# the edge that clips or content nearer than the line. In a widget nothing in the section's flow
# stands above the grid, so the section's top edge coincides with the box's and clips there:
# overflow-x:auto on .dg makes overflow-y compute to auto. In a page the h3 title lies right above
# the box with margin-bottom 4 px — the draft badge and the route chips too when the model has
# them — so a line 10 px up runs through that text. Either way a negative number says the line is
# already past the bound. A swimlane's top margin instead falls one row gap under the lane headers,
# which cover it.
#
# Below the box nothing clips — .dg-svg is drawn with overflow:visible (template/css/base.css) —
# and the section goes on. The bound there is the first content after the grid: the .dg-foot list,
# margin-top 8 px, when the model has footnotes, else the text of the .dg-legend that render()
# always emits for these kinds, which starts a padding-top of 12 px inside its box. So the bottom
# room is keyed by the footnotes as well, and is the narrower of the two when there are any.
#
# Measured in the browser by tests/test_browser_lines.py, which fails when a change of the CSS
# moves them.
TOP_ROOM = {("flow", "widget"): (-4, 12), ("flow", "page"): (-10, 18),
            ("swimlane", "widget"): (28, 12), ("swimlane", "page"): (26, 18)}
BOTTOM_ROOM = {("flow", "widget", False): (12, 8), ("flow", "widget", True): (12, 4),
               ("flow", "page", False): (18, 2), ("flow", "page", True): (18, -2),
               ("swimlane", "widget", False): (12, 8), ("swimlane", "widget", True): (12, 4),
               ("swimlane", "page", False): (18, 2), ("swimlane", "page", True): (18, -2)}


def margin_room(kind, mode_name, footnotes):
    """(top, bottom) raw room of the outer margins for this kind and mode: only a swimlane carries
    lane headers, so every other kind is measured as a flow. `footnotes` says whether the model has
    any, which moves what the bottom margin is bounded by and nothing above the grid box."""
    key = ("swimlane" if kind == "swimlane" else "flow", mode_name)
    return TOP_ROOM[key], BOTTOM_ROOM[(*key, bool(footnotes))]


class Geometry:
    """Pixel x of cards and lattice lines, relative to the grid box, as template/js/flow.js derives
    them (tracks, bx, clampX). Card heights are unknown here, so there is no y, only the gutter
    between two rows of cards, `row_gap` high, whose middle by() puts lines in.

    `top` and `bottom` are the measured raw room of the outer row margins, which no rule here
    derives; a geometry built without them answers None for those two lines, which is what a
    caller with no capacity to enforce needs."""

    def __init__(self, mode, card_w, cols, rows=0, top=None, bottom=None):
        self.w = float(f"{card_w:.0f}")  # --dg-w is written rounded
        self.gap, self.pad_l, self.cols, self.total = mode["gap"], mode["pad_l"], cols, mode["total"]
        self.pad_r, self.rows = mode["pad_r"], rows
        self.row_gap = mode["row_gap"]
        self.margin = max(8, mode["pad_l"] - 6)
        self.top_room, self.bottom_room = top, bottom

    def left(self, c):
        return self.pad_l + c * (self.w + self.gap)

    def right(self, c):
        return self.left(c) + self.w

    def x(self, X):
        if X % 2:
            return self.left(X // 2) + self.w / 2
        g = X // 2
        if g == 0:
            return self.left(0) - self.margin
        if g == self.cols:
            return self.right(self.cols - 1) + self.margin
        return self.left(g) - self.gap / 2

    def clamp(self, c, x):
        return min(max(x, self.left(c) + 12), self.right(c) - 12)

    def room(self, axis, line):
        """The px the lines of one group on this lattice line may spread over, on each side of it,
        lower coordinate first, with LINE_CLEAR already taken off towards a card and EDGE_CLEAR
        towards whatever bounds them on the other side — the edge that clips or covers them, or,
        under the bottom margin, the content the section goes on with. A negative number says a
        line on the lattice line itself is already past that bound.

        None where there is no room to state: an odd line, which runs through the cards and is
        placed against their heights by the script, and an outer row margin this geometry was not
        given the measurement of."""
        if line % 2:
            return None
        g = line // 2
        if axis == "v":
            if g == 0:
                return (self.pad_l - self.margin - EDGE_CLEAR, self.margin - LINE_CLEAR)
            if g == self.cols:
                return (self.margin - LINE_CLEAR, self.pad_r - self.margin - EDGE_CLEAR)
            return (self.gap / 2 - LINE_CLEAR, self.gap / 2 - LINE_CLEAR)
        if g in (0, self.rows):
            raw = self.top_room if g == 0 else self.bottom_room
            if raw is None:
                return None
            lo, hi = (EDGE_CLEAR, LINE_CLEAR) if g == 0 else (LINE_CLEAR, EDGE_CLEAR)
            return (raw[0] - lo, raw[1] - hi)
        return (self.row_gap / 2 - LINE_CLEAR, self.row_gap / 2 - LINE_CLEAR)


def room_beside(start, side, obstacles, limit):
    """Free px from a label's near edge `start` outwards (R: rightwards, L: leftwards)
    to the first obstacle interval, keeping LABEL_CLEAR; at most `limit`. Negative
    when an obstacle already covers the start."""
    room = limit
    for a, b in obstacles:
        if side == "R" and b > start - LABEL_CLEAR:
            room = min(room, a - start - LABEL_CLEAR)
        elif side == "L" and a < start + LABEL_CLEAR:
            room = min(room, start - b - LABEL_CLEAR)
    return room


def band_obstacles(Y, own, paths, offsets, geo, occupied, horizontal=True, half=0, reach=0):
    """Cards and lines in lattice row Y (a row of cards when odd, a gutter when even), as
    px intervals across. `own` = (path index, segment index) is the segment the label
    stands beside and does not count; `horizontal=False` leaves out lines along the row.
    `half` = -1 or 1 is for a label standing wholly above or below a height in the row: it keeps
    the verticals that come into the row from that side or pass it, and the lines along the row
    whose offset lies more than `reach` px into that half from the row's base (a negative `reach`
    takes in lines on the other side of the base, up to that far). A vertical line ending in the
    row from the other half turns there and runs along the row, so it counts as that line.
    template/js/flow.js draws every point on a lattice row line from one base plus its offset:
    the middle of a gutter; on a row of cards the middle of the overlap of the cards that lines
    enter or leave sideways there, or the row's middle when there are none or they overlap by
    16 px or less. Beside a straight sideways line (-1, minus that line's offset) the text stands
    above that line, so a line along the row with a smaller offset runs through it, a straight
    line between the same two cards included; one with the same offset or a larger one passes
    under it.
    On a row of cards where a line enters or leaves a card sideways, template/js/flow.js then
    clamps every point into one band, 10 px inside the lowest top and the highest bottom of those
    cards: the clamp is monotonic, so the order the rule above compares holds, but a line far from
    the base is drawn nearer it, a few px off it when those cards are one title line high. Card
    heights are unknown here, so beside a vertical second segment (`half` 0) every line along such
    a row counts, whatever its offset; along any other row, one whose offset is under LINE_REACH."""
    cards = [(geo.left(c), geo.right(c)) for r, c in occupied if Y % 2 and r == Y // 2]
    # a path's ends are its cards' points: an end whose segment runs along Y enters or leaves a card
    # sideways there
    banded = any(q[0][1] == q[1][1] == Y or q[-1][1] == q[-2][1] == Y for q in paths)
    lines = []
    for j, (q, off) in enumerate(zip(paths, offsets)):
        for k in range(len(q) - 1):
            if (j, k) == own:
                continue
            (x1, y1), (x2, y2) = q[k], q[k + 1]
            lo, hi = min(y1, y2), max(y1, y2)
            if x1 == x2 and lo <= Y <= hi and not (half and (lo if half < 0 else hi) == Y):
                x = geo.x(x1) + off[k][0]
                lines.append((x - 1, x + 1))
            elif half and y1 == y2 == Y and off[k][1] * half > reach:
                xa, xb = geo.x(x1) + off[k][0], geo.x(x2) + off[k + 1][0]
                lines.append((min(xa, xb), max(xa, xb)))
            elif not half and horizontal and y1 == y2 == Y and (banded or abs(off[k][1]) < LINE_REACH):
                xa, xb = geo.x(x1) + off[k][0], geo.x(x2) + off[k + 1][0]
                lines.append((min(xa, xb), max(xa, xb)))
    return cards, lines


def under_card(node, paths, offsets, geo, occupied):
    """Cards and lines, as px intervals across, that a label hanging under the card at lattice
    point `node` meets when that card is shorter than its row: template/js/flow.js hangs the text
    from the card's own bottom edge, and cards align to the top of the row, so the text stands
    inside the row. The row's other cards count, and the lines drawn at their height: a line along
    the row, and a vertical coming down to the row to turn along it. A line leaving or entering
    `node` there is drawn within that card's height, above the text; a line reaching the gutter
    below is the gutter's."""
    X, R = node
    cards = [(geo.left(c), geo.right(c)) for r, c in occupied if r == R // 2 and c != X // 2]
    lines = []
    for q, off in zip(paths, offsets):
        for k in range(len(q) - 1):
            (x1, y1), (x2, y2) = q[k], q[k + 1]
            if y1 == y2 == R and node not in (q[k], q[k + 1]):
                xa, xb = geo.x(x1) + off[k][0], geo.x(x2) + off[k + 1][0]
                lines.append((min(xa, xb), max(xa, xb)))
            elif x1 == x2 and min(y1, y2) < max(y1, y2) == R:
                # where the line goes on along the row; none when it ends on a card's top edge here
                on = k + 2 if y2 == R else k - 1
                if 0 <= on < len(q) and q[on] != node:
                    x = geo.x(x1) + off[k][0]
                    lines.append((x - 1, x + 1))
    return cards, lines


def label_spots(i, e, p, paths, offsets, geo, cells, occupied, card_w, labels=()):
    """Places template/js/flow.js can give the label of routed edge i, each with its room in px:
    `room` counts cards, `line_room` other lines too (and, beside a vertical second segment, the
    `labels` already placed). A label above a horizontal second segment has no `line_room`:
    plan() checks its lines after placing it.
    Only a label beside a vertical second segment has a choice (its row `ly` and side);
    every other shape has one place. A spot also says where its text lies: the lattice rows
    it can fall in, `band` = (first, last), its near edge `start` and the direction `grow`
    the text runs from there."""
    off = offsets[i]
    r, c = cells[e["a"]]
    tc = cells[e["b"]][1]
    sa = router.side_of(p[0], p[1])
    if len(p) >= 3 and p[2][1] == p[1][1]:
        # above the horizontal second segment, ending LABEL_BEND before its far end; the cells
        # under the segment are empty, so the only limit is the line's own bend at p1
        x1 = geo.clamp(c, geo.x(p[1][0]) + off[1][0])
        if len(p) == 3:
            x2 = geo.left(tc) if p[2][0] > p[1][0] else geo.right(tc)
        else:
            x2 = geo.x(p[2][0]) + off[2][0]
            if len(p) == 4:
                x2 = geo.clamp(tc, x2)
        rt = x2 > x1
        return [{"where": "над вторым отрезком", "room": abs(x2 - x1) - LABEL_BEND - LABEL_CLEAR,
                 "band": (p[1][1], p[1][1]), "start": x2 - LABEL_BEND if rt else x2 + LABEL_BEND, "grow": "L" if rt else "R",
                 "key": ("h", p[1][1], p[2][0], p[2][0] > p[1][0])}]
    if len(p) >= 3:
        # beside the vertical second segment. Without `ly` template/js/flow.js centres the label on the
        # segment, at a pixel row that depends on card heights: that place is kept when the side
        # is clear in every row the middle can fall in. Otherwise the label is pinned to one row
        # the segment passes, gutters included: the middle first, the rows of its ends last.
        X, Y1, Y2 = p[1][0], p[1][1], p[2][1]
        x = geo.x(X) + off[1][0]
        if len(p) == 3:
            x = geo.clamp(tc, x)
        lo, hi = min(Y1, Y2), max(Y1, Y2)
        mid = (Y1 + Y2) / 2
        # the middle stays at least half a row off the ends: clear of the lines turning there and
        # of the target card the segment ends on, not of the cards beside the line at its start
        middle = [(Y, lo < Y < hi) for Y in range(lo, hi + 1) if not (len(p) == 3 and Y == Y2)]
        pinned = sorted(range(lo, hi + 1), key=lambda Y: (Y in (Y1, Y2), abs(Y - mid), abs(Y - Y1)))
        places = [(None, lo, hi, middle)] + [(Y, Y, Y, [(Y, True)]) for Y in pinned]
        spots = []
        for ly, blo, bhi, rows in places:
            cards, lines = [], []
            for Y, horizontal in rows:
                cs, ls = band_obstacles(Y, (i, 1), paths, offsets, geo, occupied, horizontal)
                cards += cs
                lines += ls
            lines += [(a - LABEL_WORD, b + LABEL_WORD) for l_lo, l_hi, a, b in labels if l_lo <= bhi and blo <= l_hi]
            for side in ("R", "L"):
                if (side == "R" and X == 2 * geo.cols) or (side == "L" and X == 0):
                    continue  # outside the grid box the section clips the text
                start = x + LABEL_BEND if side == "R" else x - LABEL_BEND
                limit = min(card_w - 20, geo.total - start if side == "R" else start)
                room = room_beside(start, side, cards, limit)
                spot = {"where": "рядом со вторым отрезком", "room": room, "side": side,
                        "line_room": room_beside(start, side, lines, room),
                        "band": (blo, bhi), "start": start, "grow": side, "key": ("v", X, blo, bhi, side)}
                if ly is not None:
                    spot["ly"] = ly
                spots.append(spot)
        return spots
    if sa in ("L", "R"):
        # straight sideways: from the card edge towards the next card in the row, which is the target,
        # above the label's own line; another line along the row above that line, where the text
        # stands, runs through it, and so does a vertical coming into the row from above or passing it
        cards = [(geo.left(cc), geo.right(cc)) for rr, cc in occupied if rr == r and cc != c]
        _, lines = band_obstacles(p[0][1], (i, 0), paths, offsets, geo, occupied, half=-1, reach=-off[0][1])
        start = geo.right(c) + LABEL_SIDE if sa == "R" else geo.left(c) - LABEL_SIDE
        room = room_beside(start, sa, cards, geo.gap + card_w - 20)
        return [{"where": "у выхода вбок", "room": room, "line_room": room_beside(start, sa, lines, room),
                 "band": (p[0][1], p[0][1]), "start": start, "grow": sa, "key": (e["a"], sa)}]
    # straight down or up: the text stands in the gutter under or over the card, clear of cards and
    # inside the section, between the card and the middle of the gutter. A line from the card's
    # side to that middle runs through it, and so does a line along the gutter less than
    # LINE_REACH from the text's middle, or nearer the card: under a card shorter than its row the
    # text stands higher, never lower, and when the row holds other cards it may stand in the row
    Y, half = (p[0][1] + 1, -1) if sa == "B" else (p[0][1] - 1, 1)
    middle = LABEL_BELOW - LABEL_DROP if sa == "B" else LABEL_ABOVE + LABEL_DROP  # off the card edge
    _, lines = band_obstacles(Y, (i, 0), paths, offsets, geo, occupied, half=half,
                              reach=geo.row_gap / 2 - middle - LINE_REACH)
    start = geo.clamp(c, geo.x(p[1][0]) + off[1][0]) + LABEL_BESIDE
    room = min(card_w, geo.total - start)
    if sa == "B" and any(rr == r and cc != c for rr, cc in occupied):
        cards, row_lines = under_card(p[0], paths, offsets, geo, occupied)
        room = room_beside(start, "R", cards, room)
        lines += row_lines
    return [{"where": "у выхода вниз" if sa == "B" else "у выхода вверх", "room": room,
             "line_room": room_beside(start, "R", lines, room), "band": (Y, Y), "start": start, "grow": "R",
             "key": (e["a"], sa)}]


def mode_for(kind, mode_name, overrides):
    mode = dict(BASE_MODES[mode_name])
    mode.update(MODES[kind][mode_name])
    mode.update(overrides or {})
    return mode


def node_kind(n, diagram="flow"):
    k = n.get("kind")
    if k:
        return k
    if n["id"].endswith("?"):
        return "decision"
    return DEFAULT_KIND.get(diagram, "step")


def parse_edge(e, errors, i):
    """'a -> b : label [n] | dashed' or the object form."""
    label_id = f"связь #{i + 1}"
    if isinstance(e, str):
        body, _, mods = e.partition("|")
        if "->" not in body:
            errors.append(f"{label_id}: ожидается 'a -> b : подпись'")
            return None
        ends, _, label = body.partition(":")
        a, b = (s.strip() for s in ends.split("->", 1))
        out = {"a": a, "b": b, "label": label.strip(), "dashed": False}
        for m in (x.strip() for x in mods.split(",") if x.strip()):
            if m == "dashed":
                out["dashed"] = True
            else:
                errors.append(f"{label_id}: неизвестный модификатор {m!r}; допустим dashed")
        return out
    try:
        return {"a": e["from"], "b": e["to"], "label": (e.get("label") or "").strip(), "dashed": bool(e.get("dashed"))}
    except (KeyError, TypeError):
        errors.append(f"{label_id}: нужны from и to")
        return None


def plan(model, mode_name, overrides=None, draft=False):
    kind = model.get("kind", "flow")
    lanes_mode = kind == "swimlane"
    errors, layout_errors, fit_errors, warnings = [], [], [], []

    def fit_error(msg):
        layout_errors.append(msg)
        fit_errors.append(msg)

    mode = mode_for(kind, mode_name, overrides)

    groups = model.get("groups") or {}
    nodes = model.get("nodes") or []
    footnotes = model.get("footnotes") or []
    max_groups = mode.get("max_lanes", 4)
    if len(groups) > max_groups:
        warnings.append(f"групп {len(groups)}: больше {max_groups} цветов читаются плохо")
    for gid, g in groups.items():
        if not ID_RE.match(gid) or gid.endswith("?"):
            errors.append(f"группа {gid!r}: id только из строчных латинских букв, цифр и _")
        if g.get("ramp") not in RAMPS:
            errors.append(f"группа {gid}: ramp должен быть одним из {', '.join(RAMPS)}")

    cells, grid_cols, grid_rows = parse_grid(model.get("grid"), errors)
    if grid_cols < 1 or grid_cols > mode["max_cols"]:
        layout_errors.append(f"grid шириной {grid_cols}: режим {mode_name} для {kind} допускает от 1 до {mode['max_cols']} столбцов")
    grid_cols = max(grid_cols, 1)
    card_w = (mode["total"] - mode["pad_l"] - mode["pad_r"] - mode["gap"] * (grid_cols - 1)) / grid_cols
    ch, tch = mode["char"], mode["tchar"]

    lanes = model.get("lanes") or []
    if lanes_mode:
        if not lanes:
            errors.append("swimlane: нужен список lanes с id групп, по одной на столбец")
        elif len(lanes) != grid_cols:
            errors.append(f"swimlane: дорожек {len(lanes)}, а столбцов в grid {grid_cols}; каждая дорожка это столбец")
        if len(lanes) > mode.get("max_lanes", 99):
            layout_errors.append(f"swimlane: дорожек {len(lanes)}, режим {mode_name} допускает до {mode['max_lanes']}; "
                                 f"объедините второстепенных участников в одну дорожку")
        for l in lanes:
            if l not in groups:
                errors.append(f"swimlane: дорожка {l!r} не описана в groups")

    by_id = {}
    if len(nodes) > mode["max_nodes"]:
        layout_errors.append(f"узлов {len(nodes)}, режим {mode_name} допускает до {mode['max_nodes']}: "
                             f"разбейте схему на обзор и детали")
    for n in nodes:
        nid = n.get("id")
        if not nid or not ID_RE.match(nid):
            errors.append(f"узел {nid!r}: id только из строчных латинских букв, цифр и _, знак ? допустим последним")
            continue
        if nid in by_id:
            errors.append(f"узел {nid}: id повторяется")
        by_id[nid] = n
        k = node_kind(n, kind)
        if k not in NODE_KINDS:
            errors.append(f"узел {nid}: kind {k!r} не из {NODE_KINDS}")
        if nid.endswith("?") and k != "decision":
            errors.append(f"узел {nid}: id с ? на конце это развилка, а kind = {k}")
        if not n.get("title"):
            errors.append(f"узел {nid}: нет title")
            continue
        if n.get("group") and n["group"] not in groups:
            errors.append(f"узел {nid}: группа {n['group']!r} не описана в groups")
        if lanes_mode and nid in cells:
            lane = lanes[cells[nid][1]] if cells[nid][1] < len(lanes) else None
            if n.get("group") and lane and n["group"] != lane:
                errors.append(f"узел {nid}: стоит в дорожке {lane}, а group = {n['group']}; цвет узла задаёт дорожка")
        extra = 21 if k == "decision" else 0
        if lanes_mode:
            extra += 30
        def title_fits(s, extra=extra, card_w=card_w):
            return text_width(s) * 1.04 + 20 + extra <= card_w
        if not title_fits(n["title"]):
            fit_error(f"узел {nid}: заголовок {len(n['title'])} симв., влезает "
                      f"{fit_prefix(n['title'], title_fits)}; "
                      f"сократите заголовок или сузьте grid")
        text = n.get("text") or ""
        m_note = FOOT_RE.search(text) if text else None
        if m_note:
            ref = int(m_note.group(1))
            if ref < 1 or ref > len(footnotes):
                errors.append(f"узел {nid}: сноска [{ref}] не описана в footnotes")
            else:
                n["_note"] = ref
                text = text[: m_note.start()].rstrip() + " " + CIRCLED[ref - 1]
                n["_text"] = text
        def text_fits(s, card_w=card_w):
            return wrap_lines(s, card_w - 20) <= 2
        if text:
            wide = too_wide_word(text, card_w - 20)
            if wide:
                fit_error(f"узел {nid}: слово {len(wide[0])} симв., влезает ~{wide[1]}")
            elif not text_fits(text):
                fit_error(f"узел {nid}: текст {len(text)} симв., в две строки влезает ~{fit_prefix(text, text_fits)}; "
                          f"сократите или вынесите в сноску")
        items = n.get("items") or []
        if items and k != "block":
            warnings.append(f"узел {nid}: items показываются только у block")
        if len(items) > 5:
            layout_errors.append(f"узел {nid}: пунктов {len(items)}, допустимо пять")
        def item_fits(s, card_w=card_w):
            return wrap_lines(s, card_w - 30) <= 2
        for pos, it in enumerate(items, 1):
            wide = too_wide_word(it, card_w - 30)
            if wide:
                fit_error(f"узел {nid}: пункт {pos} — слово {len(wide[0])} симв., влезает ~{wide[1]}")
            elif not item_fits(it):
                fit_error(f"узел {nid}: пункт {pos} — {len(it)} симв., влезает ~{fit_prefix(it, item_fits)}")
        if k == "terminal" and text:
            warnings.append(f"узел {nid}: у terminal текст не показывается, только заголовок")

    check_placement(cells, list(by_id), errors, "узел")
    er, ec = empty_lines(cells, grid_cols, grid_rows)
    if er:
        warnings.append(f"пустые ряды в grid: {er}")
    if ec:
        warnings.append(f"пустые столбцы в grid: {ec}")
    if lanes_mode:
        rows_of = {}
        for nid, (r, _) in cells.items():
            rows_of.setdefault(r, []).append(nid)
        for r, ids in sorted(rows_of.items()):
            if len(ids) > 1:
                warnings.append(f"swimlane, ряд {r}: узлы {ids} стоят в одном ряду, читается как одновременность; так задумано?")

    # edges
    edges = []
    for i, raw in enumerate(model.get("edges") or []):
        e = parse_edge(raw, errors, i)
        if e is None:
            continue
        a, b = e["a"], e["b"]
        tag = f"связь {a} -> {b}"
        if a not in by_id or b not in by_id:
            errors.append(f"{tag}: неизвестный узел")
            continue
        if a == b:
            errors.append(f"{tag}: связь узла с собой не рисуется")
            continue
        label = e["label"]
        note = None
        m = FOOT_RE.search(label)
        if m:
            note = int(m.group(1))
            label = label[: m.start()].strip()
            if note < 1 or note > len(footnotes):
                errors.append(f"{tag}: сноска [{note}] не описана в footnotes")
        if label and (len(label) > LABEL_MAX_CHARS or len(label.split()) > LABEL_MAX_WORDS):
            errors.append(f"{tag}: подпись {label!r} длиннее {LABEL_MAX_WORDS} слов или {LABEL_MAX_CHARS} символов; "
                          f"оставьте короткую и вынесите текст в footnotes со ссылкой [n]")
        edges.append({"a": a, "b": b, "label": label, "note": note, "dashed": e["dashed"]})

    outgoing, incoming = {}, {}
    for e in edges:
        outgoing.setdefault(e["a"], []).append(e)
        incoming.setdefault(e["b"], []).append(e)
    for nid, n in by_id.items():
        k = node_kind(n, kind)
        outs = outgoing.get(nid, [])
        if k == "decision":
            if len(outs) < 2:
                errors.append(f"развилка {nid}: исходящих связей {len(outs)}, нужно не меньше двух")
            for e in outs:
                if not e["label"]:
                    errors.append(f"развилка {nid}: ветка в {e['b']} без подписи")
        if kind in ("flow", "swimlane"):
            if k != "terminal" and not outs and k != "note":
                warnings.append(f"узел {nid}: нет исходящих связей, а это не terminal")
            if k != "note" and not incoming.get(nid) and k != "terminal" and cells.get(nid, (1,))[0] != 0:
                warnings.append(f"узел {nid}: нет входящих связей, недостижим")

    used_notes = {e["note"] for e in edges if e["note"]} | {n["_note"] for n in by_id.values() if n.get("_note")}
    for i in range(1, len(footnotes) + 1):
        if i not in used_notes:
            warnings.append(f"сноска [{i}] не используется")

    # routes (scenarios)
    routes = model.get("routes") or {}
    edge_set = {(e["a"], e["b"]) for e in edges}
    for name, seq in routes.items():
        if not isinstance(seq, list) or len(seq) < 2:
            errors.append(f"маршрут {name!r}: нужен список хотя бы из двух узлов")
            continue
        for a, b in zip(seq, seq[1:]):
            if a not in by_id or b not in by_id:
                errors.append(f"маршрут {name!r}: неизвестный узел {a if a not in by_id else b}")
            elif (a, b) not in edge_set:
                errors.append(f"маршрут {name!r}: между {a} и {b} нет связи")

    if errors:
        raise ModelError(errors + layout_errors, layout=layout_errors, fit=fit_errors)

    # routing
    lat = router.Lattice(grid_cols, grid_rows, {nid: rc for nid, rc in cells.items() if nid in by_id})
    ends = [(router.Lattice.point(*cells[e["a"]]), router.Lattice.point(*cells[e["b"]])) for e in edges]
    labelled = [bool(e["label"] or e["note"]) for e in edges]
    paths, routed = [], []
    for e, p in zip(edges, router.route_all(lat, ends, labelled)):
        if p is None:
            layout_errors.append(f"связь {e['a']} -> {e['b']}: нет маршрута, не проходящего сквозь узлы; "
                                 f"освободите ячейку между ними или переставьте узлы")
            continue
        paths.append(p)
        routed.append(e)
    if layout_errors and not draft:
        raise ModelError(layout_errors, layout=layout_errors, fit=fit_errors)
    if layout_errors:
        warnings = ["черновик: " + x for x in layout_errors] + warnings

    # every gutter and margin knows its room, so a group of lines too wide for the 8 px pitch
    # closes up to 6 or 5 rather than reaching over a card edge or out of the grid box
    top, bottom = margin_room(kind, mode_name, footnotes)
    geo = Geometry(mode, card_w, grid_cols, grid_rows, top, bottom)
    offsets = router.assign_offsets(paths, nodes=frozenset(lat.blocked), room=geo.room)
    occupied = {rc for nid, rc in cells.items() if nid in by_id}

    # where a label goes and how much room it has, from the shape of the route and the
    # pixels template/js/flow.js will use: straight line: at the exit; horizontal second segment: above
    # it, near its end; vertical second segment: beside its middle when that is clear whatever
    # the card heights, else pinned to the first row it passes where the text is clear
    label_keys = {}
    placed = []  # (first lattice row, last lattice row, x0, x1) of the labels placed so far
    for e in routed:
        e["lside"] = "R"
    # labels with a single place first, so that the ones choosing a row see them all
    order = sorted((i for i, e in enumerate(routed) if e["label"] or e["note"]),
                   key=lambda i: len(paths[i]) >= 3 and paths[i][2][1] != paths[i][1][1])
    for i in order:
        e, p = routed[i], paths[i]
        text = (e["label"] + (" " + CIRCLED[e["note"] - 1] if e["note"] else "")).strip()
        need = label_width(text)
        spots = label_spots(i, e, p, paths, offsets, geo, cells, occupied, card_w, placed)
        spot = next((s for s in spots if need <= s.get("line_room", s["room"])), None)
        if spot is None:
            spot = next((s for s in spots if need <= s["room"]), None)
            if spot is not None:
                warnings.append(f"связь {e['a']} -> {e['b']}: подпись {text!r} {spot['where']} ляжет на другую линию "
                                f"или подпись; переставьте узлы или уберите подпись в сноску")
        if spot is None:
            spot = max(spots, key=lambda s: s["room"])
            room = max(spot["room"], 0)
            def label_fits(s, room=room):
                return label_width(s) <= room
            fit_error(f"связь {e['a']} -> {e['b']}: подпись {text!r} {len(text)} симв. не помещается {spot['where']}, "
                      f"влезает ~{fit_prefix(text, label_fits)}; сократите, вынесите в сноску [n] "
                      f"или переставьте узлы так, чтобы линия уходила вниз")
        e["lside"] = spot.get("side", "R")
        if "ly" in spot:
            e["ly"] = spot["ly"]
        x0 = spot["start"] if spot["grow"] == "R" else spot["start"] - need
        placed.append((*spot["band"], x0, x0 + need))
        key = spot["key"]
        if key in label_keys:
            warnings.append(f"связи {label_keys[key]} и {e['a']} -> {e['b']}: подписи встанут в одно место и наложатся; "
                            f"переставьте узлы или уберите одну подпись в сноску")
        label_keys[key] = f"{e['a']} -> {e['b']}"

    # a label above a horizontal second segment collides with any other line crossing that segment
    segs = [router.segments(q) for q in paths]
    for i, (e, p) in enumerate(zip(routed, paths)):
        if not (e["label"] or e["note"]) or len(p) < 3 or p[2][1] != p[1][1]:
            continue
        y, x1, x2 = p[1][1], min(p[1][0], p[2][0]), max(p[1][0], p[2][0])
        for j, other in enumerate(segs):
            if j == i:
                continue
            for axis, line, lo, hi in other:
                if axis == "v" and x1 < line < x2 and lo < y < hi:
                    warnings.append(f"связь {e['a']} -> {e['b']}: подпись {e['label']!r} пересечёт линию "
                                    f"{routed[j]['a']} -> {routed[j]['b']}; переставьте узлы или уберите подпись в сноску")

    if layout_errors and not draft:
        raise ModelError(layout_errors, layout=layout_errors, fit=fit_errors)
    if layout_errors:
        warnings = ["черновик: " + x for x in layout_errors if x not in " ".join(warnings)] + warnings

    # what the reader sees, not what the lattice paths would cross: with the offsets assigned the
    # two are the same number, and where they are not the author is told about the drawing
    n_cross = router.drawn_crossings(paths, offsets, frozenset(lat.blocked))
    if n_cross >= 3:
        warnings.append(f"пересечений линий: {n_cross}; переставьте узлы, чтобы их стало меньше")
    out_edges = []
    for e, p, off in zip(routed, paths, offsets):
        out = {
            "a": e["a"], "b": e["b"],
            "sa": router.side_of(p[0], p[1]), "sb": router.side_of(p[-1], p[-2]),
            "path": [[x, y, ox, oy] for (x, y), (ox, oy) in zip(p, off)],
            "d": 1 if e["dashed"] else 0,
            "label": (e["label"] + (" " + CIRCLED[e["note"] - 1] if e["note"] else "")).strip(),
            "ls": e.get("lside", "R"),
        }
        if "ly" in e:
            out["ly"] = e["ly"]  # lattice row of a label beside a vertical second segment
        out_edges.append(out)

    layout = {"kind": kind, "edges": out_edges, "card_w": card_w, "grid_cols": grid_cols, "grid_rows": grid_rows,
              "cells": cells, "mode": mode, "nodes": by_id, "lanes": lanes, "lattice": lat, "paths": paths,
              "crossings": n_cross, "draft": bool(layout_errors), "routes": routes, "footnotes": footnotes}
    return layout, warnings


# ------------------------------------------------------------------- render


def node_html(n, layout, groups):
    kind = layout["kind"]
    k = node_kind(n, kind)
    r, c = layout["cells"][n["id"]]
    row_offset = 2 if kind == "swimlane" else 1
    gid = n.get("group") or (layout["lanes"][c] if kind == "swimlane" and c < len(layout["lanes"]) else None)
    ramp = f"r-{groups[gid]['ramp']}" if gid else "r-none"
    num = f'<span class="dg-num" data-n="{r + 1}"></span>' if kind == "swimlane" else ""
    attrs = f'data-t="{esc(n["id"])}" data-r="{r}" data-c="{c}" style="grid-row:{r + row_offset};grid-column:{c + 1}"'
    title = esc(n["title"])
    text = n.get("_text") or n.get("text") or ""
    if k == "terminal":
        return f'<div class="dg-c dg-node k-terminal {ramp}" {attrs}><div class="dg-pill">{num}<span>{title}</span></div></div>'
    if k == "note":
        body = title + (f"<br>{esc(text)}" if text else "")
        return f'<div class="dg-c dg-node k-note" {attrs}><div class="dg-t">{num}{body}</div></div>'
    marker = '<span class="dg-q" aria-label="развилка">?</span>' if k == "decision" else ""
    body = f'<div class="dg-t">{esc(text)}</div>' if text else ""
    if k == "state":
        stripe = f"s-{groups[gid]['ramp']}" if gid else ""
        return (f'<div class="dg-c dg-node k-state {stripe}" {attrs}><div class="dg-h r-none">{num}<span class="ttl">{title}</span></div>'
                f'{body}</div>')
    if k == "block":
        items = n.get("items") or []
        lst = ('<ul class="dg-items">' + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>") if items else ""
        return (f'<div class="dg-c dg-node k-block" {attrs}><div class="dg-h {ramp}">{num}<span class="ttl">{title}</span></div>'
                f'{body}{lst}</div>')
    return (f'<div class="dg-c dg-node k-{k}" {attrs}><div class="dg-h {ramp}">{num}<span class="ttl">{title}</span>{marker}</div>'
            f'{body}</div>')


def legend_html(model, layout, labels):
    items = []
    for gid, g in (model.get("groups") or {}).items():
        items.append(f'<span><span class="sw sw-{g["ramp"]}"></span>{esc(g.get("label", gid))}</span>')
    items.append('<span><svg width="34" height="10" viewBox="0 0 34 10"><path d="M1 5H27" stroke="currentColor" '
                 f'stroke-width="1.5" fill="none"/><path d="M27 2l5 3-5 3z" fill="currentColor"/></svg>{esc(labels["flow_solid"])}</span>')
    if any(e["d"] for e in layout["edges"]):
        items.append('<span><svg width="34" height="10" viewBox="0 0 34 10"><path d="M1 5H27" stroke="currentColor" '
                     f'stroke-width="1.5" stroke-dasharray="5 4" fill="none"/><path d="M27 2l5 3-5 3z" fill="currentColor"/></svg>{esc(labels["flow_dashed"])}</span>')
    if any(node_kind(n, layout["kind"]) == "decision" for n in layout["nodes"].values()):
        items.append(f'<span><span class="dg-q" style="vertical-align:-3px;margin-right:4px">?</span>{esc(labels["decision"])}</span>')
    return '<div class="dg-legend">' + "".join(items) + "</div>"


def render(model, mode_name, layout, warnings, assets_mode="inline", draft=False):
    kind, mode = layout["kind"], layout["mode"]
    labels = labels_for(model)
    groups = model.get("groups") or {}
    style_vars = (f"--dg-cols:{layout['grid_cols']};--dg-w:{layout['card_w']:.0f}px;--dg-gap:{mode['gap']}px;"
                  f"--dg-rowgap:{mode['row_gap']}px;--dg-padl:{mode['pad_l']}px;--dg-padr:{mode['pad_r']}px")
    summary = model.get("summary") or model.get("title") or "Схема"
    labels_js = esc(json.dumps({}, ensure_ascii=False))

    before, after = assets.asset_blocks(assets_mode, mode_name, kind, {g["ramp"] for g in groups.values()},
                                        layout["edges"], layout["routes"], layout["footnotes"])
    parts = [before] if before else []
    parts.append(assets.section_open(model, kind, style_vars, labels_js, summary))
    if mode_name == "page" and model.get("title"):
        parts.append(f'<h3 style="margin:0 0 4px {mode["pad_l"]}px;font-size:16px;font-weight:500">{esc(model["title"])}</h3>')
    if draft or layout.get("draft"):
        parts.append(f'<span class="dg-draft">{esc(labels["draft"])}</span>')
    routes = layout["routes"]
    if routes:
        chips = "".join(f'<button type="button" class="dg-route" data-nodes="{esc(" ".join(seq))}">{esc(name)}</button>'
                        for name, seq in routes.items())
        parts.append(f'<div class="dg-routes"><span class="dg-routes-l">{esc(labels["routes"])}</span>{chips}</div>')
    parts.append('<div class="dg-grid">')
    if kind == "swimlane":
        span = layout["grid_rows"] + 1
        for c, gid in enumerate(layout["lanes"]):
            g = groups[gid]
            parts.append(f'<div class="dg-lane r-{g["ramp"]}" style="grid-row:1 / span {span};grid-column:{c + 1}"></div>')
            parts.append(f'<div class="dg-lanehead r-{g["ramp"]}" style="grid-row:1;grid-column:{c + 1}">{esc(g.get("label", gid))}</div>')
    for n in model["nodes"]:
        parts.append(node_html(n, layout, groups))
    parts.append('<svg class="dg-svg" aria-hidden="true"></svg></div>')
    if layout["footnotes"]:
        parts.append('<ol class="dg-foot">' + "".join(f"<li>{f}</li>" for f in layout["footnotes"]) + "</ol>")
    parts.append(legend_html(model, layout, labels))
    parts.append(assets.edges_json(layout["edges"]))
    parts.append("</section>")
    if after:
        parts.append(after)
    return "\n".join(parts)


def ascii(model, layout):
    ids_at = {rc: nid for nid, rc in layout["cells"].items()}
    text = router.ascii(layout["lattice"], ids_at, layout["paths"])
    lines = [text, ""]
    for e in layout["edges"]:
        lines.append(f"  {e['a']} -> {e['b']}" + (f"  : {e['label']}" if e["label"] else "") + ("  (пунктир)" if e["d"] else ""))
    lines.append(f"  пересечений линий: {layout['crossings']}")
    return "\n".join(lines)


def mermaid(model, layout):
    kind = layout["kind"]
    groups = model.get("groups") or {}

    def mid(nid):
        return nid.replace("?", "_q")

    def shape(n):
        k = node_kind(n, kind)
        t = n["title"].replace('"', "'")
        if k == "decision":
            return f'{mid(n["id"])}{{"{t}"}}'
        if k == "terminal":
            return f'{mid(n["id"])}(["{t}"])'
        if k == "note":
            return f'{mid(n["id"])}[/"{t}"/]'
        if k == "state":
            return f'{mid(n["id"])}(["{t}"])'
        return f'{mid(n["id"])}["{t}"]'

    lines = ["flowchart TD" if kind != "state" else "flowchart LR"]
    if kind == "swimlane":
        for c, gid in enumerate(layout["lanes"]):
            lines.append(f'    subgraph {gid} ["{groups[gid].get("label", gid)}"]')
            for n in model["nodes"]:
                if layout["cells"][n["id"]][1] == c:
                    lines.append("        " + shape(n))
            lines.append("    end")
    else:
        for n in model["nodes"]:
            lines.append("    " + shape(n))
    for e in layout["edges"]:
        arrow = "-.->" if e["d"] else "-->"
        label = f'|"{e["label"]}"|' if e["label"] else ""
        lines.append(f"    {mid(e['a'])} {arrow}{label} {mid(e['b'])}")
    for i, f in enumerate(layout["footnotes"], 1):
        lines.append(f"    %% {CIRCLED[i - 1]} {f}")
    return "\n".join(lines)
