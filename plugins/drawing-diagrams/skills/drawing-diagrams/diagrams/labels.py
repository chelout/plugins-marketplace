"""Where a label may stand, as rectangles of one lattice row.

Every drawn object is one or more rectangles `(Y, y0, y1, x0, x1, kind, owner)`: `Y` a lattice row,
`y` in px from the base of that row as `base()` of template/js/flow.js computes it, `x` in px across
from the grid box as `Geometry` computes it. Card heights are unknown in Python, so the model keeps
that uncertainty instead of guessing: a card is the whole of its row, a vertical run is the whole of
every row it passes and reaches, in a row it ends in, the bend drawn there — or half that row where
nothing here says where the end is drawn — and a text whose place depends on a height covers every
row it can fall in. One predicate — `overlaps` — tests two rectangles of one row, and `room`
measures the px a text has from its near edge outwards to the nearest of them.

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
other place keeps the reference it had. It is also the one place whose text can leave its row: a
gutter is `row_gap` high about its base and an outer row margin `margin` deep, and a text hanging
from a segment drawn off that base can reach past either (spec 7.1 as amended). `reached` says
which rows it then stands in, and there it lies on the cards it shares px with and on nothing else.

Wherever the page's geometry is known here, every object is read in one frame (spec 7.1 as
amended a fourth time): the lines between two rows of cards — a gutter, an outer margin, every line
of a band of empty rows — stand at px `Geometry.frame` states against those cards, and a rectangle
of any of them is written in the row of the frame's lowest line, shifted by where its own base
stands there. So a text on one line of a band meets the lines, the labels and the cards of every
other line it reaches, and a row of cards it reaches drops the place. A row of cards states no px:
there a rectangle holds every y it can be drawn at, from the least height a card is drawn at and
from the clamp of a banded row, and the frames beside it are read for whatever it reaches past it.

`place` is what `flow.plan` asks; `candidates` is the source of places it has, the table of spec 7.2
whole, `terms` prices one place and `cost` a whole choice of them, and `search` looks for the
cheapest — starting from `greedy`, which takes the first place with the room for each label in turn.
What the module never holds is a message: a `Choice` names the place, what stands in the label's way
there, and what stood nearest when no place had the room, and diagrams/flow.py writes the message
about it.

The cost reads every place against every rectangle of the rows it stands in, whatever family the
place belongs to (spec 7.3 as amended): a text on a horizontal second segment is measured against
the lines along its row and against the other labels exactly as one beside a vertical segment is.
The families differ in how a message is worded, never in what is looked at.
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

# The least height template/css draws a card at, in px. The smallest is a note — one line of 11.5 px
# text at line-height 1.35 under 5 + 7 px of padding — and a header is one line of 13 px at 1.25
# under 7 + 6, each inside a 1 px border either side: about 29.5 and 31 px. Every other number here
# that depends on a card's height reads it as unknown; this is the one bound on it, and
# tests/test_browser_lines.py holds every card it draws to it.
CARD_LEAST = 28

# How far inside the band of its cards template/js/flow.js holds a point of a banded row: rowY() and
# clampY() keep it 10 px inside the lowest top and the highest bottom of the cards a line of the row
# enters or leaves sideways. A card being at least CARD_LEAST high, the clamp moves a point towards
# the base of its row and never past it.
CLAMP = 10

CARD, LINE, LABEL, BOUND = "CARD", "LINE", "LABEL", "BOUND"

# How many nodes of the search one plan may spend (spec 7.3).
NODES = 20000

# The shapes of place, as a message names them. `where` is what the message calls the place, and
# what tells the one family whose warning has a wording of its own: a line that crosses a text on a
# horizontal second segment is a "пересечёт" there and a "ляжет" anywhere else. A place of spec 7.2
# joins the family it belongs to and takes its `where` with it — the side of a line a place stands
# on is not in the wording, except where calling a place below a line "над" would be false.
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
# on another label, CROSSED that a line runs through a text standing on a horizontal second
# segment, SAME_PLACE that another label stands in this very place. `owner` names it — the
# rectangle's owner, the path the line belongs to, the other edge.
#
# How many of each a choice raises is part of the contract, since `advice.evaluate` (spec 6) counts
# the warnings of a plan and drops a move that leaves the author with more of them (spec 7.3 as
# amended): one ON_LINE per label whose text lies on a line along its rows or on another label, one
# CROSSED per line crossing a text on a horizontal second segment, and one per pair of overlapping
# labels — told on the later of the two in the model's order, as SAME_PLACE when the two took the
# same place and inside the one ON_LINE of that label when they merely meet.
ON_LINE, CROSSED, SAME_PLACE = "ON_LINE", "CROSSED", "SAME_PLACE"

Clash = collections.namedtuple("Clash", "kind owner")

# Where one label stands: `edge` the routed edge it belongs to, `cand` the place it took, `clashes`
# the warnings that place raises, `room` the px the roomiest place offered when the text fits none
# of them at all — None when it fits one — `blocked`, the nearest thing in the way there as a Clash
# of its kind and its owner, which the error names beside the room (criterion E3), and `hits` the
# line owners the text lies on there, which `terms` prices by the edge each of them belongs to.
Choice = collections.namedtuple("Choice", "edge cand clashes room blocked hits")


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


def _turn(q, off, at, Y, banded):
    """The y a vertical run of path `q` ends at in row `Y`, where this side knows it: the offset of
    the bend drawn at point `at`, which is where template/js/flow.js draws the corner (spec 7.1 as
    amended). None where the y depends on a card height — the row is clamped into the band of its
    cards, and every line of it with an unknown amount, or the run ends on a card, whose own height
    is unknown here. The half row of the model is what stands for it there."""
    if Y in banded or at in (0, len(q) - 1):
        return None
    return off[at][1]


def _key(geo, Y):
    """(the row a rectangle of lattice row `Y` is written in, the px its y shifts by there): the
    lowest line of the frame for a line whose frame `Geometry.frame` states, and the row itself,
    unshifted, for a row of cards."""
    frame = geo.frame(Y)
    return (Y, 0.0) if frame is None else (frame.row, frame.at)


def _poke(geo, Y, up, down):
    """What something of the row of cards `Y` reaches past its top edge by `up` px and past its
    bottom edge by `down`: [(row, y0, y1)] in the frames over and under the row, and the rows of
    cards beyond those it reaches as well."""
    spans, rows = [], []
    if up > 0:
        frame = geo.frame(Y - 1)
        spans.append((frame.row, frame.bottom - up, frame.bottom))
        if frame.bottom - up < frame.top:
            rows.append(frame.first - 1)
    if down > 0:
        frame = geo.frame(Y + 1)
        spans.append((frame.row, frame.top, frame.top + down))
        if frame.top + down > frame.bottom:
            rows.append(frame.row + 1)
    return spans, rows


def _stands(geo, Y, y0, y1, banded, poke=(0, 0)):
    """([(row, y0, y1)] where a text spanning `y0`..`y1` of lattice row `Y` stands, [the rows of
    cards it only reaches into]).

    On a line of a known frame the text is written in that frame, and a finite side of it past the
    card edge on that side reaches the row of cards there. On a row of cards no line enters
    sideways its y is px from the middle of the row, which is at least CARD_LEAST high, so a side
    farther than half that from the middle can stand past the row by the rest — in the frame beside
    it, and on into the next row of cards. On a banded row its y is an order among the lines of the
    row, which the clamp keeps, and how far it reaches past the row is `poke` (up, down), which only
    the caller can tell from the clamp."""
    frame = geo.frame(Y)
    if frame is not None:
        a, b = y0 + frame.at, y1 + frame.at
        rows = []
        if -INF < a < frame.top:
            rows.append(frame.first - 1)
        if INF > b > frame.bottom:
            rows.append(frame.row + 1)
        return [(frame.row, a, b)], rows
    if Y not in banded:
        half = CARD_LEAST / 2
        poke = (-y0 - half if y0 > -INF else 0, y1 - half if y1 < INF else 0)
    spans, rows = _poke(geo, Y, *poke)
    return [(Y, y0, y1)] + spans, rows


def _clamped(oy, near, far):
    """How far past the edges of a banded row of cards a text drawn `near`..`far` px from a line of
    that row at offset `oy` can reach: (over its top edge, under its bottom edge). The clamp holds
    the line CLAMP inside the band of the cards, and it moves the line only towards the base of the
    row, which stands at least half of CARD_LEAST inside that band, so the line stands no nearer an
    edge than both of those allow."""
    top = max(CLAMP, CARD_LEAST / 2 + min(0.0, oy))
    bottom = max(CLAMP, CARD_LEAST / 2 - max(0.0, oy))
    return max(0.0, -near - top), max(0.0, far - bottom)


def _column(geo, lo, hi, top, bottom):
    """[(row, y0, y1)] of something drawn down the page from `top` in lattice row `lo` to `bottom`
    in row `hi`, each from the base of its own row, and through the whole of every row between. A
    frame it stands in is one rectangle, from the end standing in it or from the edge it enters by,
    to the other end or the edge it leaves by."""
    out = {}
    for Y in range(lo, hi + 1):
        R, at = _key(geo, Y)
        a = top + at if Y == lo else -INF
        b = bottom + at if Y == hi else INF
        out[R] = (out[R][0], b) if R in out else (a, b)
    return [(R, a, b) for R, (a, b) in out.items()]


def occupancy(cells, paths, offsets, geo, occupied):
    """Every drawn object as rectangles: the cards on `occupied` cells, named by the node standing
    there; the runs of every path, named by (path index, segment index); and the bounds the drawn
    area ends at — the left edge of the grid box and `Geometry.total` across.

    A card is the whole of its row: its height is unknown here, and cards align to the top of the
    row, so nothing below its bottom edge can be told from inside it. A vertical run covers the
    whole of every row it passes through, and a row it ends in down to the bend drawn there, its own
    half-width kept. Where `_turn` cannot say where that end is drawn, half of the row stays — the
    half the run comes from — and in a banded row it runs on to the bend's own offset where that
    lies past the base, since the clamp draws the bend somewhere between the two. A horizontal run is
    its offset either way of the base, as wide as it is drawn, and on a row of cards no line enters
    sideways it can be drawn past the row as `_stands` reads it.

    Every rectangle of a line of a known frame is written in that frame (`_key`), and a run through
    several lines of one frame is one rectangle there, from end to end."""
    named = {}
    for nid, rc in cells.items():
        if rc in occupied:
            named.setdefault(rc, nid)
    out = [Rect(2 * r + 1, -INF, INF, geo.left(c), geo.right(c), CARD, named.get((r, c), (r, c)))
           for r, c in sorted(occupied)]
    banded = banded_rows(paths)
    for j, (q, off) in enumerate(zip(paths, offsets)):
        for k in range(len(q) - 1):
            (x1, y1), (x2, y2) = q[k], q[k + 1]
            if x1 == x2:
                x = geo.x(x1) + off[k][0]
                lo, hi = min(y1, y2), max(y1, y2)
                above, below = (k, k + 1) if y1 < y2 else (k + 1, k)
                ends = []
                for at, Y, way in ((above, lo, -1), (below, hi, 1)):
                    turn = _turn(q, off, at, Y, banded)
                    if turn is not None:
                        ends.append(turn + way)
                    elif Y in banded and 0 < at < len(q) - 1:
                        ends.append((min if way < 0 else max)(0.0, off[at][1]) + way)
                    else:
                        ends.append(0.0)
                for R, a, b in _column(geo, lo, hi, *ends):
                    out.append(Rect(R, a, b, x - 1, x + 1, LINE, (j, k)))
            else:
                xa, xb = geo.x(x1) + off[k][0], geo.x(x2) + off[k + 1][0]
                for R, a, b in _stands(geo, y1, off[k][1] - 1, off[k][1] + 1, banded)[0]:
                    out.append(Rect(R, a, b, min(xa, xb), max(xa, xb), LINE, (j, k)))
    for R in sorted({_key(geo, Y)[0] for Y in range(2 * geo.rows + 1)}):
        out.append(Rect(R, -INF, INF, -INF, 0.0, BOUND, "left"))
        out.append(Rect(R, -INF, INF, geo.total, INF, BOUND, "right"))
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


def _texts(spans, rows, start, grow, need, owner):
    """The rectangles of one text standing where `_stands` says: one per span, and the whole of
    every row of cards it only reaches into."""
    return (*(_text(R, a, b, start, grow, need, owner) for R, a, b in spans),
            *(_text(R, -INF, INF, start, grow, need, owner) for R in rows))


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


def _drawn(geo, q, off, at):
    """(the frame row, the px y there) of point `at` of path `q` as template/js/flow.js draws it,
    where this side knows it: a bend on a line of a known frame, or the top edge of a card a
    vertical segment comes down onto, which is the edge its row begins with. None anywhere else — a
    point of a row of cards, whose y depends on the height of the row, and a card's bottom edge."""
    if at in (0, len(q) - 1):
        if q[at][1] <= q[at - 1][1]:
            return None
        frame = geo.frame(q[at][1] - 1)
        return frame.row, frame.bottom
    frame = geo.frame(q[at][1])
    return None if frame is None else (frame.row, frame.at + off[at][1])


