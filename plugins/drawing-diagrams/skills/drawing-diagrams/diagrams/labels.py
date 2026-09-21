"""Where a label may stand, as rectangles of one lattice row.

Every drawn object is one or more rectangles `(Y, y0, y1, x0, x1, kind, owner)`: `Y` a lattice row,
`y` in px from the base of that row as `base()` of template/js/flow.js computes it, `x` in px across
from the grid box as `Geometry` computes it. Card heights are unknown in Python, so the model keeps
that uncertainty instead of guessing: a card is the whole of its row, a vertical run is the whole of
every row it passes and half of the rows it ends in, and a text whose place depends on a height
covers every row it can fall in. One predicate — `overlaps` — tests two rectangles of one row, and
`room` measures the px a text has from its near edge outwards to the nearest of them.

What diagrams/flow.py used to do with `half`, `reach`, `horizontal` and a pass after the label loop
are values of `y0`, `y1` here (spec 7.1).

Two of those values carry an uncertainty this side cannot resolve, and both sit on the text rather
than on the line, because a clamped line and a text drawn from a point of the same clamped band move
together and only their order survives:

- Beside a vertical second segment the text stands on the base of a row (the anchor's `r`
  reference), while template/js/flow.js clamps every line of a row where a line enters or leaves a
  card sideways into the band of those cards. A line of such a row is drawn nearer the base than
  its offset says, by an amount that depends on card heights, so the text covers the whole of that
  row there.
- At a straight sideways exit the text stands `LABEL_SIDE` px beside the card edge and `LABEL_LIFT`
  px above its own line, both clamped with that line: the text is modelled as everything above the
  top edge of its own line, which is the order the clamp preserves.

A candidate that hangs from its own source card — a straight exit down — is not tested against that
card, which it lies below by construction, nor against the lines that leave or enter the card within
its height; it is tested against the other cards of the row and the lines drawn at their height
(spec 7.1). Those exceptions are the candidate's `exempt`, by row and owner.

`place` is what `flow.plan` asks; `today` is the only source of places it has at this commit, and
`greedy` the only choice — the new candidates of spec 7.2 and the search of spec 7.3 come after it.
What the module never holds is a message: a `Choice` names the place and what stands in the label's
way there, and diagrams/flow.py writes the warning about it.
"""
import collections
import math

from . import router
from .common import label_width

INF = math.inf

# Where a label stands, in px. The numbers live here, beside the model that reads them, in one copy:
# they go to the script as the `la` anchor of the edge that carries the label, and diagrams/flow.py
# imports the names it used to define.
LABEL_BEND = 6    # from a bend: beside a vertical second segment, before the end of a horizontal one
LABEL_SIDE = 3    # from the card edge at a straight sideways exit
LABEL_LIFT = 5    # from the line up to the baseline at a straight sideways exit
LABEL_BESIDE = 5  # from the line at a straight exit down or up
LABEL_BELOW = 14  # from the card's bottom edge to the baseline at a straight exit down
LABEL_ABOVE = 6   # from the baseline to the card's top edge at a straight exit up
LABEL_OVER = 9    # from the row line up to the baseline over a horizontal second segment
LABEL_DROP = 4    # from the middle of the text down to its baseline
LABEL_CLEAR = 2   # the text box keeps this far from a card edge or a line
LINE_REACH = 7.5  # a horizontal line nearer than this to the middle of the text runs through it
LABEL_WORD = 8    # two labels in one row keep this much more apart, or they read as one phrase

# Half the height of the text box, in px. A line is drawn 2 px wide, so a line whose centre is
# nearer than LINE_REACH to the middle of the text is exactly one whose box meets this one.
TEXT_HALF = LINE_REACH - 1

CARD, LINE, LABEL, BOUND = "CARD", "LINE", "LABEL", "BOUND"

# The shapes of place, as a message names them. `where` is also what tells the families apart: a
# label over a horizontal second segment is measured against no line until it stands somewhere, and
# only one beside a vertical second segment is measured against the labels already placed. A new
# place of spec 7.2 joins the family it belongs to and takes its `where` with it.
DOWN, UP, SIDEWAYS = "у выхода вниз", "у выхода вверх", "у выхода вбок"
OVER, BESIDE = "над вторым отрезком", "рядом со вторым отрезком"

# What a text keeps clear of each kind, in px across. A bound is the edge of the drawn area itself,
# which the text may touch; another label keeps LABEL_WORD more, or the two read as one phrase.
CLEARANCE = {CARD: LABEL_CLEAR, LINE: LABEL_CLEAR, LABEL: LABEL_CLEAR + LABEL_WORD, BOUND: 0}

