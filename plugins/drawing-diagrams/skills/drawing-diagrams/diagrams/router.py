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
    passing through another line's corner +4,
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


def assign_offsets(paths, step=8, nodes=frozenset()):
    """Spread edges that share a line. Returns, per path, a list of (ox, oy)
    pixel offsets for each of its points.

    Overlapping segments on one line get distinct slots. The order of the
    slots follows where each line turns: on a horizontal run the line that
    turns down lies below the one that continues, the line that turns up lies
    above; on a vertical run the line that turns right lies to the right. So
    a fan of lines leaving one node never crosses itself when it spreads."""
    # per path: segments with the direction of the neighbouring segment at each end
    items = {}  # (axis, line) -> list of dicts
    for i, p in enumerate(paths):
        segs = list(zip(p, p[1:]))
        for k, (a, b) in enumerate(segs):
            axis = "v" if a[0] == b[0] else "h"
            line = a[0] if axis == "v" else a[1]
            lo_pt, hi_pt = (a, b) if (a[1] if axis == "v" else a[0]) <= (b[1] if axis == "v" else b[0]) else (b, a)
            lo = lo_pt[1] if axis == "v" else lo_pt[0]
            hi = hi_pt[1] if axis == "v" else hi_pt[0]

            def side_at(pt):
                # which side of the line the path continues to at this endpoint: -1 up/left, +1 down/right, 0 none
                for j in (k - 1, k + 1):
                    if 0 <= j < len(segs):
                        c, d = segs[j]
                        other = d if c == pt else c if d == pt else None
                        if other is None:
                            continue
                        val = (other[1] - pt[1]) if axis == "h" else (other[0] - pt[0])
                        if val:
                            return 1 if val > 0 else -1
                return 0

            items.setdefault((axis, line), []).append(
                {"i": i, "lo": lo, "hi": hi, "lo_side": side_at(lo_pt), "hi_side": side_at(hi_pt)})

    slot = {}   # (axis, line, path index) -> (slot, width)
    for key, segs in items.items():
        segs.sort(key=lambda d: (d["lo"], d["hi"]))
        axis, line = key

        def touches_in_gutter(d, reach):
            # two lines meeting end to end: at a node they simply join it, in a gutter they form a
            # junction that must be spread apart
            if d["lo"] != reach:
                return False
            pt = (line, reach) if axis == "v" else (reach, line)
            return pt not in nodes

        # connected groups of overlapping intervals
        groups, cur, reach = [], [], None
        for d in segs:
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
                slot[(key[0], key[1], g[0]["i"])] = (0, 1)
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

            ordered = sorted(g, key=lambda d: (pref(d), (-(d["hi"] - d["lo"]) if pref(d) > 0 else (d["hi"] - d["lo"]))))
            for n, d in enumerate(ordered):
                slot[(key[0], key[1], d["i"])] = (n, len(ordered))

    def off(axis, line, i):
        sw = slot.get((axis, line, i))
        if sw is None:
            return 0.0
        n, w = sw
        return round((n - (w - 1) / 2) * step, 1)

    result = []
    for i, p in enumerate(paths):
        pts = []
        for (x, y) in p:
            pts.append((off("v", x, i), off("h", y, i)))
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
    in swapped order. assign_offsets draws a shared stretch as parallel lines,
    each at an end of it on the side its path arrives from or leaves to
    (side_at): p left of q at one end and right of it at the other cross.
    A stretch runs on through a corner both paths turn together; sides are
    taken against the direction of travel, which such a corner keeps. An end
    where both paths meet their node puts no order."""
    rp, rq = _refine(p, q), _refine(q, p)
    at = {pt: k for k, pt in enumerate(rq)}
    n, k = 0, 0
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
        if first * last < 0:
            n += 1
    return n


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
