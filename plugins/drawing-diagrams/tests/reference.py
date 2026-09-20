"""The routing of flow.plan as it stood before router.route_all, kept as an oracle.

Task 1 of the routing plan moves this loop into `router.route_all` unchanged, and task 12 replaces
its body with a search against an objective. A test that compared the router with itself would
prove nothing across either step, so the loop lives on here, where nothing under test can reach it.
This file is the only home of that loop: `router.route_all` is the search, and no other copy of the
three passes exists for a test to drift against.

Task 7 gives `router.Traffic` reference counts and a `remove`; today's class is copied here as
`OldTraffic`. The loop takes the traffic class as a parameter, so the same routing can be asked of
either class and the difference between the two answers is the class and nothing else.
"""
import support  # noqa: F401
from diagrams import router


class OldTraffic:
    """`router.Traffic` as it stood before task 7: a list of every segment of every path, scanned
    per question, with exits and entries per node side and the set of corners.

    `units` is the one field the frozen class gained. Task 9 prices a step along a unit edge of a
    line that already carries as many lines as it holds, and `route` reads that load off the
    traffic it is given, so a traffic without the field answers nothing at all. It is kept under
    the key `router.Traffic` uses, (axis, line, k) with k the lower coordinate, and it is the only
    answer taken from it: crosses, shares, corners, exits and entries still come from the segment
    list, which is what makes this class the oracle for them."""

    def __init__(self):
        self.segs = []      # (axis, line, lo, hi)
        self.units = {}     # (axis, line, k) -> lines along the unit edge from k to k + 1
        self.exits = {}     # (point, dir) -> count
        self.entries = {}   # (point, dir) -> count
        self.corners = set()  # every vertex of every path: where lines turn, start or end

    def add(self, path):
        segs = router.segments(path)
        self.segs.extend(segs)
        for axis, line, lo, hi in segs:
            for k in range(lo, hi):
                self.units[(axis, line, k)] = self.units.get((axis, line, k), 0) + 1
        self.corners.update(path[1:-1])
        if len(path) >= 2:
            d0 = router.STEPS[(_sign(path[1][0] - path[0][0]), _sign(path[1][1] - path[0][1]))]
            d1 = router.STEPS[(_sign(path[-1][0] - path[-2][0]), _sign(path[-1][1] - path[-2][1]))]
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


def reference_route_all(lat, ends, labelled, traffic_cls=OldTraffic):
    """One pass over `ends` in the given order with accumulating traffic, then two rip-up passes
    in which every line sees all the others. `ends[i]` is (source point, target point) and
    `labelled[i]` says whether the edge carries a label; the result holds one path per end pair,
    None where there is no route. An edge with no route takes no part in the rip-up passes.

    `traffic_cls` is the class the loop holds its lines in — `OldTraffic` by default, and
    `router.Traffic` where a caller asks this same loop of the class that replaced it. Only `add`
    and the questions `route` puts are used, so both classes answer it."""
    paths, live = [], []
    traffic = traffic_cls()
    for i, (src, dst) in enumerate(ends):
        p = router.route(lat, src, dst, labelled=labelled[i], traffic=traffic)
        paths.append(p)
        if p is not None:
            traffic.add(p)
            live.append(i)
    for _ in range(2):
        for i in live:
            others = traffic_cls()
            for j in live:
                if j != i:
                    others.add(paths[j])
            p = router.route(lat, ends[i][0], ends[i][1], labelled=labelled[i], traffic=others)
            if p is not None:
                paths[i] = p
    return paths