def _least(geo, q, off, lo, hi, banded):
    """The least px the second segment of `q`, lattice rows `lo` to `hi`, can be drawn long: from
    its upper end to the edge of that end's row or frame, the whole of every frame between — each
    its own height — and every row of cards between, at least CARD_LEAST, and on to its lower end.
    A bend on a line of a known frame stands its px from that frame's edge, one on a banded row
    CLAMP inside it, one on another row of cards at least half a card from the middle less its own
    offset, and a card's own edge on it."""
    upper = 1 if q[1][1] == lo else 2

    def reach(at, Y, down):
        if at in (0, len(q) - 1):
            return 0.0
        frame, oy = geo.frame(Y), off[at][1]
        if frame is not None:
            return frame.bottom - frame.at - oy if down else frame.at + oy - frame.top
        if Y in banded:
            return CLAMP
        return CARD_LEAST / 2 - oy if down else CARD_LEAST / 2 + oy

    keys = []
    for Y in range(lo, hi + 1):
        R = _key(geo, Y)[0]
        if not keys or keys[-1][0] != R:
            keys.append((R, Y))
    out = reach(upper, lo, True) + reach(3 - upper, hi, False)
    for _, Y in keys[1:-1]:
        frame = geo.frame(Y)
        out += CARD_LEAST if frame is None else frame.bottom - frame.top
    return out


