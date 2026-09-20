"""The invariant: the renderer draws exactly the crossings it counts.

For every set of paths the router can produce, with `offs = assign_offsets(paths, nodes=nodes)`:
`drawn_crossings(paths, offs, nodes) == crossings(paths)` and `drawn_overlaps(paths, offs, nodes)
== 0`. Seeded instances of the published generator are routed the way `flow.plan` routes a model
and the invariant is asserted on every one of them, under every room of ROOMS: the pitch a group
is drawn at changes how far apart its lines stand, never their order, so the invariant has to hold
at 6 px and at 5 px exactly as it does at 8.

Those rooms are a table, and `flow.plan` states one per lattice line: its lattice ends at the last
occupied row, every line of it carries the capacity of the room `flow.Geometry` gives it, and the
empty rows of that extent carry their band. That produces routes and groups a lattice without
capacities never produces, so a second population is planned the whole way the planner plans, under
the narrowest configurations the modes have. It is held to the invariant above and to one property
more: every offset of a group `router.overfull` does not name lies inside the room its lattice line
states, which is what ties the pitch a group is drawn at to the room it is drawn in.

The test knows `route_all`, `assign_offsets`, `crossings` and the two counters, and nothing about
how the offsets are found, so it guards any later ordering algorithm as well. A failure is a defect
of the renderer, never a message to the author: it prints the smallest failing instance as the
lines a regression case of `tests/test_crossings.py` is written from.
"""
import collections
import itertools
import unittest

import support  # noqa: F401
import instances
from diagrams import flow, router

# 300 instances, the floor of the invariant's test, with the seeds fixed so a failure names one
SMALL = (20260918, 240)
DENSE = (20260919, 60)

# The rooms every instance is offset under, as Geometry.room states one: a pair on an even lattice
# line, nothing on an odd one. `roomy` is an inner gutter that closes a group of four to 6 px and
# one of five to 5 px, `tight` one that already takes 5 px for a group of three and draws a wider
# one over its capacity; the table they come from is tests/test_capacity.py's.
ROOMS = (("no room", None), ("roomy", (10, 10)), ("tight", (5, 5)))

# The configurations the second population is planned under, as (kind, mode, footnotes): the two
# narrowest the mode tables have — a flow widget, whose top margin holds no line at all, and a
# swimlane widget, whose 18 px column gutters hold three — and a page with footnotes, whose bottom
# margin holds none either. `footnotes` stands for the model's list, which `flow.margin_room` reads
# for whether there are any.
CONFIGS = (("flow", "widget", ()), ("swimlane", "widget", ()), ("flow", "page", ("[1]",)))

# The prefix of each generator that population takes, and the stride the instances with an opened
# empty row are derived at. A configuration is part of the lattice, so every instance is routed once
# per configuration and routing is what costs: the population is trimmed here rather than by
# dropping one of the configurations the capacities differ most between.
PLANNED = (60, 15)
OPENED = 6

Surveyed = collections.namedtuple("Surveyed", "name room paths nodes offsets drawn counted overlaps")

# One instance of the second population under one configuration: `extent` is the drawn row count and
# `empty` its rows without a card, `named` the groups `router.overfull` refused, `checked` the
# offsets held against the room of their line and `spread` those of them that moved a line at all,
# `beyond` the ones that left their room.
Planned = collections.namedtuple(
    "Planned", "name config cols extent empty paths nodes offsets drawn counted overlaps "
               "named checked spread beyond")


def labelled_like(n):
    """Which of `n` edges in model order carry a label: a labelled edge prices its first step
    differently, so an instance holds both kinds."""
    return [k % 3 == 0 for k in range(n)]


def route_instance(cols, rows, cells, edges):
    """One instance routed as `flow.plan` routes a model: a lattice over the cells, the ends of the
    edges in model order, and the paths of the edges that have a route — one without a route is
    dropped, as a draft plan drops it. Returns the paths and the points the cards sit on."""
    lat = router.Lattice(cols, rows, cells)
    ends = [(router.Lattice.point(*cells[a]), router.Lattice.point(*cells[b])) for a, b in edges]
    return ([p for p in router.route_all(lat, ends, labelled_like(len(ends))) if p is not None],
            frozenset(lat.blocked))


def room_of(pair):
    """A room callable giving every even lattice line the same pair, or None for no room at all."""
    if pair is None:
        return None
    return lambda axis, line: None if line % 2 else pair