Rect = collections.namedtuple("Rect", "Y y0 y1 x0 x1 kind owner")

# One place a label may take: `rects` is its text, one rectangle per lattice row it can fall in;
# `rank` its preference, 0 first; `start` the near edge of the text and `grow` the direction it runs
# from there ("R" rightwards, "L" leftwards); `limit` the most room the place can offer whatever
# stands around it; `key` names the place, so two labels taking the same one are told about;
# `exempt` the (row, owner) pairs this place is not tested against; `la` the anchor `flow.plan` emits
# for it, `(pt, ref, Y, dx, dy, anchor)` as spec 7.4 defines it, which is the whole of what the
# script needs to draw the text where this rectangle stands.
Candidate = collections.namedtuple("Candidate", "where rank rects start grow limit key exempt la")

# What a plan has to say about one label, and who raised it: ON_LINE that the text lies on a line or
# on another label, CROSSED that a line runs through a text standing over a horizontal second
# segment, SAME_PLACE that another label took this very place first. `owner` names it — the
# rectangle's owner, the path the line belongs to, the edge that came first. A label raises one
# ON_LINE, one CROSSED per line and one SAME_PLACE, which is what it raises today: the advice of
# spec 6 counts the warnings of a plan, so their number is part of the contract (spec 7.3).
ON_LINE, CROSSED, SAME_PLACE = "ON_LINE", "CROSSED", "SAME_PLACE"

Clash = collections.namedtuple("Clash", "kind owner")

# Where one label stands: `edge` the routed edge it belongs to, `cand` the place it took, `clashes`
# the warnings that place raises, and `room` the px the roomiest place offered when the text fits
# none of them at all — None when it fits one.
Choice = collections.namedtuple("Choice", "edge cand clashes room")


def banded_rows(paths):
    """The lattice rows template/js/flow.js clamps into a band: a row of cards where a line enters
    or leaves a card sideways. A path's ends are its cards' points, so an end segment that runs
    along the row is one such line. Every point of the row is then drawn 10 px inside the lowest top
    and the highest bottom of those cards, which this side, knowing no height, can only read as the
    whole row."""
    out = set()
    for q in paths:
        if q[0][1] == q[1][1]:
            out.add(q[0][1])
        if q[-1][1] == q[-2][1]:
            out.add(q[-1][1])
    return frozenset(out)


def occupancy(cells, paths, offsets, geo, occupied):
    """Every drawn object as rectangles: the cards on `occupied` cells, named by the node standing
    there; the runs of every path, named by (path index, segment index); and the bounds the drawn
    area ends at — the left edge of the grid box and `Geometry.total` across.

    A card is the whole of its row: its height is unknown here, and cards align to the top of the
    row, so nothing below its bottom edge can be told from inside it. A vertical run covers the
    whole of every row it passes through and half of a row it ends in — the half it comes from. A
    horizontal run is its offset either way of the base, as wide as it is drawn."""
    named = {}
    for nid, rc in cells.items():
        if rc in occupied:
            named.setdefault(rc, nid)
    out = [Rect(2 * r + 1, -INF, INF, geo.left(c), geo.right(c), CARD, named.get((r, c), (r, c)))
           for r, c in sorted(occupied)]
    for j, (q, off) in enumerate(zip(paths, offsets)):
        for k in range(len(q) - 1):
            (x1, y1), (x2, y2) = q[k], q[k + 1]
            if x1 == x2:
                x = geo.x(x1) + off[k][0]
                lo, hi = min(y1, y2), max(y1, y2)
                for Y in range(lo, hi + 1):
                    out.append(Rect(Y, -INF if Y > lo else 0.0, INF if Y < hi else 0.0,
                                    x - 1, x + 1, LINE, (j, k)))
            else:
                xa, xb = geo.x(x1) + off[k][0], geo.x(x2) + off[k + 1][0]
                out.append(Rect(y1, off[k][1] - 1, off[k][1] + 1,
                                min(xa, xb), max(xa, xb), LINE, (j, k)))
    for Y in range(2 * geo.rows + 1):
        out.append(Rect(Y, -INF, INF, -INF, 0.0, BOUND, "left"))
        out.append(Rect(Y, -INF, INF, geo.total, INF, BOUND, "right"))
    return out


def overlaps(a, b, cx=0, cy=0):
    """Whether two rectangles of one lattice row meet, keeping `cx` px across and `cy` px down. The
    comparison is open: two rectangles that touch along an edge do not meet."""
    return (a.Y == b.Y
            and a.x0 - cx < b.x1 and b.x0 - cx < a.x1
            and a.y0 - cy < b.y1 and b.y0 - cy < a.y1)


