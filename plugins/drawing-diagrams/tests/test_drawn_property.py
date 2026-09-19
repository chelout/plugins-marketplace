"""The invariant: the renderer draws exactly the crossings it counts.

For every set of paths the router can produce, with `offs = assign_offsets(paths, nodes=nodes)`:
`drawn_crossings(paths, offs, nodes) == crossings(paths)` and `drawn_overlaps(paths, offs, nodes)
== 0`. Seeded instances of the published generator are routed the way `flow.plan` routes a model
and the invariant is asserted on every one of them, under every room of ROOMS: the pitch a group
is drawn at changes how far apart its lines stand, never their order, so the invariant has to hold
at 6 px and at 5 px exactly as it does at 8.

The test knows `route_all`, `assign_offsets`, `crossings` and the two counters, and nothing about
how the offsets are found, so it guards any later ordering algorithm as well. A failure is a defect
of the renderer, never a message to the author: it prints the smallest failing instance as the two
lines a regression case of `tests/test_crossings.py` is written from.
"""
import collections
import unittest

import support  # noqa: F401
import instances
from diagrams import router

# 300 instances, the floor of the invariant's test, with the seeds fixed so a failure names one
SMALL = (20260918, 240)
DENSE = (20260919, 60)

# The rooms every instance is offset under, as Geometry.room states one: a pair on an even lattice
# line, nothing on an odd one. `roomy` is an inner gutter that closes a group of four to 6 px and
# one of five to 5 px, `tight` one that already takes 5 px for a group of three and draws a wider
# one over its capacity; the table they come from is tests/test_capacity.py's.
ROOMS = (("no room", None), ("roomy", (10, 10)), ("tight", (5, 5)))

Surveyed = collections.namedtuple("Surveyed", "name room paths nodes offsets drawn counted overlaps")


def route_instance(cols, rows, cells, edges):
    """One instance routed as `flow.plan` routes a model: a lattice over the cells, the ends of the
    edges in model order, and the paths of the edges that have a route — one without a route is
    dropped, as a draft plan drops it. Returns the paths and the points the cards sit on."""
    lat = router.Lattice(cols, rows, cells)
    ends = [(router.Lattice.point(*cells[a]), router.Lattice.point(*cells[b])) for a, b in edges]
    # a labelled edge prices its first step differently, so an instance holds both kinds
    labelled = [k % 3 == 0 for k in range(len(ends))]
    return [p for p in router.route_all(lat, ends, labelled) if p is not None], frozenset(lat.blocked)


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


if __name__ == "__main__":
    unittest.main()