def _middle(geo, q, off, lo, hi, rows, bend, banded):
    """([(row, y0, y1)], [rows of cards reached]) of the text at the middle of the vertical second
    segment of path `q`, which template/js/flow.js draws at the middle of the segment's two drawn
    points, `rows` the lattice rows it can fall in.

    Where both points are drawn on lines of one known frame, that middle is known, and the text
    stands there. Anywhere else it depends on card heights, and the text covers every row between
    the two ends whole, and in the row of each end the row past the bend drawn there: past it by
    1 px where the segment is long enough to keep the text's near edge that far off the bend, and by
    what `_least` leaves where it is not. `flow.band_obstacles` read such a row the other way round:
    every line that crosses it counted, wherever it stopped, and every line that runs along it was
    left out, wherever it ran — the one reading the two differed in.

    A banded row is read past the bend here where `_turn` gives a run of that row no y at all: this
    text hangs from the middle of its own second segment, so the clamp that moves the bend moves the
    text with it and the order of the two survives, where the px a clamped line stands from the base
    of its row do not — unless the segment is too short to keep the text past the bend, and then
    the whole row."""
    ends = [_drawn(geo, q, off, 1), _drawn(geo, q, off, 2)]
    if ends[0] and ends[1] and ends[0][0] == ends[1][0]:
        m = (ends[0][1] + ends[1][1]) / 2
        return _stands(geo, ends[0][0], m - TEXT_HALF, m + TEXT_HALF, banded)
    past = min(1.0, _least(geo, q, off, lo, hi, banded) / 2 - TEXT_HALF)
    spans, rows_reached = [], []
    for Y in rows:
        y0 = bend[Y] + past if Y == lo and Y in bend else -INF
        y1 = bend[Y] - past if Y == hi and Y in bend else INF
        if Y in banded and past < 1:
            y0, y1 = -INF, INF
        got, reach = _stands(geo, Y, y0, y1, banded)
        rows_reached += [R for R in reach if R not in rows_reached]
        for R, a, b in got:
            if spans and spans[-1][0] == R:
                spans[-1] = (R, spans[-1][1], b)
            elif R in [x[0] for x in spans]:
                k = next(n for n, x in enumerate(spans) if x[0] == R)
                spans[k] = (R, min(spans[k][1], a), max(spans[k][2], b))
            else:
                spans.append((R, a, b))
    return spans, rows_reached