def room(cand, rects):
    """The px a candidate's text has from its near edge outwards, at most its own `limit`: to the
    nearest of `rects` that shares a row with it, meets it down the row and is not exempt, less what
    that kind keeps clear. Negative when one of them already covers the near edge.

    The caller says which rectangles count — `flow.plan` measures a place against the cards alone
    before measuring it against the lines as well — and the y of the two rectangles decides the
    rest."""
    mine = {rect.Y: rect for rect in cand.rects}
    out = cand.limit
    for rect in rects:
        own = mine.get(rect.Y)
        if own is None or (rect.Y, rect.owner) in cand.exempt:
            continue
        if not (own.y0 < rect.y1 and rect.y0 < own.y1):
            continue
        clear = CLEARANCE[rect.kind]
        if cand.grow == "R":
            if rect.x1 > cand.start - clear:
                out = min(out, rect.x0 - cand.start - clear)
        elif rect.x0 < cand.start + clear:
            out = min(out, cand.start - rect.x1 - clear)
    return out


def _text(Y, y0, y1, start, grow, need, owner):
    """The text of one candidate in one lattice row, `need` px wide from `start` outwards."""
    x0 = start if grow == "R" else start - need
    return Rect(Y, y0, y1, x0, x0 + need, LABEL, owner)


def _at_card(node, paths):
    """The runs drawn within the height of the card at lattice point `node`: one that leaves or
    enters it along its row, and a vertical that comes down to the row and turns into it. A label
    hanging under that card stands below all of them, and under_card of diagrams/flow.py leaves them
    out for the same reason."""
    out = set()
    for j, q in enumerate(paths):
        for k in range(len(q) - 1):
            (x1, y1), (x2, y2) = q[k], q[k + 1]
            if y1 == y2 == node[1] and node in (q[k], q[k + 1]):
                out.add((j, k))
            elif x1 == x2 and min(y1, y2) < max(y1, y2) == node[1]:
                # where it goes on along the row; it ends on a card's top edge when it goes nowhere
                on = k + 2 if y2 == node[1] else k - 1
                if not (0 <= on < len(q)) or q[on] == node:
                    out.add((j, k))
    return out


def _beside(Y, pin, lo, hi, bend, banded):
    """The y of a text beside a vertical second segment, in row Y.

    Pinned to a row, and in the rows the middle of the segment can fall in, the text stands on the
    base of the row: it covers the base either way of it, or the whole row where the clamp of a
    banded row moves the lines of that row by an unknown amount. In a row the segment ends in, the
    middle of the text stays beyond the bend drawn there — half a row of the lattice away from it —
    so it covers the row past that line and no more. `flow.band_obstacles` reads such a row the
    other way round: every line that crosses it counts, wherever it stops, and every line that runs
    along it is left out, wherever it runs. That is the one reading the two differ in."""
    if pin is None and Y in bend and Y in (lo, hi):
        return (bend[Y] + 1, INF) if Y == lo else (-INF, bend[Y] - 1)
    return (-INF, INF) if Y in banded else (-TEXT_HALF, TEXT_HALF)