def survey():
    """Both generators, one Surveyed per instance and room, in generator order. An instance is
    routed once and offset once per room: routing is what costs, and the rooms differ only in how
    far apart the offsets stand."""
    out = []
    for name, made in (("small", instances.small(*SMALL)), ("dense", instances.dense(*DENSE))):
        for k, instance in enumerate(made):
            paths, nodes = route_instance(*instance)
            counted = router.crossings(paths)
            for room, pair in ROOMS:
                offs = router.assign_offsets(paths, nodes=nodes, room=room_of(pair))
                out.append(Surveyed(f"{name} #{k}", room, paths, nodes, offs,
                                    router.drawn_crossings(paths, offs, nodes), counted,
                                    router.drawn_overlaps(paths, offs, nodes)))
    return out


def regression_case(row):
    """The failing instance as the two lines a regression case is written from."""
    points = ", ".join(repr(p) for p in sorted(row.nodes))
    return f"paths = {row.paths!r}\nnodes = frozenset({{{points}}})"


def smallest(rows):
    """The smallest of the failing instances: fewest lines, then fewest points, then the first one
    the generators produced — a pasteable case, and the same one on every run."""
    return min(rows, key=lambda row: (len(row.paths), sum(len(p) for p in row.paths)))


def opened(instance, at):
    """The instance with row `at` of its grid emptied: every node from that row down moves one row
    further, which opens a row without a card inside the drawn extent — a leading one at 0, an
    interior one below it. The generators make such a row in about one small instance of six and in
    no dense one at all, and the band of one is where the rooms of the lattice are narrowest, so the
    population derives its own instead of asking `tools/instances.py` for a shape it does not make."""
    cols, rows, cells, edges = instance
    return cols, rows + 1, {nid: (r + 1 if r >= at else r, c) for nid, (r, c) in cells.items()}, edges


