"""The routing objective: what a whole routing costs, and what one rerouted edge changes it by.

    Phi(P) = sum own(p) + sum_{p<q} pair(p, q) + 20 * overflow(P)     (spec 5.2, criterion C2)

`own` is the price `route` puts on a path when no other line is there, so it is held here against
the cost `route` itself reports — on a lattice that states no capacity and on one that does, where a
line holding nothing costs +20 a step whether or not anything runs along it (spec 5.2 as amended on
2026-09-20). `pair` is a different thing from `route`'s traffic surcharges and is not compared with
them: it is counted a second time here, from the segments of the two paths, and Phi against that
count. `delta` is held against the difference of two whole Phi — which is what the descent of task
12 will trust it for — and the `overflow` it restricts to the lattice lines the old and the new path
lie on against the difference of two whole-routing ones.

The states with room are planned the way `flow.plan` plans a model: the geometry comes from
`tests/test_drawn_property.py`, whose second population already builds one per configuration, and
only the lattice and the ends are built here, because a case has to reroute one edge against the
rest and that needs both.

Nothing calls any of this yet, so no render moves; what these tests guard is the arithmetic the
descent will make its decisions from.
"""
import collections
import itertools
import random
import unittest

import support  # noqa: F401
import instances
from diagrams import router
from test_drawn_property import CONFIGS, geometry_of, labelled_like, planned_population

# The instances `own` is held against `route`'s own cost on, as the plan names them.
OWN = (11, 100)

# The instances the direct count of Phi is written for: one Phi costs a term per pair of paths,
# counted twice over, so the population is a prefix of the one above rather than all of it.
COUNTED = 40

# The states the single-edge replacements are drawn from: seeded instances on a lattice that states
# no capacity, and every fourth instance of the planned population of `tests/test_drawn_property.py`
# under every configuration it names. The stride rather than a prefix, because that population lists
# its instances with an opened empty row last, and the band of such a row holds the narrowest rooms
# the lattice ever states — the lines that hold nothing at all, and the groups that are refused.
PLAIN = (21, 24)
PLANNED_STRIDE = 4
REPLACEMENTS = 200

# What share of the replacements with room has to see an overflow, before or after, for the term to
# be under test rather than merely present.
OVERFLOWING = 0.1

# What share of the replacements has to move the path at all: a proposal equal to the path it
# replaces has a delta of zero, which every implementation gets right.
MOVED = 0.25

# How a replacement is proposed, in the order the cases take them: against every other line, as the
# descent of task 12 will propose one; against none of them, which is the second start of spec 5.3;
# and against half of them, which moves a path the other two leave where it is.
PROPOSALS = ("ripup", "alone", "half")


def ends_of(cells, edges):
    return [(router.Lattice.point(*cells[a]), router.Lattice.point(*cells[b])) for a, b in edges]


def step_dir(a, b):
    """The direction of the step from a to b, as `router.STEPS` names it."""
    return router.STEPS[((b[0] > a[0]) - (b[0] < a[0]), (b[1] > a[1]) - (b[1] < a[1]))]


def zero_steps(lat, path):
    """The steps of the path along a lattice line that holds nothing at all. `route` charges +20
    for every one of them with or without traffic — a load of none is already the capacity — so
    `own` carries them too, and the difference between the two lattices is exactly 20 each."""
    n = 0
    for a, b in zip(path, path[1:]):
        cap = lat.cap_v[a[0]] if a[0] == b[0] else lat.cap_h[a[1]]
        if cap is not None and cap <= 0:
            n += abs(b[0] - a[0]) + abs(b[1] - a[1])
    return n


# One path as the terms of `pair` read it, counted here from `router.segments` alone.
Counted = collections.namedtuple("Counted", "path vs hs units inner corners exit entry")