def today(i, e, p, need, paths, offsets, geo, cells, occupied, card_w):
    """Exactly the places `flow.label_spots` offers the label of routed edge `i` today, in today's
    order of preference, as candidates of this model. `need` is the width of the text in px.

    Only a label beside a vertical second segment has a choice — its row and its side; every other
    shape of route has one place."""
    off = offsets[i]
    r, c = cells[e["a"]]
    tc = cells[e["b"]][1]
    sa = router.side_of(p[0], p[1])
    banded = banded_rows(paths)
    if len(p) >= 3 and p[2][1] == p[1][1]:
        # over the horizontal second segment, ending LABEL_BEND before its far end: the cells under
        # the segment are empty, so the only limit across is the line's own bend at p1. The text
        # stands LABEL_OVER above the row line, clear of its own segment, and a line crossing the
        # segment there runs through it
        x1 = geo.clamp(c, geo.x(p[1][0]) + off[1][0])
        if len(p) == 3:
            x2 = geo.left(tc) if p[2][0] > p[1][0] else geo.right(tc)
        else:
            x2 = geo.x(p[2][0]) + off[2][0]
            if len(p) == 4:
                x2 = geo.clamp(tc, x2)
        rt = x2 > x1
        start, grow = (x2 - LABEL_BEND, "L") if rt else (x2 + LABEL_BEND, "R")
        Y, mid = p[1][1], -(LABEL_OVER + LABEL_DROP)
        return [Candidate(OVER, 0,
                          (_text(Y, mid - TEXT_HALF, mid + TEXT_HALF, start, grow, need, i),),
                          start, grow, abs(x2 - x1) - LABEL_BEND - LABEL_CLEAR,
                          ("h", Y, p[2][0], p[2][0] > p[1][0]),
                          frozenset((Y, (i, k)) for k in range(len(p) - 1)),
                          (2, "r", Y, -LABEL_BEND if rt else LABEL_BEND, -LABEL_OVER,
                           "end" if rt else "start"))]
    if len(p) >= 3:
        # beside the vertical second segment. Anchored to the middle of the segment the script draws
        # the text at a pixel row that depends on card heights: that place is kept when the side is
        # clear in every row the middle can fall in. Otherwise the text is anchored to the base of
        # one row the segment passes, gutters included: the middle first, the rows of its ends last
        X, Y1, Y2 = p[1][0], p[1][1], p[2][1]
        x = geo.x(X) + off[1][0]
        if len(p) == 3:
            x = geo.clamp(tc, x)
        lo, hi = min(Y1, Y2), max(Y1, Y2)
        mid = (Y1 + Y2) / 2
        # the middle stays at least half a row off the ends: clear of the lines turning there and of
        # the target card the segment ends on, not of the cards beside the line at its start
        middle = [Y for Y in range(lo, hi + 1) if not (len(p) == 3 and Y == Y2)]
        pinned = sorted(range(lo, hi + 1), key=lambda Y: (Y in (Y1, Y2), abs(Y - mid), abs(Y - Y1)))
        bend = {Y1: off[1][1]}
        if len(p) >= 4:
            bend[Y2] = off[2][1]
        exempt = frozenset((Y, (i, 1)) for Y in range(lo, hi + 1))
        out, rank = [], 0
        for pin, rows in [(None, middle)] + [(Y, [Y]) for Y in pinned]:
            blo, bhi = (lo, hi) if pin is None else (pin, pin)
            for side in ("R", "L"):
                if (side == "R" and X == 2 * geo.cols) or (side == "L" and X == 0):
                    continue  # outside the grid box the section clips the text
                start = x + LABEL_BEND if side == "R" else x - LABEL_BEND
                rects = tuple(_text(Y, *_beside(Y, pin, lo, hi, bend, banded), start, side, need, i)
                              for Y in rows)
                la = (1, "m" if pin is None else "r", 0 if pin is None else pin,
                      LABEL_BEND if side == "R" else -LABEL_BEND, LABEL_DROP,
                      "start" if side == "R" else "end")
                out.append(Candidate(BESIDE, rank, rects, start, side,
                                     card_w - 20, ("v", X, blo, bhi, side), exempt, la))
                rank += 1
        return out
    if sa in ("L", "R"):
        # straight sideways: from the card edge towards the next card in the row, which is the
        # target, above the label's own line
        Y = p[0][1]
        start = geo.right(c) + LABEL_SIDE if sa == "R" else geo.left(c) - LABEL_SIDE
        return [Candidate(SIDEWAYS, 0,
                          (_text(Y, -INF, off[0][1] - 1, start, sa, need, i),),
                          start, sa, geo.gap + card_w - 20, (e["a"], sa),
                          frozenset({(Y, (i, 0)), (Y, e["a"])}),
                          (0, "p", 0, LABEL_SIDE if sa == "R" else -LABEL_SIDE, -LABEL_LIFT,
                           "start" if sa == "R" else "end"))]
    # straight down or up: the text stands in the gutter under or over the card, between the card
    # and the middle of the gutter, where lines run. Under a card shorter than its row it stands
    # higher, never lower, so when the row holds other cards it may stand in the row as well
    Y, up = (p[0][1] + 1, False) if sa == "B" else (p[0][1] - 1, True)
    middle = LABEL_ABOVE + LABEL_DROP if up else LABEL_BELOW - LABEL_DROP  # off the card edge
    mid = geo.row_gap / 2 - middle if up else middle - geo.row_gap / 2     # off the base of the row
    start = geo.clamp(c, geo.x(p[1][0]) + off[1][0]) + LABEL_BESIDE
    y0, y1 = (mid - TEXT_HALF, INF) if up else (-INF, mid + TEXT_HALF)
    rects = [_text(Y, y0, y1, start, "R", need, i)]
    exempt = {(Y, (i, 0))}
    if not up and any(rr == r and cc != c for rr, cc in occupied):
        R = p[0][1]
        rects.append(_text(R, -INF, INF, start, "R", need, i))
        exempt |= {(R, e["a"])} | {(R, owner) for owner in _at_card(p[0], paths)}
    return [Candidate(UP if up else DOWN, 0, tuple(rects), start, "R",
                      card_w, (e["a"], sa), frozenset(exempt),
                      (0, "p", 0, LABEL_BESIDE, -LABEL_ABOVE if up else LABEL_BELOW, "start"))]


