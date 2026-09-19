"""Orthogonal routing on the lattice of gutters between grid cells.

Lattice coordinates: X in 0..2*cols, Y in 0..2*rows. Odd coordinates are
column and row centres, even ones are the gutters between them (0 and the
maximum are the outer margins). A node occupies the point (2*col+1, 2*row+1).
A route is a list of lattice points from the source node's point to the
target node's point; it may pass through gutters and through empty cells,
never through another node.
"""
import heapq
import math

STEPS = {(1, 0): "R", (-1, 0): "L", (0, 1): "D", (0, -1): "U"}
OPPOSITE = {"R": "L", "L": "R", "D": "U", "U": "D"}


class Lattice:
    def __init__(self, cols, rows, occupied):
        self.cols, self.rows = cols, rows
        self.W, self.H = 2 * cols + 1, 2 * rows + 1
        self.blocked = {(2 * c + 1, 2 * r + 1): nid for nid, (r, c) in occupied.items()}

    @staticmethod
    def point(r, c):
        return (2 * c + 1, 2 * r + 1)


class Traffic:
    """What earlier routes already occupy: segments, exits per node side,
    entries per node side. Later routes pay to cross, share or bunch."""

    def __init__(self):
        self.segs = []      # (axis, line, lo, hi)
        self.exits = {}     # (point, dir) -> count
        self.entries = {}   # (point, dir) -> count
        self.corners = set()  # every vertex of every path: where lines turn, start or end

    def add(self, path):
        self.segs.extend(segments(path))
        self.corners.update(path[1:-1])
        if len(path) >= 2:
            d0 = STEPS[(_sign(path[1][0] - path[0][0]), _sign(path[1][1] - path[0][1]))]
            d1 = STEPS[(_sign(path[-1][0] - path[-2][0]), _sign(path[-1][1] - path[-2][1]))]
            self.exits[(path[0], d0)] = self.exits.get((path[0], d0), 0) + 1
            self.entries[(path[-1], d1)] = self.entries.get((path[-1], d1), 0) + 1

    def crosses(self, nx, ny, vertical):
        for axis, line, lo, hi in self.segs:
            if vertical and axis == "h" and line == ny and lo < nx < hi:
                return True
            if not vertical and axis == "v" and line == nx and lo < ny < hi:
                return True
        return False

    def shares(self, x, y, nx, ny):
        if x == nx:
            lo, hi = min(y, ny), max(y, ny)
            return any(a == "v" and l == x and s <= lo and hi <= h for a, l, s, h in self.segs)
        lo, hi = min(x, nx), max(x, nx)
        return any(a == "h" and l == y and s <= lo and hi <= h for a, l, s, h in self.segs)


def _sign(v):
    return (v > 0) - (v < 0)


def route(lat, src, dst, labelled=False, traffic=None):
    """Cheapest orthogonal path from src to dst (lattice points), or None.
    Cost: 1 per step, +2 per turn, +1 per empty cell crossed, so the router
    prefers gutters and straight lines. A labelled edge avoids leaving
    sideways into an occupied neighbour: its label would have no room.
    With `traffic`, crossing an earlier line costs +10, running along one +1,
    passing through another line's corner +3,
    leaving through a side another line uses +3 per line, entering beside
    another arrow +3 per arrow: exits spread out and bundles break up."""
    best, prev = {}, {}
    heap = [(0, src[0], src[1], None, None)]
    while heap:
        cost, x, y, d, pk = heapq.heappop(heap)
        key = (x, y, d)
        if key in best:
            continue
        best[key], prev[key] = cost, pk
        if (x, y) == dst:
            pts, k = [], key
            while k is not None:
                pts.append((k[0], k[1]))
                k = prev[k]
            return simplify(list(reversed(pts)))
        for (dx, dy), nd in STEPS.items():
            if d is not None and nd == OPPOSITE[d]:
                continue
            nx, ny = x + dx, y + dy
            if not (0 <= nx < lat.W and 0 <= ny < lat.H):
                continue
            if (nx, ny) in lat.blocked and (nx, ny) != dst:
                continue
            step = 1
            if d is not None and nd != d:
                step += 2
            if nx % 2 == 1 and ny % 2 == 1 and (nx, ny) != dst:
                step += 1
            if d is None and nd == "U":
                step += 8  # a flow reads downward: leave through the top only when nothing else works
            if nx in (0, lat.W - 1) or ny in (0, lat.H - 1):
                step += 1  # the outer margins are the last resort
            if d is None and labelled and nd in ("L", "R") and (x + 2 * dx, y) in lat.blocked:
                step += 8  # the label needs room: prefer another exit
            if (nx, ny) == dst and nd == "U":
                step += 4  # and enter from below only for a real back edge
            if traffic is not None:
                if (nx, ny) != dst and traffic.crosses(nx, ny, dy != 0):
                    step += 10  # crossing an earlier line
                if traffic.shares(x, y, nx, ny):
                    step += 1  # running along an earlier line
                if (nx, ny) in traffic.corners and (nx, ny) != dst:
                    step += 3  # passing through the corner of another line reads as a junction
                if d is None:
                    step += 3 * traffic.exits.get(((x, y), nd), 0)  # another line already leaves this side
                if (nx, ny) == dst:
                    step += 3 * traffic.entries.get((dst, nd), 0)  # another arrow already enters here
            nk = (nx, ny, nd)
            if nk not in best:
                heapq.heappush(heap, (cost + step, nx, ny, nd, key))
    return None