def counted(path):
    segs = router.segments(path)
    return Counted(
        path,
        [s for s in segs if s[0] == "v"],
        [s for s in segs if s[0] == "h"],
        {(axis, line, k) for axis, line, lo, hi in segs for k in range(lo, hi)},
        # a point strictly inside a segment: what a crossing line meets between two corners
        {(line, k) if axis == "v" else (k, line)
         for axis, line, lo, hi in segs for k in range(lo + 1, hi)},
        set(path[1:-1]),
        (path[0], step_dir(path[0], path[1])),
        (path[-1], step_dir(path[-2], path[-1])))


def perpendicular(a, b):
    """Vertical segments of one strictly across horizontal segments of the other, both ways: the
    crossings `router.crossings` counts over the ordered pairs of two paths."""
    n = 0
    for u, v in ((a, b), (b, a)):
        for _, line, lo, hi in u.vs:
            for _, row, left, right in v.hs:
                if left < line < right and lo < row < hi:
                    n += 1
    return n


def direct_pair(a, b):
    """`pair` counted a second time, from the segments of the two paths (spec 5.2):

        10 * (perpendicular crossings + shared_swaps) + shared unit steps
        + 3 * (inner points of one on corners of the other, both ways)
        + 3 * [same exit side of one node] + 3 * [same entry side of one node]

    `shared_swaps` is the router's own: a stretch two paths enter and leave in swapped order is the
    one term of Phi that no count over segments can see, and `router.crossings` reads it the same
    way, which the harness check below holds it to."""
    return (10 * (perpendicular(a, b) + router.shared_swaps(a.path, b.path))
            + len(a.units & b.units)
            + 3 * (len(a.inner & b.corners) + len(b.inner & a.corners))
            + 3 * (a.exit == b.exit) + 3 * (a.entry == b.entry))


def direct_phi(infos, paths, nodes, room):
    """Phi counted a second time: the pair terms from the segments of every pair of paths, the
    overflow term as spec 5.2 states it — sum of max(0, width - capacity) over the groups
    `router.overfull` names — and `own` from `describe`, which the class above holds against the
    cost `route` reports."""
    counts = [counted(p) for p in paths]
    total = sum(info.own for info in infos)
    total += sum(direct_pair(a, b) for a, b in itertools.combinations(counts, 2))
    if room is not None:
        total += 20 * sum(max(0, width - cap)
                          for _, _, width, _, cap in router.overfull(paths, nodes, room))
    return total


# One routed diagram a replacement is measured in: the lattice and the ends, so an edge can be
# routed again against the others, and the paths, labels and descriptions of the edges that have a
# route — the ones a routing really holds, as a draft plan holds them.
Routed = collections.namedtuple("Routed", "name lat room ends labelled paths nodes infos")


def routed(name, lat, ends, labelled, room):
    found = [(e, lab, p) for e, lab, p in zip(ends, labelled, router.route_all(lat, ends, labelled))
             if p is not None]
    paths, labels = [p for _, _, p in found], [lab for _, lab, _ in found]
    return Routed(name, lat, room, [e for e, _, _ in found], labels, paths,
                  frozenset(lat.blocked),
                  [router.describe(lat, p, lab) for p, lab in zip(paths, labels)])


def plain_states():
    """The states without room: seeded instances on a lattice that states no capacity, so a delta
    there is the two sums of Phi and nothing else."""
    out = []
    for k, (cols, rows, cells, edges) in enumerate(instances.small(*PLAIN)):
        lat = router.Lattice(cols, rows, cells)
        ends = ends_of(cells, edges)
        out.append(routed(f"small #{k}", lat, ends, labelled_like(len(ends)), None))
    return out


def planned_lattice(config, cols, cells):
    """The lattice `flow.plan` builds for this configuration and the geometry it states its rooms
    from: the extent ends at the last occupied row, the rows of it without a card carry their band,
    and every line states the capacity of its room. The geometry itself is
    `tests/test_drawn_property.py`'s, which the planned population is already built with."""
    used = {r for r, _ in cells.values()}
    extent = max(used) + 1
    geo = geometry_of(config, cols, extent, [r for r in range(extent) if r not in used])

    def line_capacity(axis, line):
        room = geo.room(axis, line)
        return None if room is None else router.capacity(room)

    return geo, router.Lattice(cols, extent, cells, capacity=line_capacity)