def reached(geo, Y, y0, y1):
    """The rows of cards a text spanning `y0`..`y1` of lattice row `Y` reaches into (spec 7.1 as
    amended a third and a fourth time on 2026-09-21: a text stands in every row it reaches, and is
    read in the frame of the line it hangs from).

    A row line this side states the px of is one of a known frame (`Geometry.frame`): a gutter in
    the middle of the `row_gap` between two rows of cards, an outer row margin `margin` px outside
    them, and every line of a band of empty rows where `tracks()` invents its tracks. Cards align to
    the top of their row, so the row under the frame begins with its cards and a text reaching into
    it lies on whatever card it shares px with; the row over it ends with its tallest card, whose
    height is unknown here, so a text reaching into that one is read the same way.

    Nothing comes back for a row of cards, as high as its own tallest card: what a text there
    reaches past it is `_stands`'."""
    if geo.frame(Y) is None:
        return ()
    return tuple(_stands(geo, Y, y0, y1, ())[1])


def drawn_owners(paths):
    """Everything drawn in a row but the cards and the bounds, by the owner the model names it
    with: a run by the (path, segment) it is, a text by the edge it belongs to."""
    return (tuple((j, k) for j, q in enumerate(paths) for k in range(len(q) - 1))
            + tuple(range(len(paths))))