def uprights(paths):
    """The vertical runs, by (path, segment): the ones that can run through a text standing over a
    horizontal second segment. A run along that row is the segment the text hangs from, or another
    one in the same band, and neither is what the check of spec 7.1 looks for."""
    return frozenset((j, k) for j, q in enumerate(paths) for k in range(len(q) - 1)
                     if q[k][0] == q[k + 1][0])


def met(cand, rects):
    """The owner of the nearest of `rects` the candidate's text runs into — what a label that does
    not stand clear lies on — or None when it stands clear of all of them. Nearest is measured from
    the text's near edge outwards, as `room` measures it and without its limit: the limit is the
    place's own reach and names nothing."""
    plain = cand._replace(limit=INF)
    near = None
    for rect in rects:
        if (rect.Y, rect.owner) in cand.exempt:
            continue
        if not any(overlaps(text, rect, CLEARANCE[rect.kind], 0) for text in cand.rects):
            continue
        at = room(plain, [rect])
        if near is None or at < near[0]:
            near = (at, rect.owner)
    return None if near is None else near[1]


def greedy(order, cands, needs, cards, runs, upright):
    """The labels of `order` in that order, each taking the first of its candidates with room for
    its text: today's choice, over whatever candidates it is given.

    Room is measured three ways, as the places of spec 7.2 fall into three families. Every place is
    measured against the cards and the bounds, which a text may never stand on. Every place but one
    over a horizontal second segment is measured against the lines as well, and a text that has to
    lie on one is told about; over a horizontal second segment the lines are looked for once the
    text stands somewhere, because what counts there is the ones that run through the text itself.
    Beside a vertical second segment the labels already placed count too — that is the one place
    with a row to choose, so it is the one that can choose another.

    Failing all of them the roomiest place is taken with the room it offered, which is the fit
    error. `cards` and `runs` are the rectangles of `occupancy` split by kind, `needs` the width of
    each text in px, and `upright` the runs of `uprights`."""
    out, keys, placed = [], {}, []
    for i in order:
        cs, need = cands[i], needs[i]
        wide = [room(c, cards) for c in cs]
        tight = [w if c.where == OVER else
                 min(w, room(c, runs + (placed if c.where == BESIDE else [])))
                 for c, w in zip(cs, wide)]
        clashes, short = [], None
        spot = next((c for c, t in zip(cs, tight) if need <= t), None)
        if spot is None:
            spot = next((c for c, w in zip(cs, wide) if need <= w), None)
            if spot is not None:
                on = met(spot, runs + (placed if spot.where == BESIDE else []))
                clashes.append(Clash(ON_LINE, on))
        if spot is None:
            at = max(range(len(cs)), key=lambda k: wide[k])
            spot, short = cs[at], max(wide[at], 0)
        placed += list(spot.rects)
        if spot.key in keys:
            clashes.append(Clash(SAME_PLACE, keys[spot.key]))
        keys[spot.key] = i
        if spot.where == OVER:
            clashes += [Clash(CROSSED, run.owner[0]) for run in runs
                        if run.owner in upright and (run.Y, run.owner) not in spot.exempt
                        and any(overlaps(text, run) for text in spot.rects)]
        out.append(Choice(i, spot, tuple(clashes), short))
    return out


def place(edges, texts, paths, offsets, geo, cells, occupied, card_w):
    """Where the label of every routed edge that carries one goes: a Choice per label, in the order
    they were placed — the labels with a single place first, so that the ones with a row to choose
    see them all. `texts` is the drawn text of each edge, empty where the edge carries none.

    At this commit the places are `today`'s and the choice is `greedy`'s."""
    rects = occupancy(cells, paths, offsets, geo, occupied)
    cards = [r for r in rects if r.kind in (CARD, BOUND)]
    runs = [r for r in rects if r.kind == LINE]
    order = sorted((i for i, text in enumerate(texts) if text),
                   key=lambda i: len(paths[i]) >= 3 and paths[i][2][1] != paths[i][1][1])
    needs = {i: label_width(texts[i]) for i in order}
    cands = {i: today(i, edges[i], paths[i], needs[i], paths, offsets, geo, cells, occupied, card_w)
             for i in order}
    return greedy(order, cands, needs, cards, runs, uprights(paths))