def simplify(pts):
    out = [pts[0]]
    for p in pts[1:]:
        if len(out) >= 2:
            a, b = out[-2], out[-1]
            if (a[0] == b[0] == p[0]) or (a[1] == b[1] == p[1]):
                out[-1] = p
                continue
        out.append(p)
    return out


def route_all(lat, ends, labelled):
    """Route a whole diagram: one path per entry of `ends`, None where there is no route.
    `ends[i]` is (source point, target point) and `labelled[i]` says whether the edge carries a
    label or a footnote, which `route` prices.

    One pass in the given order with accumulating traffic, then two rip-up passes: the first pass
    is greedy in that order, so early lines take the easy exits and late ones detour, and the two
    passes let every line see all the others. An edge with no route stays None and takes no part
    in them."""
    paths, live = [], []
    traffic = Traffic()
    for i, (src, dst) in enumerate(ends):
        p = route(lat, src, dst, labelled=labelled[i], traffic=traffic)
        paths.append(p)
        if p is not None:
            traffic.add(p)
            live.append(i)
    for _ in range(2):
        for i in live:
            others = Traffic()
            for j in live:
                if j != i:
                    others.add(paths[j])
            p = route(lat, ends[i][0], ends[i][1], labelled=labelled[i], traffic=others)
            if p is not None:
                paths[i] = p
    return paths