def _on_segment(i, p, off, x1, x2, need, geo, owners, banded):
    """The three places on a horizontal second segment, preferred first (spec 7.2): over it just
    after the bend, under it just after the bend, over it at its far end. `x1` is the px x of the
    bend the segment starts at, `x2` of the end it runs to.

    "Just after the bend" starts the text LABEL_BEND past the bend and grows away from the source;
    the far end grows back towards it. Either way the text may reach neither end of the segment, so
    all three have the segment's own length less that bend and a clearance for their limit.

    Down the row every one of them is read from the segment as it is drawn — `off[1][1]`, the y its
    own line is spread to — and not from the base of the row (spec 7.2 as amended): the anchor takes
    the drawn y of the point it hangs from, so the text moves with the line it belongs to, and a
    segment drawn far from the base no longer runs through its own label. A segment drawn far enough
    off that base takes its text out of the row as well, and `_stands` says which rows it then
    stands in. Along a banded row of cards the clamp moves the segment and its text together: the
    text covers the row past its own line, and past the row's edge as far as the clamp leaves the
    line from it.

    In a row it only reaches into the text lies on the cards it shares px with, and on nothing else
    (spec 7.1 as amended): it pokes past the edge of that row, and everything else drawn there — the
    lines along it, the texts standing on its base — is a card height away from that edge, which
    this side does not know. A line that crosses the row passes the text's own row on its way and is
    met there instead. So every such owner is the place's `exempt` in the rows it reaches, beside
    its own supporting path in all of them."""
    Y, seg, rt = p[1][1], off[1][1], x2 > x1
    # the cells under the segment are empty, so the only limit across is the far end of the segment
    limit = abs(x2 - x1) - LABEL_BEND - LABEL_CLEAR
    out = []
    for rank, (where, pt, x, back) in enumerate(((OVER, 1, x1, False), (BENEATH, 1, x1, False),
                                                 (OVER, 2, x2, True))):
        away = rt != back  # whether the text grows rightwards from the end it hangs from
        start = x + LABEL_BEND if away else x - LABEL_BEND
        grow = "R" if away else "L"
        up = where == OVER
        dy = -LABEL_OVER if up else LABEL_UNDER   # from the segment to the baseline
        near = dy - LABEL_DROP - TEXT_HALF        # and on to the edges of the text
        far = dy - LABEL_DROP + TEXT_HALF
        if Y in banded:
            spans, rows = _stands(geo, Y, *((-INF, seg - 1) if up else (seg + 1, INF)), banded,
                                  _clamped(seg, near, far))
        else:
            spans, rows = _stands(geo, Y, seg + near, seg + far, banded)
        exempt = {(R, (i, k)) for R in (*(s[0] for s in spans), *rows) for k in range(len(p) - 1)}
        exempt |= {(R, owner) for R in rows for owner in owners}
        out.append(Candidate(where, rank, _texts(spans, rows, start, grow, need, i),
                             start, grow, limit,
                             # the place a second label would have to take to land on this text:
                             # the end it hangs from and the way it grows, and the segment's own
                             # offset with them, since that is what the text is drawn from now
                             ("h", Y, seg, p[pt][0], p[2][0] > p[1][0], up), frozenset(exempt),
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
    owners = drawn_owners(paths)
    if len(p) >= 3 and p[2][1] == p[1][1]:
        x1 = geo.clamp(c, geo.x(p[1][0]) + off[1][0])
        if len(p) == 3:
            x2 = geo.left(tc) if p[2][0] > p[1][0] else geo.right(tc)
        else:
            x2 = geo.x(p[2][0]) + off[2][0]
            if len(p) == 4:
                x2 = geo.clamp(tc, x2)
        return _on_segment(i, p, off, x1, x2, need, geo, owners, banded)
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
        exempt = frozenset((_key(geo, Y)[0], (i, 1)) for Y in range(lo, hi + 1))
        out, rank = [], 0
        for pin, rows in [(None, middle)] + [(Y, [Y]) for Y in pinned]:
            blo, bhi = (lo, hi) if pin is None else (pin, pin)
            for side in ("R", "L"):
                if (side == "R" and X == 2 * geo.cols) or (side == "L" and X == 0):
                    continue  # outside the grid box the section clips the text
                start = x + LABEL_BEND if side == "R" else x - LABEL_BEND
                # pinned, the text stands on the base of its row, or anywhere in a banded one
                spans, reach = (_middle(geo, p, off, lo, hi, rows, bend, banded) if pin is None
                                else _stands(geo, pin, *((-INF, INF) if pin in banded
                                                         else (-TEXT_HALF, TEXT_HALF)), banded))
                la = (1, "m" if pin is None else "r", 0 if pin is None else pin,
                      LABEL_BEND if side == "R" else -LABEL_BEND, LABEL_DROP,
                      "start" if side == "R" else "end")
                out.append(Candidate(BESIDE, rank, _texts(spans, reach, start, side, need, i),
                                     start, side, card_w - 20, ("v", X, blo, bhi, side),
                                     exempt | {(R, owner) for R in reach for owner in owners}, la))
                rank += 1
        return out
    if sa in ("L", "R"):
        # straight sideways: from the card edge towards the next card in the row, which is the
        # target, above the label's own line and then below it. The text is clamped with that line,
        # so above it covers everything over the line's top edge and below it everything under the
        # bottom edge — the order is all the clamp of a banded row leaves of the two
        # clamped within its card, the line stands inside the card's edges, and the text reaches
        # past them into the gutter over or under the card as far as `_clamped` leaves it
        Y = p[0][1]
        start = geo.right(c) + LABEL_SIDE if sa == "R" else geo.left(c) - LABEL_SIDE
        dx = LABEL_SIDE if sa == "R" else -LABEL_SIDE
        anchor = "start" if sa == "R" else "end"
        out = []
        for rank, (up, rows) in enumerate(((True, (-INF, off[0][1] - 1)),
                                           (False, (off[0][1] + 1, INF)))):
            dy = -LABEL_LIFT if up else LABEL_SINK
            near, far = dy - LABEL_DROP - TEXT_HALF, dy - LABEL_DROP + TEXT_HALF
            spans, reach = _stands(geo, Y, *rows, banded | {Y}, _clamped(off[0][1], near, far))
            exempt = ({(Y, (i, 0)), (Y, e["a"])}
                      | {(R, owner) for R in reach for owner in owners})
            out.append(Candidate(SIDEWAYS, rank, _texts(spans, reach, start, sa, need, i),
                                 start, sa, geo.gap + card_w - 20, (e["a"], sa, up),
                                 frozenset(exempt), (0, "p", 0, dx, dy, anchor)))
        return out
    # straight down or up: the text stands in the gutter under or over the card, between the card
    # and the middle of the gutter, where lines run, on the right of its own line and then on the
    # left. Under a card shorter than its row it stands higher, never lower, so when the row holds
    # other cards it may stand in the row as well
    # the card edge is the frame's own, wherever the line the text stands on lies in it
    Y, up = (p[0][1] + 1, False) if sa == "B" else (p[0][1] - 1, True)
    frame = geo.frame(Y)
    middle = LABEL_ABOVE + LABEL_DROP if up else LABEL_BELOW - LABEL_DROP  # off the card edge
    mid = frame.bottom - middle if up else frame.top + middle
    x = geo.clamp(c, geo.x(p[1][0]) + off[1][0])
    spans, reach = _stands(geo, frame.row, *((mid - TEXT_HALF, INF) if up
                                             else (-INF, mid + TEXT_HALF)), banded)
    in_row = not up and any(rr == r and cc != c for rr, cc in occupied)
    out = []
    for rank, side in enumerate(("R", "L")):
        start = x + LABEL_BESIDE if side == "R" else x - LABEL_BESIDE
        rects = list(_texts(spans, reach, start, side, need, i))
        exempt = {(frame.row, (i, 0))} | {(R, owner) for R in reach for owner in owners}
        if in_row:
            # the rectangle of that row is the height of the card the text hangs from, which this
            # side does not know, and it is there for the cards of the row and for the lines drawn
            # at their height. Another label of the row hangs from a card of that row and is drawn
            # within its height, rising and falling with it exactly as this text does with its own,
            # so what it would answer for there is that unknown and not a place two texts share
            R = p[0][1]
            rects.append(_text(R, -INF, INF, start, side, need, i))
            exempt |= ({(R, e["a"])} | {(R, owner) for owner in _at_card(p[0], paths)}
                       | {(R, j) for j in range(len(paths))})
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


def hits(cand, rects):
    """The owners of `rects` the candidate's text lies on, each named once however many rows of the
    place its rectangles are met in. An owner here is still the (path, segment) a run is named by:
    what the cost counts is the path, `terms` below taking each of these by its edge, and the
    segment is what tells a run crossing the text from one along its row.

    The exemptions of spec 7.1 are what a place is never measured against: its own supporting path,
    and the card it hangs from with the lines drawn within that card's height.

    The rows the place stands in are taken first, since the search asks this of every place of
    every label and a plan's rectangles are spread over the whole lattice."""
    mine = frozenset(text.Y for text in cand.rects)
    return frozenset(rect.owner for rect in rects
                     if rect.Y in mine and (rect.Y, rect.owner) not in cand.exempt
                     and any(overlaps(text, rect, CLEARANCE[rect.kind], 0) for text in cand.rects))


def meet(a, b):
    """Whether the texts of two places overlap: two labels in one row keep LABEL_WORD more than a
    text keeps off a line, or the two read as one phrase. Either place's exemptions hold here as
    they hold against a card or a line — a rectangle a place is not measured in is not one it can
    meet another text in."""
    mine, yours = a.rects[0].owner, b.rects[0].owner
    return any(overlaps(x, y, CLEARANCE[LABEL], 0)
               for x in a.rects if (x.Y, yours) not in a.exempt
               for y in b.rects if (y.Y, mine) not in b.exempt)


def _span(cands):
    """The rows a label's places can fall in and the px they run between, over all of them: two
    labels whose spans do not meet have no pair of places that can, which is what keeps the pairing
    below off the labels standing nowhere near each other."""
    rects = [rect for c in cands for rect in c.rects]
    return (frozenset(rect.Y for rect in rects),
            min(rect.x0 for rect in rects), max(rect.x1 for rect in rects))


def terms(cand, hit, pinned=()):
    """What one place contributes to the cost of spec 7.3: the pairs it makes with the places that
    stand still, the line edges its text lies on — an edge once per candidate however many of its
    rectangles are hit, and a path cut into several runs is one edge — and the place's own
    preference rank. `hit` is what `hits` answered for this place.

    This is the one place a place is priced. `cost` prices a finished choice with it and the search
    a half-built one, so what the search minimises is what the cost compares; a pair of two chosen
    places belongs to neither of them alone and is counted over the choice instead, once."""
    return (sum(1 for other in pinned if meet(cand, other)),
            len({owner[0] for owner in hit}),
            cand.rank)


def cost(choices):
    """What a whole choice of places costs, compared lexicographically (spec 7.3): the pairs of
    chosen labels whose texts overlap, the line edges those texts lie on, and the sum of the
    preference ranks of the places taken.

    Every term is a sum of non-negative parts, one per label or per pair of them, which is what lets
    the search price a half-built choice and lets a component be solved apart from the rest."""
    took = sorted(choices, key=lambda c: c.edge)
    out = [sum(1 for k, a in enumerate(took) for b in took[k + 1:] if meet(a.cand, b.cand)), 0, 0]
    for c in took:  # nothing stands still in a whole choice: its pairs are the ones counted above
        for term, part in enumerate(terms(c.cand, c.hits)):
            out[term] += part
    return tuple(out)


def fits(order, cands, needs, cards):
    """({label: the places whose text stands clear of the cards and the bounds, preferred first},
    {label: the room the roomiest place offered}).

    A place a card or a bound covers is dropped, since no choice may put a text on one. A label
    left with none of them keeps the roomiest place it had and answers with the room there, which
    is the fit error of criterion E3 and what `flow.plan` has always reported."""
    keep, short = {}, {}
    for i in order:
        wide = [room(c, cards) for c in cands[i]]
        left = [c for c, w in zip(cands[i], wide) if needs[i] <= w]
        if left:
            keep[i] = left
        else:
            at = max(range(len(wide)), key=lambda k: wide[k])
            keep[i], short[i] = [cands[i][at]], max(wide[at], 0)
    return keep, short


def components(free, places):
    """The labels of `free` grouped by whether their places can overlap: two are in one group when
    some place of the one meets some place of the other, and a group is solved apart from the rest
    because no choice inside it can change what any other group costs. Groups come back in the
    model's order, by the first label of each."""
    home = {i: i for i in free}

    def root(i):
        while home[i] != i:
            home[i] = home[home[i]]
            i = home[i]
        return i

    spans, clear = {i: _span(places[i]) for i in free}, CLEARANCE[LABEL]
    for k, i in enumerate(free):
        rows, x0, x1 = spans[i]
        for j in free[k + 1:]:
            other, ox0, ox1 = spans[j]
            if (root(i) == root(j) or not (rows & other)
                    or ox0 - clear >= x1 or x0 - clear >= ox1):
                continue
            if any(meet(a, b) for a in places[i] for b in places[j]):
                home[root(j)] = root(i)
    out = {}
    for i in free:
        out.setdefault(root(i), []).append(i)
    return [out[k] for k in sorted(out, key=lambda k: min(out[k]))]


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


def verdicts(order, took, short, cards, runs, upright):
    """What a plan has to say about a finished choice: one Choice per label of `order`, in that
    order, with `took` the place each one holds and `short` the room of the labels that fit nowhere.

    Every place is read against every rectangle of the rows it stands in, whatever family it belongs
    to (spec 7.3 as amended). What the families differ in is the wording: a line crossing a text on
    a horizontal second segment raises the "пересечёт" of its own, so the "ляжет" of such a label is
    left to the lines along its rows and to the other labels. A pair of labels whose texts overlap
    is told about once, on the later of the two in the model's order — as SAME_PLACE where the two
    took the very same place, and inside that label's one "ляжет" where they merely meet. A label
    therefore answers for the labels before it and never for the ones after, which is also what the
    fit error names beside its room."""
    out = []
    for i in order:
        cand, hit = took[i], hits(took[i], runs)
        crossed = sorted({run.owner[0] for run in runs if run.owner in hit
                          and run.owner in upright}) if cand.where in SECOND_RUN else []
        before = [rect for j in order if j < i for rect in took[j].rects]
        lay = [j for j in order if j < i and meet(took[j], cand)]
        same = [j for j in lay if took[j].key == cand.key]
        clashes = []
        # a label that fits nowhere is answered for by its error, which already names the nearest
        # thing in its way: the warning that it lies on something would be the same fact twice, and
        # the advice of spec 6 counts both
        if i not in short and ([owner for owner in hit if owner not in upright or not crossed]
                               or lay):
            on = met(cand, runs + before)
            clashes.append(Clash(ON_LINE, on and on.owner))
        clashes += [Clash(SAME_PLACE, j) for j in same]
        clashes += [Clash(CROSSED, j) for j in crossed]
        # what the error of a label that fits nowhere names beside the room: the nearest of
        # everything drawn, since such a text is stopped by a card or a bound and may lie on a line
        # nearer still
        blocked = met(cand, cards + runs + before) if i in short else None
        out.append(Choice(i, cand, tuple(clashes), short.get(i), blocked, hit))
    return out


def greedy(order, cands, needs, cards, runs, upright):
    """The labels of `order` in that order, each taking the first of its places with room for its
    text: today's choice, over whatever candidates it is given, and the complete choice the search
    of spec 7.3 starts from and is never allowed to do worse than.

    Room is measured three ways here, as the places of spec 7.2 fall into three families. Every
    place has already been measured against the cards and the bounds by `fits`, which a text may
    never stand on. Every place but one on a horizontal second segment is measured against the lines
    as well; on that segment they are not, which is why greedy takes the first place `fits` left it
    there and why what tells the three apart is the search — or, where one of them would take its
    text out of the gutter onto a card, `fits` itself. Beside a vertical second segment the labels
    already placed count too. Failing all of them the preferred place is taken, and `verdicts` says
    what the label then lies on.

    `cards` and `runs` are the rectangles of `occupancy` split by kind, `needs` the width of each
    text in px, and `upright` the runs of `uprights`."""
    keep, short = fits(order, cands, needs, cards)
    return verdicts(order, _first_fit(order, keep, needs, runs), short, cards, runs, upright)


def _first_fit(order, keep, needs, runs):
    """{label: the place greedy takes}, over the places `fits` left it — the half of `greedy` the
    search calls with the `fits` it has already paid for."""
    took, placed = {}, []
    for i in order:
        spot = next((c for c in keep[i]
                     if c.where in SECOND_RUN
                     or needs[i] <= room(c, runs + (placed if c.where == BESIDE else []))),
                    keep[i][0])
        took[i], placed = spot, placed + list(spot.rects)
    return took


def _pairings(group, places):
    """{label: {another label of the component: whether each of their places meets each of its}}.
    This is the whole of what couples the labels of a component, and the search looks it up at
    every node rather than measuring two rectangles again there."""
    near = {i: {} for i in group}
    spans = {i: _span(places[i]) for i in group}
    clear = CLEARANCE[LABEL]
    for k, i in enumerate(group):
        rows, x0, x1 = spans[i]
        for j in group[k + 1:]:
            other, ox0, ox1 = spans[j]
            if not (rows & other) or ox0 - clear >= x1 or x0 - clear >= ox1:
                continue
            grid = [[meet(a, b) for b in places[j]] for a in places[i]]
            if any(any(row) for row in grid):
                near[i][j] = grid
                near[j][i] = [list(col) for col in zip(*grid)]
    return near


def _score(walk, pick, priced, near):
    """What a complete choice of one component costs: each place on its own, and the pairs of this
    component's labels that meet in it."""
    out = [0, 0, 0]
    for k, i in enumerate(walk):
        for term, part in enumerate(priced[i][pick[i]]):
            out[term] += part
        out[0] += sum(1 for j in walk[:k] if j in near[i] and near[i][j][pick[i]][pick[j]])
    return tuple(out)


def _bound(group, places, priced, start, budget):
    """Branch and bound over one component, most constrained first: {label: the place it takes}, as
    a position in its own list. `priced` gives each place what it costs on its own, `start` is the
    incumbent greedy left and `budget` the nodes left over the whole plan, spent here and read by
    the caller. The incumbent comes back unchanged when nothing cheaper is found and when the nodes
    run out, which is what makes the search never worse than greedy and stop wherever it is.

    A half-built choice already costs what its head costs: every term of the cost is a sum of
    non-negative parts, so a branch that has reached the incumbent's cost cannot be brought under it
    further down and is cut off there.

    A node is one place priced against the head above it, and one choice carried to its end: what
    the allowance bounds is the work, not the depth, and an allowance of one buys the root of the
    walk and no place at all."""
    near = _pairings(group, places)
    walk = sorted(group, key=lambda i: (len(places[i]), -len(near[i]), i))
    best = [dict(start), _score(walk, start, priced, near)]
    held = {}

    def step(k, acc):
        if budget[0] <= 0:
            return
        budget[0] -= 1
        if k == len(walk):
            best[0], best[1] = dict(held), acc
            return
        i = walk[k]
        for at in range(len(places[i])):
            if budget[0] <= 0:
                return
            budget[0] -= 1
            own = priced[i][at]
            with_it = (acc[0] + own[0] + sum(1 for j in walk[:k] if j in near[i]
                                             and near[i][j][at][held[j]]),
                       acc[1] + own[1], acc[2] + own[2])
            if with_it >= best[1]:
                continue
            held[i] = at
            step(k + 1, with_it)
    step(0, (0, 0, 0))
    return best[0]


def search(order, cands, needs, cards, runs, upright, nodes=NODES):
    """(the choices, the nodes the search spent): the cheapest choice of places it found, priced by
    `cost` (spec 7.3).

    The labels whose places can overlap form components, and each is solved by branch and bound from
    greedy's choice over the same candidates, which is complete by construction. A label left one
    place stands still and is priced into the places of the labels it meets. The components are
    given the node allowance in the model's order, so a plan that runs out of nodes keeps greedy's
    choice for the components it never reached: the result is never worse than greedy's, and the
    same input always gives the same one."""
    keep, short = fits(order, cands, needs, cards)
    took = _first_fit(order, keep, needs, runs)
    free = [i for i in sorted(order) if len(keep[i]) > 1]
    still = [i for i in sorted(order) if len(keep[i]) == 1]
    left = [nodes]
    for group in components(free, keep):
        # what the labels outside this component contribute is the same whatever it chooses: the
        # ones left a single place stand still, and no place of another component can meet one of
        # this one, which is what a component is
        pinned = [took[j] for j in still]
        priced = {i: [terms(c, hits(c, runs), pinned) for c in keep[i]] for i in group}
        start = {i: keep[i].index(took[i]) for i in group}
        for i, at in _bound(group, {i: keep[i] for i in group}, priced, start, left).items():
            took[i] = keep[i][at]
    return verdicts(order, took, short, cards, runs, upright), nodes - left[0]


def place(edges, texts, paths, offsets, geo, cells, occupied, card_w, nodes=NODES):
    """Where the label of every routed edge that carries one goes: a Choice per label, in the order
    they were placed — the labels whose place stands in one row first, so that the ones beside a
    vertical second segment, which reach into several, are placed against them. `texts` is the drawn
    text of each edge, empty where the edge carries none, and `nodes` the allowance the search of
    spec 7.3 has; `nodes=1` buys the root of the first component and nothing else, which is greedy's
    own choice."""
    rects = occupancy(cells, paths, offsets, geo, occupied)
    cards = [r for r in rects if r.kind in (CARD, BOUND)]
    runs = [r for r in rects if r.kind == LINE]
    order = sorted((i for i, text in enumerate(texts) if text),
                   key=lambda i: len(paths[i]) >= 3 and paths[i][2][1] != paths[i][1][1])
    needs = {i: label_width(texts[i]) for i in order}
    cands = {i: candidates(i, edges[i], paths[i], needs[i], paths, offsets, geo, cells, occupied,
                           card_w) for i in order}
    return search(order, cands, needs, cards, runs, uprights(paths), nodes)[0]