def planned_population():
    """The instances of the second population, named and in a fixed order: a prefix of each
    generator — the seeds of the first population, whose instance k depends on the seed and k alone,
    so a prefix is the same instances the whole run has — and, every OPENED of them, the same
    instance with a leading empty row and with an interior one."""
    base = [(f"small #{k}", instance)
            for k, instance in enumerate(itertools.islice(instances.small(*SMALL), PLANNED[0]))]
    base += [(f"dense #{k}", instance)
             for k, instance in enumerate(itertools.islice(instances.dense(*DENSE), PLANNED[1]))]
    out = list(base)
    out += [(f"{base[k][0]} leading", opened(base[k][1], 0)) for k in range(0, len(base), OPENED)]
    out += [(f"{base[k][0]} interior", opened(base[k][1], 1))
            for k in range(OPENED // 2, len(base), OPENED)]
    return out


def geometry_of(config, cols, rows, empty):
    """The `Geometry` `flow.plan` builds for this configuration: the mode of the kind, the card width
    it derives from the mode and the columns, the raw room of the two outer margins, and the rows of
    the drawn extent that hold no card."""
    kind, mode_name, footnotes = config
    mode = flow.mode_for(kind, mode_name, None)
    card_w = (mode["total"] - mode["pad_l"] - mode["pad_r"] - mode["gap"] * (cols - 1)) / cols
    return flow.Geometry(mode, card_w, cols, rows, *flow.margin_room(kind, mode_name, footnotes),
                         empty=empty)


def plan_instance(config, cols, cells, edges):
    """One instance planned as `flow.plan` plans a model: the lattice ends at the last occupied row,
    the rows of that extent without a card are the geometry's empty ones, every lattice line states
    what `router.capacity` makes of its room, and the paths that have a route are placed through
    `router.place`, which draws them in the order the search priced them in. Returns the geometry,
    those paths, the points the cards sit on, the drawn extent, its empty rows, the offsets the
    paths are drawn at and the groups the capacity check refuses."""
    used = {r for r, _ in cells.values()}
    extent = max(used) + 1
    empty = [r for r in range(extent) if r not in used]
    geo = geometry_of(config, cols, extent, empty)

    def line_capacity(axis, line):
        room = geo.room(axis, line)
        return None if room is None else router.capacity(room)

    lat = router.Lattice(cols, extent, cells, capacity=line_capacity)
    ends = [(router.Lattice.point(*cells[a]), router.Lattice.point(*cells[b])) for a, b in edges]
    labelled = labelled_like(len(ends))
    found = [(end, lab, p) for end, lab, p
             in zip(ends, labelled, router.route_all(lat, ends, labelled)) if p is not None]
    paths, nodes = [p for _, _, p in found], frozenset(lat.blocked)
    offsets, over = router.place([end for end, _, _ in found], [lab for _, lab, _ in found],
                                 paths, nodes, geo.room)
    return geo, paths, nodes, extent, empty, offsets, over


def room_check(geo, paths, offsets, over):
    """Every offset against the room its lattice line states: how many were held against one, how
    many of those moved their line at all, and the ones that ended up outside it as
    (axis, line, offset, room).

    A group `router.overfull` names is drawn as tightly as lines can be drawn and still reaches past
    its room — that is the error the author is told about, not a defect of the pitch — so the lines
    it names are left out. It names a group by the lattice line it lies on, which is the granularity
    this side has: two groups on one line are left out together."""
    named = {(axis, line) for axis, line, *_ in over}
    checked, spread, out = 0, 0, []
    for path, offs in zip(paths, offsets):
        for (x, y), (nx, _), (ox, oy) in zip(path, path[1:], offs):
            # a segment reads one offset, on its own axis, and both of its points carry that one
            axis, line, off = ("v", x, ox) if x == nx else ("h", y, oy)
            room = geo.room(axis, line)
            if room is None or (axis, line) in named:
                continue
            checked += 1
            spread += off != 0
            if not (-room[0] <= off <= room[1]):
                out.append((axis, line, off, room))
    return checked, spread, out


def planned_survey():
    """The second population, one Planned per instance and configuration. Nothing is shared between
    the configurations the way the rooms of the first survey share a routing: the capacity of a line
    belongs to the lattice, so each configuration routes its own paths."""
    out = []
    for name, (cols, _, cells, edges) in planned_population():
        for config in CONFIGS:
            geo, paths, nodes, extent, empty, offs, over = plan_instance(config, cols, cells, edges)
            checked, spread, beyond = room_check(geo, paths, offs, over)
            out.append(Planned(name, config, cols, extent, empty, paths, nodes, offs,
                               router.drawn_crossings(paths, offs, nodes), router.crossings(paths),
                               router.drawn_overlaps(paths, offs, nodes),
                               len(over), checked, spread, beyond))
    return out


def planned_case(row):
    """The failing instance as the lines a regression case is written from: the two of
    `regression_case`, and the geometry its offsets were assigned under."""
    return (f"{regression_case(row)}\n"
            f"geo = geometry_of({row.config!r}, {row.cols}, {row.extent}, {row.empty!r})")


class DrawnEqualsCounted(unittest.TestCase):
    """What `assign_offsets` draws is what `crossings` counts, and no two lines share a slot."""

    @classmethod
    def setUpClass(cls):
        cls.surveyed = survey()

    def test_every_instance_draws_what_it_counts(self):
        bad = [row for row in self.surveyed if row.drawn != row.counted or row.overlaps]
        if bad:
            row = smallest(bad)
            self.fail(f"{len(bad)} of {len(self.surveyed)} instances draw something other than they "
                      f"count\nsmallest {row.name} ({row.room}): drawn {row.drawn}, counted "
                      f"{row.counted}, overlaps {row.overlaps}\n{regression_case(row)}")

    def test_the_instances_exercise_the_invariant(self):
        """The test above passes on an instance that draws nothing, so the population is checked
        here: a routing that lost its lines, or one with no crossing to place, would prove nothing.
        Kept out of that test so a degenerate population fails loudly instead of being read as the
        expected failure."""
        self.assertEqual(len(self.surveyed), (SMALL[1] + DENSE[1]) * len(ROOMS))
        thin = [row.name for row in self.surveyed if len(row.paths) < 2]
        self.assertEqual(thin, [], "harness: an instance with fewer than two lines counts nothing")
        crossing = [row.name for row in self.surveyed if row.counted]
        self.assertGreater(len(crossing), 2 * len(self.surveyed) // 3,
                           "harness: too few instances have a crossing to draw")

    def test_the_rooms_narrow_some_pitches(self):
        """A room that left every offset where it was would add copies of the run above and no
        coverage of its own, so each of them has to move lines, and between them they have to draw
        the half-pixel offsets a group of an even width takes at the 5 px pitch."""
        plain = {row.name: row.offsets for row in self.surveyed if row.room == ROOMS[0][0]}
        for room, _ in ROOMS[1:]:
            moved = [row.name for row in self.surveyed
                     if row.room == room and row.offsets != plain[row.name]]
            self.assertGreater(len(moved), 10, f"harness: the {room} room narrowed almost no pitch")
        halves = [row.name for row in self.surveyed
                  if any(o % 1 for pts in row.offsets for pt in pts for o in pt)]
        self.assertTrue(halves, "harness: no group of an even width took the 5 px pitch, so the "
                                "half-pixel offsets are never drawn here")


class PlannedTheWayFlowPlans(unittest.TestCase):
    """The same invariant on the population the planner really produces — a lattice of stated
    capacities over the drawn extent — and the pitch it is drawn at held against the room."""

    @classmethod
    def setUpClass(cls):
        cls.surveyed = planned_survey()

    def test_every_instance_draws_what_it_counts(self):
        bad = [row for row in self.surveyed if row.drawn != row.counted or row.overlaps]
        if bad:
            row = smallest(bad)
            self.fail(f"{len(bad)} of {len(self.surveyed)} planned instances draw something other "
                      f"than they count\nsmallest {row.name} {row.config}: drawn {row.drawn}, "
                      f"counted {row.counted}, overlaps {row.overlaps}\n{planned_case(row)}")

    def test_every_group_its_line_holds_is_drawn_inside_that_room(self):
        """What ties the pitch to the room: a group the line has room for is drawn inside it. The
        pitch is chosen from the width of the group, and the offsets are handed out from the pitch,
        so a line reaching past its room is a line over a card edge or out of the grid box — drawn,
        and with no capacity error to warn the author of it."""
        bad = [row for row in self.surveyed if row.beyond]
        if bad:
            row = smallest(bad)
            axis, line, off, room = row.beyond[0]
            self.fail(f"{sum(len(r.beyond) for r in bad)} offsets of {len(bad)} of "
                      f"{len(self.surveyed)} planned instances lie outside the room their line "
                      f"states\nsmallest {row.name} {row.config}: {off} px on the {axis} line "
                      f"{line}, which states {room}\n{planned_case(row)}")

    def test_the_instances_exercise_the_invariant(self):
        """What this population has to hold for the two tests above to mean anything: lines to
        cross, empty rows of both kinds inside a drawn extent — the narrowest rooms the lattice ever
        states — offsets really held against a room in every configuration, and a group `overfull`
        names, which is the one case the room test leaves out. Kept out of those tests so a
        degenerate population fails loudly instead of being read as the expected failure."""
        population = planned_population()
        self.assertEqual(len(self.surveyed), len(population) * len(CONFIGS))
        thin = [row.name for row in self.surveyed if len(row.paths) < 2]
        self.assertEqual(thin, [], "harness: an instance with fewer than two lines counts nothing")
        crossing = [row.name for row in self.surveyed if row.counted]
        self.assertGreater(len(crossing), 2 * len(self.surveyed) // 3,
                           "harness: too few instances have a crossing to draw")

        empty = {row.name for row in self.surveyed if row.empty}
        self.assertGreater(len(empty), len(population) // 4,
                           "harness: almost no instance has an empty row in its drawn extent")
        leading = {row.name for row in self.surveyed if row.empty and row.empty[0] == 0}
        interior = {row.name for row in self.surveyed if any(r > 0 for r in row.empty)}
        for kind, found in (("leading", leading), ("interior", interior)):
            self.assertGreater(len(found), 10, f"harness: too few instances have a {kind} empty row")

        named = [row.name for row in self.surveyed if row.named]
        self.assertGreater(len(named), 10, "harness: no group is ever refused, so the room test "
                                           "never leaves one out and says nothing about the case")
        self.assertGreater(len(self.surveyed) - len(named), len(self.surveyed) // 2,
                           "harness: most groups are refused, so the room test holds almost nothing")
        for config in CONFIGS:
            rows = [row for row in self.surveyed if row.config == config]
            with self.subTest(config=config):
                checked = sum(row.checked for row in rows)
                self.assertGreater(sum(row.spread for row in rows), checked // 3,
                                   "harness: this configuration leaves almost every line unmoved")
                self.assertTrue(any(o % 1 for row in rows for pts in row.offsets for pt in pts
                                    for o in pt),
                                "harness: no group of an even width took the 5 px pitch here")


if __name__ == "__main__":
    unittest.main()