def side_of(a, b):
    """Side of the node at lattice point `a` that the step towards `b` leaves."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    sx = (dx > 0) - (dx < 0)
    sy = (dy > 0) - (dy < 0)
    return {(1, 0): "R", (-1, 0): "L", (0, 1): "B", (0, -1): "T"}[(sx, sy)]


def segments(path):
    """(axis, line, lo, hi) for every straight segment: axis 'v' means a vertical
    segment on the vertical line X=line spanning Y in [lo, hi]."""
    out = []
    for a, b in zip(path, path[1:]):
        if a[0] == b[0]:
            out.append(("v", a[0], min(a[1], b[1]), max(a[1], b[1])))
        else:
            out.append(("h", a[1], min(a[0], b[0]), max(a[0], b[0])))
    return out


def _along(pt, axis):
    """The coordinate of `pt` along a line of this axis: Y on a vertical line, X on a horizontal."""
    return pt[1] if axis == "v" else pt[0]


def _across_to(pt, other, axis):
    """Which side of a line of this axis the path continues to at `pt`, given the point it goes on
    to: -1 towards the lower coordinate across the line (up or left), +1 towards the higher (down
    or right), 0 where the path stops at `pt` or goes straight on."""
    if other is None:
        return 0
    return _sign(other[1] - pt[1]) if axis == "h" else _sign(other[0] - pt[0])


def _runs(path):
    """The runs of one path and the run of each of its segments.

    A run is a maximal straight piece of the path on one lattice line, so consecutive segments on
    that line are one run. A zero-length segment — two equal consecutive points, which schema.plan
    produces — is a run of its own, on the vertical line through it as today, and does not break
    the piece it lies in. A run carries the interval it covers on its line and the side the path
    leaves to at each of its ends, which is what orders the slots of a group."""
    segs = list(zip(path, path[1:]))
    runs, of_seg, open_run = [], [], None
    for k, (a, b) in enumerate(segs):
        axis = "v" if a[0] == b[0] else "h"
        line = a[0] if axis == "v" else a[1]
        lo, hi = sorted((_along(a, axis), _along(b, axis)))
        going_on = (open_run is not None and a != b
                    and runs[open_run]["axis"] == axis and runs[open_run]["line"] == line)
        if going_on:
            d = runs[open_run]
            d["lo"], d["hi"], d["k1"] = min(d["lo"], lo), max(d["hi"], hi), k
        else:
            runs.append({"axis": axis, "line": line, "lo": lo, "hi": hi, "k0": k, "k1": k})
            if a != b:
                open_run = len(runs) - 1
        of_seg.append(open_run if going_on else len(runs) - 1)
    for d in runs:
        head, tail = path[d["k0"]], path[d["k1"] + 1]
        lo_side = _across_to(head, path[d["k0"] - 1] if d["k0"] else None, d["axis"])
        hi_side = _across_to(tail, _nth(path, d["k1"] + 2), d["axis"])
        if _along(head, d["axis"]) > _along(tail, d["axis"]):
            lo_side, hi_side = hi_side, lo_side
        elif head == tail:
            # a run of no length has both its arms at one point, and either of them tells which
            # side the path leaves to there
            lo_side = hi_side = lo_side or hi_side
        d["lo_side"], d["hi_side"] = lo_side, hi_side
    return runs, of_seg


def assign_offsets(paths, step=8, nodes=frozenset()):
    """Spread edges that share a line. Returns, per path, a list of (ox, oy)
    pixel offsets for each of its points.

    The unit is the run: a maximal straight piece of one path on one lattice
    line (_runs). Runs of one line that overlap or meet end to end in a
    gutter form a group and get distinct slots, so a path with two runs on
    one line gets one slot for each of them. The order of the slots follows
    where each line turns: on a horizontal run the line that turns down lies
    below the one that continues, the line that turns up lies above; on a
    vertical run the line that turns right lies to the right. So a fan of
    lines leaving one node never crosses itself when it spreads.

    Two lines that share a stretch keep one order along all of it, through
    the corners they turn together, so the line inside such a corner on one
    lattice line stays inside on the next: the order they enter and leave
    the stretch in (stretches), and lines between the same two nodes along
    one route the order of their indices on the first segment of the route.
    Two lines that enter and leave in swapped order cross once whatever the
    order; along several lattice lines they keep the one they enter in, where
    the others allow it, and cross where they leave. A pair that shares two
    stretches on one line keeps the order of each: the order belongs to the
    two runs the stretch runs on, not to the two paths.

    Two runs that share no stretch but meet end to end at a gutter point,
    their arms there pointing opposite ways, take the slots their arms point
    to. That is the weakest of the three strengths of order and is recorded
    only where a shared stretch has said nothing, so it never displaces one
    and cannot close a cycle among them."""
    runs = [_runs(p) for p in paths]

    def covering(i, axis, line, lo, hi):
        """The run of path i on this line whose interval covers [lo, hi]: a straight piece of a
        stretch belongs to exactly one run of each path it lies on."""
        for r, d in enumerate(runs[i][0]):
            if d["axis"] == axis and d["line"] == line and d["lo"] <= lo and hi <= d["hi"]:
                return (i, r)
        return None

    # per pair of runs of two paths, the order their shared stretch puts them in:
    # (u, v) -> 1 when run v lies on the higher side of run u, -1 on the lower; firm where the
    # stretch has no swap, loose where it has one
    firm, loose = {}, {}
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            for pts, first, last in stretches(paths[i], paths[j]):
                swap = first * last < 0
                if swap and (len({x for x, _ in pts}) == 1 or len({y for _, y in pts}) == 1):
                    continue  # along one lattice line they cross at an end of it whatever the order
                side = _sign(first) or _sign(last) or _higher(pts[0], pts[1])
                order = loose if swap else firm
                for a, b in zip(pts, pts[1:]):
                    axis, line = ("v", a[0]) if a[0] == b[0] else ("h", a[1])
                    lo, hi = sorted((_along(a, axis), _along(b, axis)))
                    u, v = covering(i, axis, line, lo, hi), covering(j, axis, line, lo, hi)
                    if u is None or v is None:
                        continue
                    order[(u, v)] = side * _higher(a, b)
                    order[(v, u)] = -side * _higher(a, b)

    items = {}  # (axis, line) -> the runs on that line, each knowing its path and its index in it
    for i, (rs, _) in enumerate(runs):
        for r, d in enumerate(rs):
            items.setdefault((d["axis"], d["line"]), []).append(dict(d, i=i, r=r))

    slot = {}   # (path index, run index) -> (slot, width)
    for (axis, line), on_line in items.items():
        on_line.sort(key=lambda d: (d["lo"], d["hi"]))

        def touches_in_gutter(d, reach):
            # two lines meeting end to end: at a node they simply join it, in a gutter they form a
            # junction that must be spread apart
            if d["lo"] != reach:
                return False
            pt = (line, reach) if axis == "v" else (reach, line)
            return pt not in nodes

        # connected groups of overlapping intervals
        groups, cur, reach = [], [], None
        for d in on_line:
            if cur and (d["lo"] < reach or touches_in_gutter(d, reach)):
                cur.append(d)
                reach = max(reach, d["hi"])
            else:
                if cur:
                    groups.append(cur)
                cur, reach = [d], d["hi"]
        if cur:
            groups.append(cur)
        for g in groups:
            if len(g) == 1:
                slot[(g[0]["i"], g[0]["r"])] = (0, 1)
                continue

            def pref(d):
                # the side the line branches to at the ends that lie inside or on another member
                sides = []
                for end, side in (("lo", d["lo_side"]), ("hi", d["hi_side"])):
                    x = d[end]
                    if any(o is not d and o["lo"] <= x <= o["hi"] for o in g) and side:
                        sides.append(side)
                if not sides:
                    sides = [x for x in (d["lo_side"], d["hi_side"]) if x]
                return sum(sides) / len(sides) if sides else 0

            ranked = sorted(g, key=lambda d: (pref(d), (-(d["hi"] - d["lo"]) if pref(d) > 0 else (d["hi"] - d["lo"]))))

            # two runs that meet end to end at a gutter point with their arms there pointing to
            # opposite sides: the one whose arm points to the lower coordinate takes the lower
            # slot, so each corner moves towards its own arms and the pair does not cross twice.
            # They share no stretch, so nothing above says anything about them.
            soft = {}
            for u in g:
                for v in g:
                    if u is v or u["hi"] != v["lo"] or not u["hi_side"] or not v["lo_side"]:
                        continue
                    if u["hi_side"] == v["lo_side"]:
                        continue
                    pt = (line, u["hi"]) if axis == "v" else (u["hi"], line)
                    ku, kv = (u["i"], u["r"]), (v["i"], v["r"])
                    if pt in nodes or (ku, kv) in firm or (ku, kv) in loose:
                        continue
                    soft[(ku, kv)], soft[(kv, ku)] = -u["hi_side"], u["hi_side"]

            def free(d, orders):
                # no run of the group still to place has to lie below d
                return not any(order.get(((o["i"], o["r"]), (d["i"], d["r"]))) == 1
                               for order in orders for o in ranked)

            # the order of shared stretches first, a loose one only where the firm ones allow it
            # and the end-to-end one only where both do; the ranking places the lines they leave
            # free and breaks a cycle among them
            ordered = []
            while ranked:
                n = next((n for n, d in enumerate(ranked) if free(d, (firm, loose, soft))), None)
                if n is None:
                    n = next((n for n, d in enumerate(ranked) if free(d, (firm, loose))), None)
                if n is None:
                    n = next((n for n, d in enumerate(ranked) if free(d, (firm,))), 0)
                ordered.append(ranked.pop(n))
            for n, d in enumerate(ordered):
                slot[(d["i"], d["r"])] = (n, len(ordered))

    def off(key):
        sw = slot.get(key)
        if sw is None:
            return 0.0
        n, w = sw
        return round((n - (w - 1) / 2) * step, 1)

    result = []
    for i, p in enumerate(paths):
        rs, of_seg = runs[i]
        pts = []
        for m in range(len(p)):
            # ox from the vertical run through the point, oy from the horizontal one: the run of
            # the segment that ends at the point, else of the one that starts there. So both points
            # of a segment read one offset on that segment's own axis.
            here = {}
            for k in (m - 1, m):
                if 0 <= k < len(of_seg) and rs[of_seg[k]]["axis"] not in here:
                    here[rs[of_seg[k]]["axis"]] = off((i, of_seg[k]))
            pts.append((here.get("v", 0.0), here.get("h", 0.0)))
        result.append(pts)
    return result


def crossings(paths):
    """Number of places where two paths cross however their lines are spread:
    a vertical segment of one through a horizontal segment of another, and a
    stretch two paths share that they enter and leave in swapped order
    (shared_swaps)."""
    segs = [segments(p) for p in paths]
    n = 0
    for i in range(len(paths)):
        for j in range(len(paths)):
            if i == j:
                continue
            for a in segs[i]:
                if a[0] != "v":
                    continue
                for b in segs[j]:
                    if b[0] != "h":
                        continue
                    if b[2] < a[1] < b[3] and a[2] < b[1] < a[3]:
                        n += 1
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            n += shared_swaps(paths[i], paths[j])
    return n


def shared_swaps(p, q):
    """Number of stretches the paths p and q share that they enter and leave
    in swapped order (stretches): p left of q at one end and right of it at
    the other cross, however the stretch is drawn."""
    return sum(1 for _, first, last in stretches(p, q) if first * last < 0)


BIG = 10000  # one lattice step in the half-pixel units of the two counters below


def drawn_crossings(paths, offsets, nodes):
    """Number of places where the lines as they are drawn cross: a vertical
    segment of one displaced centreline through a horizontal segment of
    another. `offsets` are what assign_offsets returns, `nodes` the lattice
    points the cards sit on. The mapping from lattice to pixels in flow.js is
    monotone per coordinate, so a strict crossing here is one on the page;
    rounded corners, arrowheads and clipping are not modelled."""
    segs = [segments(_drawn_points(p, o, nodes)) for p, o in zip(paths, offsets)]
    n = 0
    for i in range(len(segs)):
        for j in range(len(segs)):
            if i == j:
                continue
            for a in segs[i]:
                if a[0] != "v":
                    continue
                for b in segs[j]:
                    if b[0] == "h" and b[2] < a[1] < b[3] and a[2] < b[1] < a[3]:
                        n += 1
    return n


def drawn_overlaps(paths, offsets, nodes):
    """Number of pairs of segments of two drawn lines that run along one
    coordinate over a stretch of it: two lines sharing a slot, which the
    reader sees as one line."""
    segs = [segments(_drawn_points(p, o, nodes)) for p, o in zip(paths, offsets)]
    n = 0
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            for a in segs[i]:
                for b in segs[j]:
                    if a[0] == b[0] and a[1] == b[1] and max(a[2], b[2]) < min(a[3], b[3]):
                        n += 1
    return n


def _drawn_points(path, offs, nodes):
    """`path` as integer points in half-pixel units: a lattice step is BIG and
    half a pixel is 1, so the .5 of a 5 px pitch stays exact. An end that lies
    on a node moves half a lattice step towards its neighbour and takes the
    neighbour's cross coordinate, as anchor() in flow.js does, so two lines
    that reach one node from different sides do not meet at its centre."""
    pts = [(x * BIG + round(2 * ox), y * BIG + round(2 * oy))
           for (x, y), (ox, oy) in zip(path, offs)]
    out = list(pts)
    for end, nb in ((0, 1), (-1, -2)):
        if len(pts) < 2 or path[end] not in nodes:
            continue
        dx = _sign(path[nb][0] - path[end][0])
        dy = _sign(path[nb][1] - path[end][1])
        if dx:
            out[end] = (pts[end][0] + dx * (BIG // 2), pts[nb][1])
        elif dy:
            out[end] = (pts[nb][0], pts[end][1] + dy * (BIG // 2))
    return out


def stretches(p, q):
    """The stretches the paths p and q share, as (points, first, last): the
    points of p along the stretch, and the side of q against p where they
    enter it and where they leave it, from the points each arrives from or
    leaves to (side_at), relative to p's direction of travel: positive when q
    is on the side _side calls 1, negative on the other, 0 where both meet
    their node. A stretch runs on through a corner both paths turn together;
    sides are taken against the direction of travel, which such a corner
    keeps."""
    rp, rq = _refine(p, q), _refine(q, p)
    at = {pt: k for k, pt in enumerate(rq)}
    k = 0
    while k < len(rp) - 1:
        if rp[k] not in at or rp[k + 1] not in at or abs(at[rp[k + 1]] - at[rp[k]]) != 1:
            k += 1
            continue
        d, s = at[rp[k + 1]] - at[rp[k]], k
        while k + 1 < len(rp) and rp[k + 1] in at and at[rp[k + 1]] - at[rp[k]] == d:
            k += 1
        # the stretch is rp[s..k], and rq walked from at[rp[s]] in steps of d
        t0 = (rp[s + 1][0] - rp[s][0], rp[s + 1][1] - rp[s][1])
        t1 = (rp[k][0] - rp[k - 1][0], rp[k][1] - rp[k - 1][1])
        first = _side(t0, rp[s], _nth(rq, at[rp[s]] - d)) - _side(t0, rp[s], _nth(rp, s - 1))
        last = _side(t1, rp[k], _nth(rq, at[rp[k]] + d)) - _side(t1, rp[k], _nth(rp, k + 1))
        yield rp[s:k + 1], first, last


def _refine(path, other):
    """`path` with every vertex of `other` that lies inside one of its
    segments added, so that a stretch both share has the same points in both."""
    out = [path[0]]
    for a, b in zip(path, path[1:]):
        inner = [v for v in other if v != a and v != b and min(a[0], b[0]) <= v[0] <= max(a[0], b[0])
                 and min(a[1], b[1]) <= v[1] <= max(a[1], b[1])]
        out.extend(sorted(inner, key=lambda v: abs(v[0] - a[0]) + abs(v[1] - a[1])))
        out.append(b)
    return out


def _nth(pts, k):
    return pts[k] if 0 <= k < len(pts) else None


def _higher(a, b):
    """Where the side _side calls 1 lies for travel from a to b, on the axis
    across it: 1 at the higher coordinate (below, right), -1 at the lower."""
    return _sign(b[0] - a[0]) if a[1] == b[1] else -_sign(b[1] - a[1])


def _side(t, pt, other):
    """Side of the direction t at pt that the neighbouring point `other` lies
    on: 1 or -1; 0 straight ahead or behind, or where the path ends at pt."""
    if other is None:
        return 0
    return _sign(t[0] * (other[1] - pt[1]) - t[1] * (other[0] - pt[0]))


def ascii(lat, ids_at, paths, arrows=True):
    """Text rendering: node ids in their cells, routes as box-drawing lines."""
    cols, rows = lat.cols, lat.rows
    colw = [max([len(ids_at.get((r, c), "")) for r in range(rows)] + [1]) + 2 for c in range(cols)]
    gw = 3
    xs = []  # text x of every lattice X (centre for gutters, start for cells)
    pos = 0
    for X in range(lat.W):
        if X % 2 == 0:
            xs.append(pos + 1)
            pos += gw
        else:
            xs.append(pos)
            pos += colw[X // 2]
    width = pos
    canvas = [[" "] * width for _ in range(lat.H)]

    def cx(X):
        return xs[X] + (colw[X // 2] // 2 if X % 2 == 1 else 0)

    def put(x, y, ch):
        if 0 <= y < lat.H and 0 <= x < width:
            canvas[y][x] = ch

    for p in paths:
        for k, (a, b) in enumerate(zip(p, p[1:])):
            x1, y1, x2, y2 = cx(a[0]), a[1], cx(b[0]), b[1]
            if x1 == x2:
                for y in range(min(y1, y2), max(y1, y2) + 1):
                    if canvas[y][x1] in "-+":
                        put(x1, y, "+")
                    elif canvas[y][x1] == " ":
                        put(x1, y, "|")
            else:
                for x in range(min(x1, x2), max(x1, x2) + 1):
                    if canvas[y1][x] in "|+":
                        put(x, y1, "+")
                    elif canvas[y1][x] == " ":
                        put(x, y1, "-")
            if k > 0:
                put(x1, y1, "+")
        if arrows and len(p) >= 2:
            a, b = p[-2], p[-1]
            nid = ids_at.get(((b[1] - 1) // 2, (b[0] - 1) // 2), "")
            if a[0] == b[0]:
                put(cx(b[0]), b[1] + (-1 if b[1] > a[1] else 1), "v" if b[1] > a[1] else "^")
            elif b[0] > a[0]:
                put(xs[b[0]] - 1, b[1], ">")
            else:
                put(xs[b[0]] + len(nid) + 2, b[1], "<")
    for (r, c), nid in ids_at.items():
        X, Y = 2 * c + 1, 2 * r + 1
        text = "[" + nid + "]"
        for k, ch in enumerate(text):
            put(xs[X] + k, Y, ch)
    return "\n".join("".join(row).rstrip() for row in canvas)
