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

A place over or under a horizontal second segment is the one whose rectangle is read from its own
line rather than from the base of the row: the text is anchored to the drawn `y` of a point of that
segment, so a segment drawn away from the base takes its label with it (spec 7.2 as amended). Every
other place keeps the reference it had.

`place` is what `flow.plan` asks; `candidates` is the source of places it has, the table of spec 7.2
whole, and `greedy` the only choice — the search of spec 7.3 comes after it. What the module never
holds is a message: a `Choice` names the place, what stands in the label's way there, and what stood
nearest when no place had the room, and diagrams/flow.py writes the message about it.
"""
import collections
import math

from . import router
from .common import label_width

INF = math.inf

# Where a label stands, in px. The numbers live here, beside the model that reads them, in one copy:
# they go to the script as the `la` anchor of the edge that carries the label, and diagrams/flow.py
# imports the names it used to define.
LABEL_BEND = 6    # from a bend: beside a vertical second segment, either end of a horizontal one
LABEL_SIDE = 3    # from the card edge at a straight sideways exit
LABEL_LIFT = 5    # from the line up to the baseline at a straight sideways exit
LABEL_SINK = 13   # from the line down to the baseline at a straight sideways exit
LABEL_BESIDE = 5  # from the line at a straight exit down or up
LABEL_BELOW = 14  # from the card's bottom edge to the baseline at a straight exit down
LABEL_ABOVE = 6   # from the baseline to the card's top edge at a straight exit up
LABEL_OVER = 9    # from a horizontal second segment up to the baseline over it
LABEL_UNDER = 17  # from a horizontal second segment down to the baseline under it
LABEL_DROP = 4    # from the middle of the text down to its baseline
LABEL_CLEAR = 2   # the text box keeps this far from a card edge or a line
LINE_REACH = 7.5  # a horizontal line nearer than this to the middle of the text runs through it
LABEL_WORD = 8    # two labels in one row keep this much more apart, or they read as one phrase

# A text under a line stands as far under it as the one over it stands over it: the box is
# TEXT_HALF either way of its middle and LABEL_DROP over its baseline, so a baseline `lift` px over
# a line has its box as near that line as a baseline `lift + 2 * LABEL_DROP` px under it. That is
# LABEL_SINK against LABEL_LIFT and LABEL_UNDER against LABEL_OVER, and it is why a place below a
# line needs vertical offsets of its own rather than the ones above it.

# Half the height of the text box, in px. A line is drawn 2 px wide, so a line whose centre is
# nearer than LINE_REACH to the middle of the text is exactly one whose box meets this one.
TEXT_HALF = LINE_REACH - 1

CARD, LINE, LABEL, BOUND = "CARD", "LINE", "LABEL", "BOUND"

# The shapes of place, as a message names them. `where` is also what tells the families apart: a
# label over or under a horizontal second segment is measured against no line until it stands
# somewhere, and only one beside a vertical second segment is measured against the labels already
# placed. A place of spec 7.2 joins the family it belongs to and takes its `where` with it — the
# side of a line a place stands on is not in the wording, except where calling a place below a line
# "над" would be false.
DOWN, UP, SIDEWAYS = "у выхода вниз", "у выхода вверх", "у выхода вбок"
OVER, BENEATH = "над вторым отрезком", "под вторым отрезком"
BESIDE = "рядом со вторым отрезком"

# The family of places on a horizontal second segment: over it and under it (spec 7.3 as amended).
SECOND_RUN = frozenset({OVER, BENEATH})

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
# the warnings that place raises, `room` the px the roomiest place offered when the text fits none
# of them at all — None when it fits one — and `blocked`, the nearest thing in the way there as a
# Clash of its kind and its owner, which the error names beside the room (criterion E3).
Choice = collections.namedtuple("Choice", "edge cand clashes room blocked")


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


def _on_segment(i, p, off, x1, x2, need):
    """The three places on a horizontal second segment, preferred first (spec 7.2): over it just
    after the bend, under it just after the bend, over it at its far end. `x1` is the px x of the
    bend the segment starts at, `x2` of the end it runs to.

    "Just after the bend" starts the text LABEL_BEND past the bend and grows away from the source;
    the far end grows back towards it. Either way the text may reach neither end of the segment, so
    all three have the segment's own length less that bend and a clearance for their limit.

    Down the row every one of them is read from the segment as it is drawn — `off[1][1]`, the y its
    own line is spread to — and not from the base of the row (spec 7.2 as amended): the anchor takes
    the drawn y of the point it hangs from, so the text moves with the line it belongs to, and a
    segment drawn far from the base no longer runs through its own label."""
    Y, seg, rt = p[1][1], off[1][1], x2 > x1
    # the cells under the segment are empty, so the only limit across is the far end of the segment
    limit = abs(x2 - x1) - LABEL_BEND - LABEL_CLEAR
    exempt = frozenset((Y, (i, k)) for k in range(len(p) - 1))
    out = []
    for rank, (where, pt, x, back) in enumerate(((OVER, 1, x1, False), (BENEATH, 1, x1, False),
                                                 (OVER, 2, x2, True))):
        away = rt != back  # whether the text grows rightwards from the end it hangs from
        start = x + LABEL_BEND if away else x - LABEL_BEND
        up = where == OVER
        dy = -LABEL_OVER if up else LABEL_UNDER   # from the segment to the baseline
        mid = seg + dy - LABEL_DROP               # and on to the middle of the text
        out.append(Candidate(where, rank,
                             (_text(Y, mid - TEXT_HALF, mid + TEXT_HALF, start,
                                    "R" if away else "L", need, i),),
                             start, "R" if away else "L", limit,
                             # the place a second label would have to take to land on this text:
                             # the end it hangs from and the way it grows, and the segment's own
                             # offset with them, since that is what the text is drawn from now
                             ("h", Y, seg, p[pt][0], p[2][0] > p[1][0], up), exempt,
                             (pt, "p", 0, LABEL_BEND if away else -LABEL_BEND, dy,
                              "start" if away else "end")))
    return out


def candidates(i, e, p, need, paths, offsets, geo, cells, occupied, card_w):
    """Where the label of routed edge `i` may stand, preferred first, as the table of spec 7.2 has
    them. `need` is the width of the text in px.

    A straight exit down or up is offered the right of its line and then the left; a straight
    sideways exit the room above its line and then the room below; a horizontal second segment the
    three places of `_on_segment`; a vertical one its middle and then the rows it passes, on either
    side of the line each time."""
    off = offsets[i]
    r, c = cells[e["a"]]
    tc = cells[e["b"]][1]
    sa = router.side_of(p[0], p[1])
    banded = banded_rows(paths)
    if len(p) >= 3 and p[2][1] == p[1][1]:
        x1 = geo.clamp(c, geo.x(p[1][0]) + off[1][0])
        if len(p) == 3:
            x2 = geo.left(tc) if p[2][0] > p[1][0] else geo.right(tc)
        else:
            x2 = geo.x(p[2][0]) + off[2][0]
            if len(p) == 4:
                x2 = geo.clamp(tc, x2)
        return _on_segment(i, p, off, x1, x2, need)
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
        # target, above the label's own line and then below it. The text is clamped with that line,
        # so above it covers everything over the line's top edge and below it everything under the
        # bottom edge — the order is all the clamp of a banded row leaves of the two
        Y = p[0][1]
        start = geo.right(c) + LABEL_SIDE if sa == "R" else geo.left(c) - LABEL_SIDE
        exempt = frozenset({(Y, (i, 0)), (Y, e["a"])})
        dx = LABEL_SIDE if sa == "R" else -LABEL_SIDE
        anchor = "start" if sa == "R" else "end"
        return [Candidate(SIDEWAYS, rank,
                          (_text(Y, *rows, start, sa, need, i),),
                          start, sa, geo.gap + card_w - 20, (e["a"], sa, up), exempt,
                          (0, "p", 0, dx, -LABEL_LIFT if up else LABEL_SINK, anchor))
                for rank, (up, rows) in enumerate(((True, (-INF, off[0][1] - 1)),
                                                   (False, (off[0][1] + 1, INF))))]
    # straight down or up: the text stands in the gutter under or over the card, between the card
    # and the middle of the gutter, where lines run, on the right of its own line and then on the
    # left. Under a card shorter than its row it stands higher, never lower, so when the row holds
    # other cards it may stand in the row as well
    Y, up = (p[0][1] + 1, False) if sa == "B" else (p[0][1] - 1, True)
    middle = LABEL_ABOVE + LABEL_DROP if up else LABEL_BELOW - LABEL_DROP  # off the card edge
    mid = geo.row_gap / 2 - middle if up else middle - geo.row_gap / 2     # off the base of the row
    x = geo.clamp(c, geo.x(p[1][0]) + off[1][0])
    y0, y1 = (mid - TEXT_HALF, INF) if up else (-INF, mid + TEXT_HALF)
    in_row = not up and any(rr == r and cc != c for rr, cc in occupied)
    out = []
    for rank, side in enumerate(("R", "L")):
        start = x + LABEL_BESIDE if side == "R" else x - LABEL_BESIDE
        rects = [_text(Y, y0, y1, start, side, need, i)]
        exempt = {(Y, (i, 0))}
        if in_row:
            R = p[0][1]
            rects.append(_text(R, -INF, INF, start, side, need, i))
            exempt |= {(R, e["a"])} | {(R, owner) for owner in _at_card(p[0], paths)}
        out.append(Candidate(UP if up else DOWN, rank, tuple(rects), start, side,
                             card_w, (e["a"], sa, side), frozenset(exempt),
                             (0, "p", 0, LABEL_BESIDE if side == "R" else -LABEL_BESIDE,
                              -LABEL_ABOVE if up else LABEL_BELOW,
                              "start" if side == "R" else "end")))
    return out


def uprights(paths):
    """The vertical runs, by (path, segment): the ones that can run through a text standing over a
    horizontal second segment. A run along that row is the segment the text hangs from, or another
    one in the same band, and neither is what the check of spec 7.1 looks for."""
    return frozenset((j, k) for j, q in enumerate(paths) for k in range(len(q) - 1)
                     if q[k][0] == q[k + 1][0])


def met(cand, rects):
    """The nearest of `rects` the candidate's text runs into, as a Clash of its kind and its owner —
    what a label that does not stand clear lies on, and what stands in the way of one that fits
    nowhere — or None when the text stands clear of all of them. Nearest is measured from the text's
    near edge outwards, as `room` measures it and without its limit: the limit is the place's own
    reach and names nothing.

    An owner answers once however many rows of the candidate its rectangles meet: what the text runs
    into is one card, one line edge or one label, and the rows it is drawn in are the rows one
    rectangle of this model happens to be cut into (spec 7.3)."""
    plain = cand._replace(limit=INF)
    near = None
    for rect in rects:
        if (rect.Y, rect.owner) in cand.exempt:
            continue
        if not any(overlaps(text, rect, CLEARANCE[rect.kind], 0) for text in cand.rects):
            continue
        at = room(plain, [rect])
        if near is None or at < near[0]:
            near = (at, Clash(rect.kind, rect.owner))
    return None if near is None else near[1]


def greedy(order, cands, needs, cards, runs, upright):
    """The labels of `order` in that order, each taking the first of its candidates with room for
    its text: today's choice, over whatever candidates it is given.

    Room is measured three ways, as the places of spec 7.2 fall into three families. Every place is
    measured against the cards and the bounds, which a text may never stand on. Every place but one
    over or under a horizontal second segment is measured against the lines as well, and a text that
    has to lie on one is told about; on a horizontal second segment the lines are looked for once the
    text stands somewhere, because what counts there is the ones that run through the text itself.
    Beside a vertical second segment the labels already placed count too — that is the one family
    whose places differ in the rows they stand in, so it is the one another label can push out of a
    row.

    Failing all of them the roomiest place is taken with the room it offered and the nearest thing
    in the way there, which is the fit error. `cards` and `runs` are the rectangles of `occupancy`
    split by kind, `needs` the width of each text in px, and `upright` the runs of `uprights`."""
    out, keys, placed = [], {}, []
    for i in order:
        cs, need = cands[i], needs[i]
        wide = [room(c, cards) for c in cs]
        tight = [w if c.where in SECOND_RUN else
                 min(w, room(c, runs + (placed if c.where == BESIDE else [])))
                 for c, w in zip(cs, wide)]
        clashes, short, blocked = [], None, None
        spot = next((c for c, t in zip(cs, tight) if need <= t), None)
        if spot is None:
            spot = next((c for c, w in zip(cs, wide) if need <= w), None)
            if spot is not None:
                on = met(spot, runs + (placed if spot.where == BESIDE else []))
                clashes.append(Clash(ON_LINE, on and on.owner))
        if spot is None:
            at = max(range(len(cs)), key=lambda k: wide[k])
            spot, short = cs[at], max(wide[at], 0)
            # what the error names beside the room: the nearest of everything drawn, since a text
            # that fits nowhere is stopped by a card or a bound and may lie on a line nearer still
            blocked = met(spot, cards + runs + placed)
        placed += list(spot.rects)
        if spot.key in keys:
            clashes.append(Clash(SAME_PLACE, keys[spot.key]))
        keys[spot.key] = i
        if spot.where in SECOND_RUN:
            crossed = {run.owner[0] for run in runs
                       if run.owner in upright and (run.Y, run.owner) not in spot.exempt
                       and any(overlaps(text, run) for text in spot.rects)}
            clashes += [Clash(CROSSED, j) for j in sorted(crossed)]
        out.append(Choice(i, spot, tuple(clashes), short, blocked))
    return out


def place(edges, texts, paths, offsets, geo, cells, occupied, card_w):
    """Where the label of every routed edge that carries one goes: a Choice per label, in the order
    they were placed — the labels that never look at another one first, so that the ones beside a
    vertical second segment, which do, see them all. `texts` is the drawn text of each edge, empty
    where the edge carries none.

    At this commit the places are the table of spec 7.2 and the choice is `greedy`'s."""
    rects = occupancy(cells, paths, offsets, geo, occupied)
    cards = [r for r in rects if r.kind in (CARD, BOUND)]
    runs = [r for r in rects if r.kind == LINE]
    order = sorted((i for i, text in enumerate(texts) if text),
                   key=lambda i: len(paths[i]) >= 3 and paths[i][2][1] != paths[i][1][1])
    needs = {i: label_width(texts[i]) for i in order}
    cands = {i: candidates(i, edges[i], paths[i], needs[i], paths, offsets, geo, cells, occupied,
                           card_w) for i in order}
    return greedy(order, cands, needs, cards, runs, uprights(paths))