def planned_instances():
    """The instances the states with room are built from: every PLANNED_STRIDE of the planned
    population, so the sample reaches the empty-row variants it ends with."""
    return planned_population()[::PLANNED_STRIDE]


def planned_states():
    """The states with room: every sampled instance under every configuration, routed against the
    capacities and offset against the rooms the planner really states."""
    out = []
    for name, (cols, _, cells, edges) in planned_instances():
        for config in CONFIGS:
            geo, lat = planned_lattice(config, cols, cells)
            ends = ends_of(cells, edges)
            out.append(routed(f"{name} {config[0]} {config[1]}", lat, ends,
                              labelled_like(len(ends)), geo.room))
    return out


def proposal(state, i, how):
    """A new path for edge i of a state, proposed the way the descent will propose one."""
    traffic = None
    if how != "alone":
        others = [p for j, p in enumerate(state.paths) if j != i]
        traffic = router.Traffic()
        for p in (others[:len(others) // 2] if how == "half" else others):
            traffic.add(p)
    src, dst = state.ends[i]
    return router.route(state.lat, src, dst, labelled=state.labelled[i], traffic=traffic)


# One replacement: the state it happens in, the edge it replaces, and the description of the path
# proposed for it.
Case = collections.namedtuple("Case", "state i new")


def cases(states, seed, count):
    """`count` single-edge replacements in a fixed order: the states in turn, an edge of each drawn
    from the seeded generator, and the proposals in turn. A proposal that finds no route — which a
    walled-in edge never has one of in the first place — is not a replacement and is dropped."""
    rng = random.Random(seed)
    out = []
    for k in range(count):
        state = states[k % len(states)]
        i = rng.randrange(len(state.paths))
        new = proposal(state, i, PROPOSALS[k % len(PROPOSALS)])
        if new is not None:
            out.append(Case(state, i, router.describe(state.lat, new, state.labelled[i])))
    return out


def replaced(case):
    """The descriptions of the routing after the replacement."""
    after = list(case.state.infos)
    after[case.i] = case.new
    return after


def touched_lines(case):
    """The lattice lines the old path or the new one has a run on, as (axis, line): the lines a
    delta may recompute its overflow on, and the only ones whose groups either path is in."""
    return {(axis, line) for p in (case.state.paths[case.i], case.new.path)
            for axis, line, _, _ in router.segments(p)}


class OwnIsTheCostRouteReports(unittest.TestCase):
    """`own` replays the step rules of `route` with no traffic, so `route`'s own cost for a path it
    found alone is the number it has to give."""

    def assertOwnIsReported(self, lat, ends, labelled):
        """Every edge routed alone, its reported cost against `own` of the path that cost it.
        Returns the paths, for the caller to check what the run exercised."""
        found = []
        for k, (src, dst) in enumerate(ends):
            cost = []
            p = router.route(lat, src, dst, labelled=labelled[k], cost=cost)
            if p is None:
                continue
            found.append(p)
            self.assertEqual(len(cost), 1, "route appends the cost of the path it returns, once")
            with self.subTest(edge=k, labelled=labelled[k]):
                self.assertEqual(router.describe(lat, p, labelled[k]).own, cost[0])
        return found

    def test_on_a_lattice_that_states_no_capacity(self):
        seen = 0
        for cols, rows, cells, edges in instances.small(*OWN):
            lat = router.Lattice(cols, rows, cells)
            ends = ends_of(cells, edges)
            labelled = labelled_like(len(ends))
            with self.subTest(cols=cols, rows=rows, edges=len(edges)):
                self.assertTrue(any(labelled), "harness: no labelled edge prices its first step")
                seen += len(self.assertOwnIsReported(lat, ends, labelled))
        self.assertGreater(seen, 10 * OWN[1], "harness: these instances route almost nothing")

    def test_on_a_lattice_with_capacities_a_line_that_holds_nothing_among_them(self):
        """The lattice `flow.plan` builds, where two thirds of the configurations state a line that
        holds nothing at all — a flow widget's top margin, a page's bottom margin under footnotes,
        the tightest lines of the band of an empty row. `own` is the cost `route` reports there
        too, and it prices no step `route` leaves unpriced: the difference from the same path on a
        lattice that states no capacity is 20 per step along such a line, which is none of them
        here. The price is what makes the router leave those lines alone, so a path that pays it is
        a path with no other way out, and the two cases below are where it has none."""
        holding_nothing = 0
        for name, (cols, _, cells, edges) in planned_instances():
            for config in CONFIGS:
                _, lat = planned_lattice(config, cols, cells)
                plain = router.Lattice(cols, lat.rows, cells)
                ends = ends_of(cells, edges)
                labelled = labelled_like(len(ends))
                holding_nothing += 0 in lat.cap_v + lat.cap_h
                with self.subTest(instance=name, config=config):
                    for p in self.assertOwnIsReported(lat, ends, labelled):
                        self.assertEqual(router.describe(lat, p, False).own
                                         - router.describe(plain, p, False).own,
                                         20 * zero_steps(lat, p))
        self.assertGreater(holding_nothing, 0, "harness: no lattice of this population states a "
                                               "line that holds nothing")

    def assertEveryWayOutIsPriced(self, cells, size, axis, src, dst, want):
        """A hand-made lattice on which every line of one axis holds nothing, so that the cheapest
        path has to run along such lines and pay +20 for each of its steps. `own` is the cost
        `route` reports for it, and that much more than the same path costs where no line states a
        capacity."""
        cols, rows = size
        lat = router.Lattice(cols, rows, cells, capacity=lambda a, line: 0 if a == axis else None)
        plain = router.Lattice(cols, rows, cells)
        cost = []
        p = router.route(lat, router.Lattice.point(*src), router.Lattice.point(*dst), cost=cost)
        self.assertEqual(p, want)
        self.assertEqual(zero_steps(lat, p), 4)
        self.assertEqual(router.describe(lat, p, False).own, cost[0])
        self.assertEqual(router.describe(lat, p, False).own,
                         router.describe(plain, p, False).own + 80)

    def test_a_hand_made_lattice_whose_columns_hold_nothing(self):
        # one column, three rows, a card at the top and one at the bottom: the path down the middle
        # pays for each of its four steps, and there is no way round a column that is not one
        self.assertEveryWayOutIsPriced({"a": (0, 0), "b": (2, 0)}, (1, 3), "v",
                                       (0, 0), (2, 0), [(1, 1), (1, 5)])

    def test_a_hand_made_lattice_whose_rows_hold_nothing(self):
        # the same three cells turned on their side, and the same four steps priced: a row line is
        # where an empty row's band and the outer row margins lie, and they hold nothing as readily
        self.assertEveryWayOutIsPriced({"a": (0, 0), "b": (0, 2)}, (3, 1), "h",
                                       (0, 0), (0, 2), [(1, 1), (5, 1)])


class PhiIsTheSumOfItsTerms(unittest.TestCase):
    """Phi against the terms of spec 5.2 counted directly: the crossings and the swaps of every
    pair, the unit steps they share, the corners of one another they pass through, the node sides
    they leave and enter together, and the slots their groups take past what their lines hold."""

    def assertPhiIsCounted(self, state):
        self.assertEqual(router.phi(state.infos, state.nodes, state.room),
                         direct_phi(state.infos, state.paths, state.nodes, state.room))

    def test_the_direct_count_reads_crossings_as_the_renderer_counts_them(self):
        """The harness check of the count above: the perpendicular crossings and the swapped
        stretches of every pair are what `router.crossings` reports for the whole routing, so the
        term Phi charges 10 for is the number the author is warned about."""
        for state in plain_states():
            counts = [counted(p) for p in state.paths]
            with self.subTest(instance=state.name):
                self.assertEqual(
                    sum(perpendicular(a, b) + router.shared_swaps(a.path, b.path)
                        for a, b in itertools.combinations(counts, 2)),
                    router.crossings(state.paths))

    def test_without_room(self):
        seen = 0
        for k, (cols, rows, cells, edges) in enumerate(instances.small(OWN[0], COUNTED)):
            lat = router.Lattice(cols, rows, cells)
            ends = ends_of(cells, edges)
            state = routed(f"small #{k}", lat, ends, labelled_like(len(ends)), None)
            seen += router.crossings(state.paths) > 0
            with self.subTest(instance=state.name):
                self.assertGreater(len(state.paths), 1, "harness: nothing to pair")
                self.assertPhiIsCounted(state)
        self.assertGreater(seen, COUNTED // 2, "harness: too few of these routings cross at all")

    def test_with_the_room_the_planner_states(self):
        over = 0
        for state in planned_states():
            over += router.overflow(state.infos, state.nodes, state.room) > 0
            with self.subTest(instance=state.name):
                self.assertPhiIsCounted(state)
        self.assertGreater(over, 0, "harness: no planned routing overflows, so the term Phi "
                                    "charges 20 for is never counted here")


class DeltaIsTheDifferenceOfTwoSums(unittest.TestCase):
    """What the descent asks once per proposal: the exact change of Phi when one edge takes another
    path, without a second whole sum."""

    @classmethod
    def setUpClass(cls):
        cls.plain = cases(plain_states(), 5202, REPLACEMENTS)
        cls.planned = cases(planned_states(), 5203, REPLACEMENTS)

    def assertDeltaIsTheDifference(self, found):
        for case in found:
            state = case.state
            with self.subTest(instance=state.name, edge=case.i):
                self.assertEqual(
                    router.delta(case.i, case.new, state.infos, state.nodes, state.room),
                    router.phi(replaced(case), state.nodes, state.room)
                    - router.phi(state.infos, state.nodes, state.room))

    def test_without_room(self):
        self.assertDeltaIsTheDifference(self.plain)

    def test_with_the_room_the_planner_states(self):
        self.assertDeltaIsTheDifference(self.planned)

    def test_the_restricted_overflow_is_the_difference_of_two_whole_ones(self):
        """The one term of Phi that is not pairwise additive. A delta recomputes it on the lattice
        lines where the old or the new path has a run and nowhere else — the groups of every other
        line hold the same runs of the same paths in the same order, so their slots cannot move —
        and a whole-routing `overfull` costs a scan of every pair of paths, once per proposal."""
        for case in self.planned:
            state, after, lines = case.state, replaced(case), touched_lines(case)
            with self.subTest(instance=state.name, edge=case.i):
                self.assertEqual(
                    router.overflow(after, state.nodes, state.room, lines)
                    - router.overflow(state.infos, state.nodes, state.room, lines),
                    router.overflow(after, state.nodes, state.room)
                    - router.overflow(state.infos, state.nodes, state.room))

    def test_the_replacements_exercise_the_terms(self):
        """What the cases have to hold for the three tests above to mean anything: paths that moved,
        since a proposal equal to the path it replaces has a delta of zero however it is computed,
        and enough replacements whose routing overflows before or after, since the overflow term is
        the one a difference of two pairwise sums cannot reach."""
        for name, found in (("without room", self.plain), ("with room", self.planned)):
            with self.subTest(cases=name):
                self.assertGreater(len(found), 9 * REPLACEMENTS // 10,
                                   "harness: too many proposals found no route at all")
                moved = [case for case in found if case.new.path != case.state.paths[case.i]]
                self.assertGreater(len(moved), MOVED * len(found),
                                   "harness: almost every proposal is the path it replaces")
        overflowing = [case for case in self.planned
                       if router.overflow(case.state.infos, case.state.nodes, case.state.room)
                       or router.overflow(replaced(case), case.state.nodes, case.state.room)]
        self.assertGreater(len(overflowing), OVERFLOWING * len(self.planned),
                           "harness: almost no replacement overflows before or after, so the term "
                           "the restriction is about is not tested")


if __name__ == "__main__":
    unittest.main()
