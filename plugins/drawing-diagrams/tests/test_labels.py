"""Where `flow.plan` stands a label, and what it says about it.

`diagrams/labels.py` places every label now: `flow.plan` hands `labels.place` the routed edges and
their texts and gets a `Choice` each — the place it took, the warnings that place raises with their
owners, or the room when the text fits nowhere — and writes the messages from them. The equivalence
this file used to hold, the model walked beside `flow.room_beside`, `flow.band_obstacles`,
`flow.under_card` and `flow.label_spots`, has nothing left to compare against: those functions are
gone with the switch.

What replaces it is a record. The whole corpus below — the shipped examples, the models of
`tests/test_label_lines.py` and a hundred seeded labelled instances, 174 plans — is planned once and
frozen: every place of every label of the label cases with what was said about it, the tally of the
seeded corpus, and the five instances the end-row reading of the switch moved. `python3
tests/test_labels.py --record` prints the whole of it from the tree it runs in, which is how it is
regenerated when the places move; the differential against the previous tree goes in that commit's
report, never here.

The places are the table of spec 7.2 as amended on 2026-09-21, and the choice among them is the
search of spec 7.3, which this commit filled in: `labels.place` is a bounded branch and bound over
the components of labels whose places can overlap, started from greedy's choice. `TheSearch` holds
it to costing no more than that start, to answering greedy when its allowance is one node, to
spending no more nodes than it was given, to solving a component apart from the others and to
finding what an exhaustive walk finds; `TheCostTheSearchMinimises` holds the cost itself, over
places built by hand, since no plan of the corpus ever has to choose between parting a pair of
labels and taking a line on; and the classes around them hold the table of places, what a label
answers for, and the two readings the switch carried.
"""
import copy
import functools
import itertools
import math
import re
import sys
import unittest

import support
import bench_routing
import instances
from diagrams import flow, labels, router
from diagrams.common import ModelError, label_width

import test_label_lines as cases

MODES = ("widget", "page")

# The hundred seeded labelled instances, and the labels they carry: every third edge, as the rest of
# the suite labels an instance (`tests/test_drawn_property.py`), with texts of four widths so the
# room is read at more than one length.
SEEDED = (20260921, 100)
SEEDED_MODE = "page"
TEXTS = ("да", "нет", "по ошибке", "ручная сверка данных")

LABEL_MESSAGE = re.compile(r"^(связь .*: подпись |связи .* и .*: подписи встанут )")

# What each message of a label is, by the word that tells it from the others: it lies on a line or
# on another label, it does not fit, a line runs through it where it stands over a horizontal second
# segment, or another label took its place first.
LIES, NO_FIT, CROSSES, SAME = "ляжет", "не помещается", "пересечёт", "одно место"

# What a plan says about the labels of one model: the place of each, as `place` below reads it off
# the anchor, and then the messages by their word. One string per model, and one entry per model of
# `tests/test_label_lines.py`; a pair where the two modes answer differently.
LABEL_CASES = {
    'a card alone in its row': 'a?->b R | a?->q R',
    'a line into the next card under a short card':
        ('a?->b R | a?->p R2 ; ляжет',
         'a?->b R | a?->p R2'),
    'a lone exit': 'a?->b R | a?->x A',
    'along the gutter over an exit up':
        ('a?->e U | a?->b R ; ляжет',
         'a?->e U | a?->b R'),
    'along the gutter, 4 away': 'a?->f U | a?->d R | a?->g A ; ляжет',
    'along the gutter, 4 towards':
        ('a?->d R | a?->c A ; ляжет',
         'a?->d R | a?->c A'),
    'along the gutter, 8 towards': 'a?->b U | a?->g R ; ляжет',
    "along the row ['. b d', 'e . f', '. g .']": 'e->f B',
    "along the row ['d b .', 'f . e', '. g .']": 'e->f B',
    'an exit up that does not fit':
        'a?->d A | a?->c O | b->d U | c->b A | d->b O | d->c L ; ляжет, ляжет, пересечёт',
    'beside a second segment, a banded row': 'd->b R2 ; ляжет',
    'beside a second segment, a gutter row': 'a->c A | a->d L2 | e->c F ; ляжет',
    'exit down': 'a?->b L | a?->c O',
    'exit up': 'a?->d A | a?->c O | b->d U | c->b A | d->b O | d->c L ; ляжет, ляжет, пересечёт',
    "lines at the source card's own height, beside": 'a?->b R | a?->t A',
    "lines at the source card's own height, into":
        ('a?->b R | a?->t A ; ляжет',
         'a?->b R | a?->t B'),
    "loop ['. a', 'c b?', '. d'] c -> a": 'b?->c B | b?->d R',
    "loop ['. a', 'c b?', '. d'] c -> d": 'b?->c A | b?->d R',
    "loop ['a .', 'b? c', 'd .'] c -> a": 'b?->c B | b?->d R',
    "loop ['a .', 'b? c', 'd .'] c -> d": 'b?->c A | b?->d R',
    "loop back ['. a', 'c b?', '. d'] back": 'b?->c B | b?->d R',
    "loop back ['. a', 'c b?', '. d'] last": 'b?->c B | b?->d R',
    "loop back ['a .', 'b? c', 'd .'] back": 'b?->c A | b?->d R',
    "loop back ['a .', 'b? c', 'd .'] last": 'b?->c A | b?->d R',
    "loop below ['. a', 'c b?', 'e d']": 'b?->c A | b?->d R',
    "loop below ['a .', 'b? c', 'd e']": 'b?->c A | b?->d R',
    'past the right edge':
        ('a?->b L | a?->r A ; не помещается',
         'a?->b R | a?->r A'),
    'the next card limits the room':
        ('a?->b R | a?->t A ; не помещается',
         'a?->b R | a?->t A'),
    'through the gutter past the label': 'a?->c R4 | a?->b L',
    'turning from the far side, down': 'a?->b A | a?->c R',
    'turning from the far side, up': 'a?->c O | a?->b R',
    'two labels in one place':
        ('n00->n06 R | n01->n13 R4 | n04->n01 U | n07->n00 R2 | n09->n14 U | n11->n08 U | n14->n03 L2 | '
         'n15->n06 U ; ляжет, ляжет, ляжет, ляжет, не помещается',
         'n00->n06 L | n01->n13 U | n04->n01 U | n07->n00 F | n09->n14 U | n11->n08 U | n14->n03 L2 | '
         'n15->n06 F ; ляжет, ляжет, ляжет, ляжет, ляжет, ляжет, пересечёт, пересечёт, пересечёт, пересечёт, пересечёт'),
    "under the row's own line": 'c->a A',
}
SEEDED_PLACES = {'рядом со вторым отрезком': 161, 'над вторым отрезком': 103, 'под вторым отрезком': 68,
                 'у выхода вбок': 62, 'у выхода вниз': 34, 'у выхода вверх': 14}
SEEDED_SAID = {LIES: 89, NO_FIT: 24, CROSSES: 24}

# The five seeded instances the end-row reading moves, and what each moves: the label, where it
# stood before the switch and where it stands now. Named rather than counted, so a sixth one is a
# failure and not a number.
SEEDED_MOVED = {
    "seeded #12": ("n00 -> n03", ("R", 2), ("L", None)),
    "seeded #40": ("n00 -> n04", ("L", 4), ("R", None)),
    "seeded #57": ("n09 -> n03", ("R", 5), ("L", None)),
    "seeded #61": ("n05 -> n03", ("L", None), ("L", 6)),
    "seeded #97": ("n08 -> n06", ("L", 6), ("L", None)),
}


def said(warnings):
    """What a plan said about its labels, by the word of each message, sorted. A draft plan reports
    its layout errors as warnings and a fit error is a layout error, so the prefix comes off."""
    out = []
    for w in warnings:
        text = w[len(flow.DRAFT):] if w.startswith(flow.DRAFT) else w
        if LABEL_MESSAGE.match(text):
            out.append(next(word for word in (SAME, NO_FIT, CROSSES, LIES) if word in text))
    return sorted(out)


def beside(e):
    """(side, pinned lattice row) of a label beside a vertical second segment, read off the anchor
    the edge carries: `la` is (pt, ref, Y, dx, dy, anchor) of spec 7.4, the text runs rightwards
    from the line when `dx` is positive, and the row is None where the anchor takes the middle of
    the segment instead of the base of a row."""
    _, ref, Y, dx = e["la"][:4]
    return ("R" if dx > 0 else "L"), (Y if ref == "r" else None)


def place(e):
    """The place of a labelled edge as the record below names it, read off the anchor it carries —
    one letter per place of the table of spec 7.2:

    `R`, `L`   right or left of the line of a straight exit down or up
    `A`, `B`   above or below the line of a straight sideways exit
    `O`, `U`   over or under a horizontal second segment, just after the bend
    `F`        over a horizontal second segment at its far end
    `R2`, `L`  beside a vertical second segment: the side, with the row it is pinned to when it has
               one, and the side alone where the anchor takes the middle of the segment instead
    """
    pt, ref, _, dx, dy, _ = e["la"]
    if pt == 2:
        return "F"
    if pt == 1 and ref == "p":
        return "O" if dy < 0 else "U"
    if pt == 0:
        if e["sa"] in ("L", "R"):
            return "A" if dy < 0 else "B"
        return "R" if dx > 0 else "L"
    side, row = beside(e)
    return side + ("" if row is None else str(row))


def digest(layout, warnings):
    """A plan's labels as `LABEL_CASES` records them."""
    spots = [f"{e['a']}->{e['b']} {place(e)}" for e in layout["edges"] if e["label"]]
    words = said(warnings)
    return " | ".join(spots) + (" ; " + ", ".join(words) if words else "")


def inputs(layout, mode_name):
    """What `flow.plan` hands `labels.place`, read back off the layout it returns: the geometry, the
    paths of the edges that routed, their offsets, the cells of the grid and the occupied ones."""
    geo = flow.Geometry(layout["mode"], layout["card_w"], layout["grid_cols"], layout["grid_rows"],
                        *flow.margin_room(layout["kind"], mode_name, layout["footnotes"]),
                        empty=layout["empty_rows"])
    offsets = [[(pt[2], pt[3]) for pt in e["path"]] for e in layout["edges"]]
    occupied = {rc for nid, rc in layout["cells"].items() if nid in layout["nodes"]}
    return geo, layout["paths"], offsets, layout["cells"], occupied


def candidates(layout, mode_name):
    """The places of every label of a layout, per edge, with what `greedy` measures them against:
    the cards and the bounds, the lines, the widths and the vertical runs."""
    geo, paths, offsets, cells, occupied = inputs(layout, mode_name)
    edges, card_w = layout["edges"], layout["card_w"]
    rects = labels.occupancy(cells, paths, offsets, geo, occupied)
    order = sorted((i for i, e in enumerate(edges) if e["label"]),
                   key=lambda i: len(paths[i]) >= 3 and paths[i][2][1] != paths[i][1][1])
    needs = {i: label_width(edges[i]["label"]) for i in order}
    cands = {i: labels.candidates(i, edges[i], paths[i], needs[i], paths, offsets, geo, cells,
                                  occupied, card_w) for i in order}
    return (order, cands, needs,
            [r for r in rects if r.kind in (labels.CARD, labels.BOUND)],
            [r for r in rects if r.kind == labels.LINE],
            labels.uprights(paths))


def chosen(layout, mode_name, exempt=True, nodes=labels.NODES):
    """The choices of a layout, by the road `labels.place` itself takes — the search of spec 7.3.
    `exempt=False` takes the exemptions of spec 7.1 off every candidate, which is what the test of
    them needs, and `nodes` is the allowance the search is given."""
    order, cands, needs, cards, runs, upright = candidates(layout, mode_name)
    if not exempt:
        cands = {i: [c._replace(exempt=frozenset()) for c in cs] for i, cs in cands.items()}
    return labels.search(order, cands, needs, cards, runs, upright, nodes)[0]


def greedily(layout, mode_name):
    """The choices greedy makes on a layout: the first place with the room for each label, in
    today's order, which is where the search of spec 7.3 starts from."""
    order, cands, needs, cards, runs, upright = candidates(layout, mode_name)
    return labels.greedy(order, cands, needs, cards, runs, upright)


def price(order, took, runs):
    """What a complete choice of places costs, straight from the places themselves: the tuple of
    spec 7.3, counted here rather than taken from `labels.cost`, so an exhaustive walk can price a
    choice nothing ever wrote a verdict about. It is that function's independent check as well —
    the line edges are counted here in this file's own words, and
    `test_the_cost_of_a_choice_is_what_this_file_prices_it_at` holds the two answers together."""
    picked = [took[i] for i in sorted(order)]
    pairs = sum(1 for k, a in enumerate(picked) for b in picked[k + 1:] if labels.meet(a, b))
    lines = sum(len({owner[0] for owner in labels.hits(c, runs)}) for c in picked)
    return pairs, lines, sum(c.rank for c in picked)


def segment_price(order, took, runs):
    """What the same choice costs when a line's rectangles are counted one by one instead of its
    edge — the reading spec 7.3 forbids ("a line edge counts once per candidate however many of its
    rectangles are hit"), kept here as the premise of the instances it left the search dearer on
    than the greedy choice it starts from."""
    picked = [took[i] for i in sorted(order)]
    pairs = sum(1 for k, a in enumerate(picked) for b in picked[k + 1:] if labels.meet(a, b))
    return pairs, sum(len(labels.hits(c, runs)) for c in picked), sum(c.rank for c in picked)


def post_check(layout):
    """The (label, path) pairs the check before the switch warned about: a line whose lattice column
    lies strictly inside a horizontal second segment and which spans the row of that segment,
    wherever along it the text stands and wherever the line stops."""
    paths = layout["paths"]
    segs = [router.segments(q) for q in paths]
    out = []
    for i, (e, p) in enumerate(zip(layout["edges"], paths)):
        if not e["label"] or len(p) < 3 or p[2][1] != p[1][1]:
            continue
        y, x1, x2 = p[1][1], min(p[1][0], p[2][0]), max(p[1][0], p[2][0])
        out += [(i, j) for j, other in enumerate(segs) if j != i
                for axis, line, lo, hi in other if axis == "v" and x1 < line < x2 and lo < y < hi]
    return sorted(out)


def planned(corpus):
    """Every model of a corpus planned as a draft — the only plan that answers for a model whose
    label does not fit — with its layout and what it said about its labels."""
    for name, model, mode in corpus:
        layout, warnings = flow.plan(copy.deepcopy(model), mode, draft=True)
        yield name, mode, layout, warnings


@functools.lru_cache(maxsize=None)
def examples():
    return tuple((f"{path.name} {mode}", model, mode)
                 for path, model in bench_routing.examples() for mode in MODES)


@functools.lru_cache(maxsize=None)
def label_models():
    """The models of `tests/test_label_lines.py`, in the order its cases read them: the loop models
    of a straight sideways exit, the exit models of a straight exit down or up, the short-card
    models and the two beside-a-second-segment ones."""
    out = [(f"loop {grid} {last}", cases.loop_model(grid, cases.EDGES + [last]))
           for last in ("c -> a", "c -> d") for grid in cases.ABOVE]
    out += [(f"loop back {grid} {first}", cases.loop_model(grid, edges))
            for grid in cases.ABOVE
            for first, edges in (("back", ["c -> b?"] + cases.EDGES),
                                 ("last", cases.EDGES + ["c -> b?"]))]
    out += [(f"loop below {grid}", cases.loop_model(grid, cases.EDGES + ["c -> e", "e -> b?"]))
            for grid in cases.BELOW]
    out += [(f"along the row {grid}",
             cases.exit_model(grid, ["e -> f : да", "e -> d", "f -> b", "f -> g"]))
            for grid in (["d b .", "f . e", ". g ."], [". b d", "e . f", ". g ."])]
    out += [("under the row's own line",
             cases.exit_model(["c . a", "d b e", "f . ."],
                              ["b -> c", "c -> a : да", "c -> e", "a -> c", "d -> c", "c -> b",
                               "c -> f"])),
            ("exit down", cases.DOWN),
            ("exit up", cases.UP),
            ("through the gutter past the label",
             cases.exit_model(["c .", "b .", ". e", "a? f"],
                              ["c -> a?", "a? -> c : да", "a? -> b : да", "e -> a?", "e -> f"],
                              terminals=("b", "f"))),
            ("a lone exit",
             cases.exit_model(["a? x", "b c"], ["a? -> b : да", "a? -> x : нет"],
                              terminals=("b", "c"))),
            ("turning from the far side, down",
             cases.exit_model(["a? b", "c d"],
                              ["b -> c", "d -> c", "a? -> b : да", "d -> b", "a? -> c : да"])),
            ("turning from the far side, up",
             cases.exit_model(["b e c", "a? f d", "g h i"],
                              ["b -> c", "a? -> c : да", "a? -> b : да", "b -> g", "g -> a?"])),
            ("along the gutter, 4 away",
             cases.exit_model(["f e a? g", "c h d b"],
                              ["a? -> f : да", "a? -> d : да", "b -> f", "g -> f", "a? -> g : да"])),
            ("along the gutter, 8 towards",
             cases.exit_model(["e h g b", "d c a? f"],
                              ["a? -> b : да", "g -> c", "d -> h", "a? -> g : да", "g -> f",
                               "d -> e", "f -> c", "e -> h"])),
            ("along the gutter, 4 towards",
             cases.exit_model(["c a? . f", "e d b ."],
                              ["e -> d", "b -> c", "a? -> d : да", "a? -> c : да", "f -> c",
                               "d -> c", "c -> e"])),
            ("along the gutter over an exit up",
             cases.exit_model([". e b c", ". f a? d"],
                              ["d -> c", "a? -> e : да", "e -> d", "b -> e", "a? -> b : да",
                               "b -> d", "d -> a?"])),
            ("past the right edge",
             cases.exit_model(["p q r a?", "s t u b"],
                              ["a? -> b : подтверждено вендором", "a? -> r : нет"])),
            ("an exit up that does not fit",
             cases.exit_model(cases.UP["grid"],
                              [e if e != "d -> c : да" else "d -> c : подтверждено вендором"
                               for e in cases.UP["edges"]])),
            ("a line into the next card under a short card",
             cases.exit_model(["p q . .", "a? t . .", "b . . ."],
                              ["a? -> b : сверка вручную", "a? -> p : нет", "q -> t", "p -> t"],
                              nodes=cases.TALL)),
            ("the next card limits the room",
             cases.exit_model([". q . .", "a? t . .", "b . . ."],
                              ["a? -> b : ручная сверка данных", "a? -> t : нет", "q -> t"],
                              nodes=cases.TALL)),
            ("a card alone in its row",
             cases.exit_model(["q . . .", "a? . . .", "b . . ."],
                              ["a? -> b : ручная сверка данных", "a? -> q : нет"],
                              nodes=cases.TALL)),
            ("lines at the source card's own height, beside",
             cases.exit_model(["a? . t .", "b . . ."],
                              ["a? -> b : ручная проверка", "a? -> t : нет"], nodes=cases.TALL)),
            ("lines at the source card's own height, into",
             cases.exit_model(["p q . .", "a? . t .", "b . . ."],
                              ["a? -> b : ручная проверка", "a? -> t : нет", "p -> a?", "q -> a?"],
                              nodes=cases.TALL)),
            ("beside a second segment, a banded row",
             cases.exit_model(["e a b", "d . c"],
                              ["e -> d", "c -> d", "c -> b", "d -> b : да", "d -> a", "a -> c",
                               "e -> c"], terminals=("b",))),
            # from the seeded stream past the hundred of the record (instance 104 of
            # `instances.small(SEEDED[0], …)`), which is where two labels first take one place: no
            # shipped example and none of the hundred reaches that warning
            ("two labels in one place",
             cases.exit_model(["n00 n01 n02 n03 n04 n05", "n06 n07 n08 n09 n10 n11",
                               "n12 n13 n14 n15 n16 n17"],
                              ["n00 -> n06 : да", "n00 -> n11", "n00 -> n12", "n01 -> n13 : нет",
                               "n02 -> n10", "n02 -> n13", "n04 -> n01 : по ошибке", "n04 -> n08",
                               "n05 -> n01", "n07 -> n00 : ручная сверка данных", "n07 -> n02",
                               "n07 -> n15", "n09 -> n14 : да", "n10 -> n00", "n11 -> n02",
                               "n11 -> n08 : нет", "n12 -> n14", "n13 -> n10",
                               "n14 -> n03 : по ошибке", "n15 -> n00", "n15 -> n02",
                               "n15 -> n06 : ручная сверка данных", "n15 -> n13", "n17 -> n16"])),
            ("beside a second segment, a gutter row",
             cases.exit_model([". . d e", ". b c a"],
                              ["a -> c : да", "a -> d : да", "d -> a", "e -> c : да", "b -> c",
                               "d -> b"], terminals=("e",)))]
    return tuple((f"{name} {mode}", model, mode) for name, model in out for mode in MODES)


@functools.lru_cache(maxsize=None)
def seeded():
    """A hundred seeded instances as labelled models: every third edge carries a label, and a model
    the renderer refuses outright is left out — there is no layout to read a label off."""
    out = []
    for k, (cols, rows, cells, edges) in enumerate(instances.small(*SEEDED)):
        model = bench_routing.model_from(cols, rows, cells, edges)
        model["edges"] = [f"{e} : {TEXTS[(i // 3) % len(TEXTS)]}" if i % 3 == 0 else e
                          for i, e in enumerate(model["edges"])]
        try:
            flow.plan(copy.deepcopy(model), SEEDED_MODE, draft=True)
        except ModelError:
            continue
        out.append((f"seeded #{k}", model, SEEDED_MODE))
    return tuple(out)


class WhatThePlansSay(unittest.TestCase):
    """Criterion E2, second half: `flow.plan` places its labels through `labels.place`, and this is
    what it then puts in the layout and in the warnings."""

    def test_the_label_cases_stand_where_this_record_says(self):
        for name, mode, layout, warnings in planned(label_models()):
            case = name.rsplit(" ", 1)[0]
            want = LABEL_CASES[case]
            with self.subTest(case=case, mode=mode):
                self.assertEqual(digest(layout, warnings),
                                 want if isinstance(want, str) else want[MODES.index(mode)])

    def test_the_seeded_corpus_comes_to_these_numbers(self):
        corpus = seeded()
        self.assertGreaterEqual(len(corpus), 90, "harness: too few seeded instances plan at all")
        places, words = {}, []
        for name, mode, layout, warnings in planned(corpus):
            for choice in chosen(layout, mode):
                places[choice.cand.where] = places.get(choice.cand.where, 0) + 1
            words += said(warnings)
        self.assertEqual(places, SEEDED_PLACES)
        self.assertEqual({w: words.count(w) for w in sorted(set(words))}, SEEDED_SAID)

    def test_the_five_instances_the_end_row_reading_moves(self):
        """The one class in which the switch places a label elsewhere (spec 7.1 as amended): a row
        the vertical second segment ends in. Each of the five is named with the place it used to
        take, and only the place it takes now is asserted — the other side of the pair is the tree
        before the switch, which the differential of task 20 commit 1 read once."""
        found = {}
        for name, mode, layout, _ in planned(seeded()):
            if name not in SEEDED_MOVED:
                continue
            edge, _, now = SEEDED_MOVED[name]
            e = next(x for x in layout["edges"] if f"{x['a']} -> {x['b']}" == edge)
            found[name] = beside(e)
        self.assertEqual(found, {name: now for name, (_, _, now) in SEEDED_MOVED.items()})

    def test_the_corpus_exercises_every_place(self):
        """What the record above has to hold to read anything: every place of the table of spec 7.2
        is taken somewhere in the corpus, a place that reaches into more than one row is taken too,
        and every kind of message a plan can write is heard at least once. A place is named here by
        its family and its rank in it.

        With the search of spec 7.3 the table is whole. The two places greedy could not reach on
        its own — under a horizontal second segment, and over it at its far end — have the same
        room as the place before them wherever all three stand in the gutter row, so nothing could
        tell them apart until something priced the lines each one meets; since spec 7.1 as amended
        a third time `fits` can also drop the place before them, and hand one of the two to greedy
        after all. The message this corpus no longer hears from a plan is the one about two labels
        in one place: a pair costs more than any number of lines or ranks, so the search parts them
        wherever either can move, and `TheSearch` holds the model where greedy still does not."""
        taken, rows, words = set(), set(), set()
        for name, mode, layout, warnings in planned(examples() + label_models() + seeded()):
            for choice in chosen(layout, mode):
                taken.add((choice.cand.where, choice.cand.rank if choice.cand.where != labels.BESIDE
                           else None))
                rows.add(len(choice.cand.rects) > 1)
            words |= set(said(warnings))
        self.assertEqual(taken, {(labels.DOWN, 0), (labels.DOWN, 1), (labels.UP, 0), (labels.UP, 1),
                                 (labels.SIDEWAYS, 0), (labels.SIDEWAYS, 1), (labels.OVER, 0),
                                 (labels.OVER, 2), (labels.BENEATH, 1), (labels.BESIDE, None)})
        self.assertEqual(rows, {True, False})
        self.assertEqual(words, {LIES, NO_FIT, CROSSES})

    def test_place_is_the_search_over_the_candidates(self):
        """The interface of this commit: `labels.place` is `labels.search` over
        `labels.candidates` and nothing else, so the road the tests above take is the one
        `flow.plan` takes."""
        for name, mode, layout, _ in planned(label_models()):
            geo, paths, offsets, cells, occupied = inputs(layout, mode)
            texts = [e["label"] for e in layout["edges"]]
            with self.subTest(case=name):
                self.assertEqual(labels.place(layout["edges"], texts, paths, offsets, geo, cells,
                                              occupied, layout["card_w"]),
                                 chosen(layout, mode))

    def test_flow_plan_writes_one_message_per_clash_and_emits_the_place_it_was_given(self):
        """Spec 7.3 as amended: a label raises one warning where it lies on a line or a label, one
        per line that runs through a text over a horizontal second segment, and one where another
        label took its place first — and a fit error where it fits nowhere. The advice of spec 6
        counts those warnings, so a plan that wrote more or fewer of them than the choices carry
        would change which moves it offers."""
        for name, mode, layout, warnings in planned(examples() + label_models() + seeded()):
            choices = chosen(layout, mode)
            word = {labels.ON_LINE: LIES, labels.CROSSED: CROSSES, labels.SAME_PLACE: SAME}
            want = [word[c.kind] for choice in choices for c in choice.clashes]
            want += [NO_FIT for choice in choices if choice.room is not None]
            with self.subTest(model=name):
                self.assertEqual(said(warnings), sorted(want))
                self.assertEqual({choice.edge: choice.cand.la for choice in choices},
                                 {i: e["la"] for i, e in enumerate(layout["edges"]) if e["label"]})
                self.assertEqual([e for e in layout["edges"] if "la" in e and not e["label"]], [])


# The model of a straight exit down in the last column of its grid: the room right of the line ends
# at the edge of the drawn area, and left of it the row is empty as far as the text reaches.
LAST_COLUMN = cases.exit_model(["p q . a?", "s t u b"],
                               ["a? -> b : ручная сверка данных", "a? -> q : нет"])

# The model of a branch label over a horizontal second segment: a -> f leaves a downwards, turns
# along the gutter row under the cards and turns again into f. Every other edge is there to fill the
# row, so the segment is drawn off the base of it and the two are told apart.
BRANCH = cases.exit_model(["a b c", "d e f", "g h i"],
                          ["a -> f : да", "b -> d", "c -> e", "d -> h", "e -> g", "f -> i"])

# The seeded instances where one line edge is met in several rows of one place, with the edge whose
# label meets it and how many rows of that place it is met in: a label beside a vertical second
# segment, and a label under a card shorter than its row, which stands in the gutter and reaches
# into the row as well. The first of the two used to be seeded #15's n12 -> n08, which meets no line
# any more: the line it met was one ending at a bend drawn 12 px off the base of a gutter row, and
# a run read where its bend is drawn (spec 7.1 as amended) never reaches that text.
MET_IN_ROWS = {"seeded #64": ("n08 -> n00", 2), "seeded #38": ("n09 -> n12", 2)}

# The model of a label that has to give way to one already placed: `e -> d` leaves sideways along
# the bottom row and its text stands there, and `d -> c`, which comes later, would take the middle
# of its own vertical second segment — a place reaching into that same row, where the text it finds
# leaves it too little. The shape is the shipped example `four-blocks`, whose labels are this long
# and whose cards leave this much room beside them.
GIVE_WAY = cases.exit_model(["a . b", ". c .", "d . e"],
                            ["c -> d : 1 читает approved", "c -> a : 2 сверяет снимки",
                             "c -> e : 3-4 попытки, fire", "c -> b : 4a блокировка?",
                             "e -> d : 5 approved | dashed", "d -> c : 6 resume: covered"])


class TheTableOfPlaces(unittest.TestCase):
    """Spec 7.2 as amended on 2026-09-21, criterion E3: the places of the table, preferred first,
    with the ones this commit adds. A label that had nowhere to stand beside its line now has the
    other side of it, and a label on a horizontal second segment stands just after the bend."""

    def test_a_straight_exit_down_in_the_last_column_stands_left_of_its_line(self):
        """Criterion E3's first case. Right of the line the text runs out of the drawn area, which
        is a fit error and all today had to offer; left of it the row is empty as far as it reaches.
        On a page the same cards are wide enough that the preferred place still has the room, so the
        label stays where it was: the second place is taken because the first has no room, never
        because it is there."""
        for mode, dx, anchor in (("widget", -labels.LABEL_BESIDE, "end"),
                                 ("page", labels.LABEL_BESIDE, "start")):
            layout, warnings = flow.plan(copy.deepcopy(LAST_COLUMN), mode, draft=True)
            with self.subTest(mode=mode):
                e = next(x for x in layout["edges"] if (x["a"], x["b"]) == ("a?", "b"))
                self.assertEqual(len(e["path"]), 2, f"premise: {e['a']} -> {e['b']} no longer "
                                                    f"leaves straight down: {e['path']}")
                self.assertEqual(e["la"], (0, "p", 0, dx, labels.LABEL_BELOW, anchor))
                self.assertEqual(said(warnings), [], warnings)
        # the premise of the widget case, read off the rooms rather than off the outcome: the
        # preferred place has less room than the text needs and the one left of the line has more
        layout, _ = flow.plan(copy.deepcopy(LAST_COLUMN), "widget", draft=True)
        order, cands, needs, cards, runs, _ = candidates(layout, "widget")
        i = next(k for k in order if layout["edges"][k]["b"] == "b")
        right, left = cands[i][0], cands[i][1]
        self.assertEqual((right.grow, left.grow), ("R", "L"))
        self.assertLess(labels.room(right, cards), needs[i])
        self.assertGreaterEqual(min(labels.room(left, cards), labels.room(left, runs)), needs[i])

    def test_a_branch_label_over_a_horizontal_second_segment_sits_after_the_bend(self):
        """Criterion E3's second case, and the owner's ruling Q4: the text starts LABEL_BEND past
        the bend and grows away from the source, where it used to end LABEL_BEND before the far end
        and grow back towards it."""
        for mode in MODES:
            layout, warnings = flow.plan(copy.deepcopy(BRANCH), mode, draft=True)
            with self.subTest(mode=mode):
                i, e = next((k, x) for k, x in enumerate(layout["edges"])
                            if (x["a"], x["b"]) == ("a", "f"))
                p = layout["paths"][i]
                self.assertEqual((len(p), p[1][1] == p[2][1], p[2][0] > p[1][0]), (4, True, True),
                                 f"premise: {p} is no longer a turn into a horizontal second "
                                 f"segment running rightwards")
                self.assertEqual(e["la"], (1, "p", 0, labels.LABEL_BEND, -labels.LABEL_OVER,
                                           "start"))
                geo, paths, offsets, cells, occupied = inputs(layout, mode)
                bend = geo.clamp(cells["a"][1], geo.x(p[1][0]) + offsets[i][1][0])
                spot = next(c for c in chosen(layout, mode) if c.edge == i).cand
                self.assertEqual(spot.rects[0].x0, bend + labels.LABEL_BEND)
                self.assertEqual(said(warnings), [], warnings)

    def test_the_three_places_of_a_horizontal_second_segment_are_offered_in_order(self):
        """The whole row of the table: over the segment just after the bend, under it just after
        the bend, over it at its far end. Each is anchored to the end of the segment it hangs from
        and to that segment's own drawn y.

        The three share one limit across, and the room is that limit for every one of them that
        stands in the gutter row alone — which is why `greedy`, stopping at the first place with
        the room, could never tell the places over the segment apart. The segment of this model is
        drawn below the base of its row, so the place under it reaches the row of cards below (spec
        7.1 as amended a third time) and has no room there at all: that one greedy can tell."""
        layout, _ = flow.plan(copy.deepcopy(BRANCH), "widget", draft=True)
        order, cands, needs, cards, runs, _ = candidates(layout, "widget")
        i = next(k for k in order if (layout["edges"][k]["a"], layout["edges"][k]["b"]) == ("a", "f"))
        cs = cands[i]
        self.assertEqual([(c.where, c.rank, c.grow, c.la) for c in cs],
                         [(labels.OVER, 0, "R",
                           (1, "p", 0, labels.LABEL_BEND, -labels.LABEL_OVER, "start")),
                          (labels.BENEATH, 1, "R",
                           (1, "p", 0, labels.LABEL_BEND, labels.LABEL_UNDER, "start")),
                          (labels.OVER, 2, "L",
                           (2, "p", 0, -labels.LABEL_BEND, -labels.LABEL_OVER, "end"))])
        self.assertEqual(len({c.limit for c in cs}), 1, "the three no longer share one limit")
        inside = [c for c in cs if len(c.rects) == 1]
        self.assertEqual([(c.where, c.rank) for c in inside], [(labels.OVER, 0), (labels.OVER, 2)],
                         "premise: the segment is no longer drawn off the base of its gutter row")
        self.assertEqual({labels.room(c, cards) for c in inside}, {cs[0].limit},
                         "the two over the segment no longer have one room between them")
        self.assertEqual([r.Y for r in cs[1].rects], [layout["paths"][i][1][1],
                                                      layout["paths"][i][1][1] + 1])
        self.assertLess(labels.room(cs[1], cards), needs[i])
        # and what that one limit is: the segment's own length, less the bend the text starts past
        # and a clearance at the far end. Nothing else holds LABEL_BEND to this place — the room a
        # text has here is the whole of what the table's three places offer
        geo, paths, offsets, cells, _ = inputs(layout, "widget")
        p, off, e = paths[i], offsets[i], layout["edges"][i]
        x1 = geo.clamp(cells[e["a"]][1], geo.x(p[1][0]) + off[1][0])
        x2 = geo.clamp(cells[e["b"]][1], geo.x(p[2][0]) + off[2][0])
        self.assertEqual(cs[0].limit, abs(x2 - x1) - labels.LABEL_BEND - labels.LABEL_CLEAR)

    def test_the_error_of_a_label_that_fits_nowhere_names_what_is_in_the_way(self):
        """Criterion E3's third case: the room as today, and then the nearest thing standing in it —
        a card by the id of the node on it, a line by the edge it belongs to."""
        want = {"the next card limits the room widget": ", мешает карточка t",
                "two labels in one place widget": ", мешает линия n10 -> n00"}
        found = {}
        for name, mode, layout, warnings in planned(label_models()):
            for w in warnings:
                text = w[len(flow.DRAFT):] if w.startswith(flow.DRAFT) else w
                if name in want and NO_FIT in text:
                    found.setdefault(name, []).append(text)
        for name, clause in want.items():
            with self.subTest(case=name):
                self.assertEqual(len(found.get(name, [])), 1, found.get(name))
                self.assertIn(clause, found[name][0])
                self.assertLess(found[name][0].index("влезает ~"), found[name][0].index(clause),
                                "the room comes first, as it did before this commit")

    def test_a_label_that_fits_nowhere_is_answered_for_by_its_error_alone(self):
        """Spec 7.3 and `design.md` 14: the error of a label that fits nowhere already names the
        nearest thing in its way, so a warning that the text lies on something would be the same
        fact twice — and `advice.evaluate` counts both. The label of this model keeps a place that
        lies on several line edges and says nothing about any of them.

        The record of `LABEL_CASES` holds the count of messages as well, but a regeneration writes
        whatever the tree answers; this says what the answer has to be. The count is read per edge
        rather than over the whole plan: other labels of the model do lie on lines, and what this
        case is about is the one that fits nowhere."""
        model = next(m for n, m, mode in label_models()
                     if n == "two labels in one place widget" and mode == "widget")
        layout, warnings = flow.plan(copy.deepcopy(model), "widget", draft=True)
        choices = chosen(layout, "widget")
        short = [c for c in choices if c.room is not None]
        self.assertEqual(len(short), 1, "premise: another label of the model fits nowhere too")
        self.assertTrue(short[0].hits, "premise: the place it keeps no longer lies on a line")
        self.assertEqual(short[0].clashes, ())
        e = layout["edges"][short[0].edge]
        about = [w for w in warnings if f"связь {e['a']} -> {e['b']}:" in w]
        self.assertEqual([w for w in about if LIES in w], [], warnings)
        self.assertEqual(len([w for w in about if NO_FIT in w]), 1, warnings)

    def test_what_the_message_calls_each_thing_in_the_way(self):
        """The four kinds a rectangle of the model has, each named the way an author can act on it.
        Two of them a plan of the corpus reaches, and the case above holds those two; the bound and
        another label are the kinds the corpus never stands nearest to."""
        routed = [{"a": "x", "b": "y", "label": "да"}, {"a": "p", "b": "q", "label": "нет"}]
        self.assertEqual(flow.in_the_way(labels.Clash(labels.CARD, "t"), routed),
                         ", мешает карточка t")
        self.assertEqual(flow.in_the_way(labels.Clash(labels.LINE, (1, 0)), routed),
                         ", мешает линия p -> q")
        self.assertEqual(flow.in_the_way(labels.Clash(labels.LABEL, 0), routed),
                         ", мешает подпись связи x -> y")
        self.assertEqual(flow.in_the_way(labels.Clash(labels.BOUND, "right"), routed),
                         ", мешает край диаграммы")
        # and nothing at all where the place itself is too short for the text, which is the one case
        # in which no rectangle stands in its way
        self.assertEqual(flow.in_the_way(None, routed), "")

    def test_a_line_met_in_several_rows_of_one_place_is_one_warning(self):
        """Spec 7.3: one warning where a label lies on a line, however many rectangles this model
        cuts that line into. A place that reaches into more than one row meets a line running down
        past all of them once per row; `hits` names the owner once, `met` answers with the nearest,
        and `flow.plan` writes one message."""
        models = {name: (model, mode) for name, model, mode in seeded()}
        for name, (edge, rows) in MET_IN_ROWS.items():
            model, mode = models[name]
            layout, warnings = flow.plan(copy.deepcopy(model), mode, draft=True)
            with self.subTest(instance=name):
                i = next(k for k, e in enumerate(layout["edges"])
                         if f"{e['a']} -> {e['b']}" == edge)
                choice = next(c for c in chosen(layout, mode) if c.edge == i)
                on = [c for c in choice.clashes if c.kind == labels.ON_LINE]
                self.assertEqual(len(on), 1, choice.clashes)
                geo, paths, offsets, cells, occupied = inputs(layout, mode)
                runs = [r for r in labels.occupancy(cells, paths, offsets, geo, occupied)
                        if r.kind == labels.LINE and r.owner == on[0].owner]
                met = [r.Y for r in runs
                       if any(labels.overlaps(t, r, labels.CLEARANCE[r.kind], 0)
                              for t in choice.cand.rects)]
                self.assertEqual(len(met), rows, f"premise: that line is met in rows {met}")
                self.assertEqual([w for w in warnings if w.startswith(f"связь {edge}:")
                                  and LIES in w],
                                 [f"связь {edge}: подпись {layout['edges'][i]['label']!r} "
                                  f"{choice.cand.where} ляжет на другую линию или подпись; "
                                  f"переставьте узлы или уберите подпись в сноску"], warnings)


# Every label of the seeded hundred greedy stands over a horizontal second segment just after the
# bend with a line through it there, and what the search does with it: the instance, the edge, the
# place it ends in (`U` under the segment, `F` over it at its far end, `O` where it stays), and the
# lines still crossing it afterwards. Six of the twelve lose the crossing; the other six keep the
# place, either because the same line runs through every place left or because nothing else on that
# segment is free — and since spec 7.1 as amended a third time a place whose text would leave the
# gutter onto a card is not left either.
SEEDED_CROSSED = (
    ("seeded #7", "n00 -> n06", "U", 0),
    ("seeded #11", "n00 -> n04", "O", 1),
    ("seeded #16", "n05 -> n09", "F", 0),
    ("seeded #20", "n15 -> n05", "O", 2),
    ("seeded #33", "n07 -> n09", "U", 0),
    ("seeded #34", "n05 -> n10", "O", 1),
    ("seeded #35", "n07 -> n02", "O", 1),
    ("seeded #54", "n07 -> n04", "F", 0),
    ("seeded #75", "n01 -> n12", "O", 1),
    ("seeded #77", "n03 -> n09", "O", 1),
    ("seeded #77", "n05 -> n07", "F", 0),
    ("seeded #87", "n10 -> n05", "O", 1),
    ("seeded #87", "n15 -> n11", "U", 0),
)

# How many of the seeded instances the search leaves at a strictly lower cost than greedy's choice.
SEEDED_BETTER = 15

# The three seeded instances on which a cost that counted a line's rectangles instead of its edge
# left the search dearer than the greedy choice it starts from: on each of them the place the search
# takes lies on one line edge cut into more segments than the place greedy took.
SEEDED_PRICED = ("seeded #12", "seeded #47", "seeded #56")

# The seeded instance whose search spends the most nodes, and so the one an allowance can end in the
# middle of a component of.
SEEDED_BUDGET = "seeded #86"

# The seeded instance whose labels fall into two pairs and four labels standing alone: no place of
# any group can meet a place of another, so each is solved on its own and the nodes the search
# spends on the whole plan are the nodes the groups spend one at a time.
SEEDED_APART = ("seeded #11", ((0, 6, 9), (3, 18), (12,), (15,), (21,)))


class TheSearch(unittest.TestCase):
    """Spec 7.3, criterion E4: `labels.place` is a bounded branch and bound over the components of
    labels whose places can overlap, started from greedy's choice under the same cost, so the
    result is never worse than greedy's and the same input always gives the same choice."""

    def test_the_search_never_costs_more_than_greedy(self):
        """Criterion E4's first half, over the seeded hundred: the cost of the choice `place`
        returns is never above the cost of the choice `greedy` starts it from, and on some
        instances it is strictly lower."""
        better = []
        for name, mode, layout, _ in planned(seeded()):
            was, now = greedily(layout, mode), chosen(layout, mode)
            with self.subTest(instance=name):
                self.assertLessEqual(labels.cost(now), labels.cost(was))
            if labels.cost(now) < labels.cost(was):
                better.append(name)
        self.assertEqual(len(better), SEEDED_BETTER, better)

    def test_the_three_instances_a_count_of_segments_left_dearer_than_greedy(self):
        """Spec 7.3 prices a line by its edge, "once per candidate however many of its rectangles
        are hit", and the model cuts one line into a rectangle per row it passes and one per run it
        is made of. On these three a place of greedy's own choice lies on such a line: priced by the
        rectangle that choice reads dearer than it is, and the search walked off it to a choice that
        cost more by the edge. Priced by the edge nothing here is cheaper than greedy's choice, so
        the search keeps it."""
        for name in SEEDED_PRICED:
            layout, mode = next((lay, m) for n, m, lay, _ in planned(seeded()) if n == name)
            order, _, _, _, runs, _ = candidates(layout, mode)
            was = {c.edge: c.cand for c in greedily(layout, mode)}
            now = {c.edge: c.cand for c in chosen(layout, mode)}
            with self.subTest(instance=name):
                self.assertGreater(segment_price(order, was, runs), price(order, was, runs),
                                   f"premise: no place greedy takes on {name} lies on a line this "
                                   f"model cuts into several rectangles")
                self.assertLessEqual(price(order, now, runs), price(order, was, runs))
                self.assertEqual(now, was)

    def test_the_cost_of_a_choice_is_what_this_file_prices_it_at(self):
        """One cost, two roads to it: `labels.cost` reads the Choices a plan wrote, `price` above
        reads the places themselves and counts the line edges in this file's own words. Over the
        whole corpus the two agree, which is what lets the exhaustive walk below price a choice no
        plan ever wrote a verdict about."""
        for name, mode, layout, _ in planned(examples() + label_models() + seeded()):
            order, _, _, _, runs, _ = candidates(layout, mode)
            choices = chosen(layout, mode)
            with self.subTest(instance=name):
                self.assertEqual(price(order, {c.edge: c.cand for c in choices}, runs),
                                 labels.cost(choices))

    def test_the_nodes_spent_never_exceed_the_allowance(self):
        """Spec 7.3: the components are given the allowance in the model's order and the walk stops
        wherever it is, so a plan never spends a node it was not given. Every allowance from one
        node up to what the whole instance spends is tried, and the ones that run out mid-component
        — which is most of them here — spend exactly what they were handed and no more."""
        layout, mode = next((lay, m) for n, m, lay, _ in planned(seeded()) if n == SEEDED_BUDGET)
        order, cands, needs, cards, runs, upright = candidates(layout, mode)
        whole = labels.search(order, cands, needs, cards, runs, upright)[1]
        self.assertGreater(whole, 50, f"harness: the search over {SEEDED_BUDGET} spends {whole} "
                                      f"nodes, too few for an allowance to end inside a component")
        spent = [labels.search(order, cands, needs, cards, runs, upright, nodes=n)[1]
                 for n in range(1, whole + 1)]
        self.assertEqual([(n, used) for n, used in enumerate(spent, 1) if used > n], [])
        self.assertTrue([n for n, used in enumerate(spent, 1) if used == n and n < whole],
                        "harness: no allowance here ends inside a component")

    def test_one_node_is_greedys_own_choice(self):
        """Criterion E4's second half: one node buys the root of the first component's walk and no
        place at all, so what comes back is the choice the search started from."""
        for name, mode, layout, _ in planned(label_models() + seeded()):
            with self.subTest(instance=name):
                self.assertEqual(chosen(layout, mode, nodes=1), greedily(layout, mode))

    def test_the_same_input_twice_gives_the_same_choice(self):
        for name, mode, layout, _ in planned(seeded()):
            with self.subTest(instance=name):
                self.assertEqual(chosen(layout, mode), chosen(layout, mode))

    def test_the_search_finds_what_an_exhaustive_walk_finds(self):
        """What the bound and the order are allowed to cut away: nothing. Every component of the
        seeded corpus small enough to walk whole is walked, and the cheapest choice the walk finds
        costs exactly what the search's does."""
        walked = 0
        for name, mode, layout, _ in planned(seeded()):
            order, cands, needs, cards, runs, upright = candidates(layout, mode)
            took = {c.edge: c.cand for c in chosen(layout, mode)}
            keep = labels.fits(order, cands, needs, cards)[0]
            free = [i for i in sorted(order) if len(keep[i]) > 1]
            for group in labels.components(free, keep):
                if math.prod(len(keep[i]) for i in group) > labels.NODES:
                    continue
                walked += 1
                best = min(price(order, {**took, **dict(zip(group, combo))}, runs)
                           for combo in itertools.product(*[keep[i] for i in group]))
                with self.subTest(instance=name, group=tuple(group)):
                    self.assertEqual(price(order, took, runs), best)
        self.assertGreater(walked, 300, f"harness: only {walked} components were walked whole")

    def test_a_component_is_solved_apart_from_the_others(self):
        """The nodes of one plan are spent group by group (spec 7.3): the search over the whole
        instance spends exactly what the groups spend one at a time, with the other labels pinned
        to the places it gave them, and answers the same."""
        name, want = SEEDED_APART
        layout, mode = next((lay, m) for n, m, lay, _ in planned(seeded()) if n == name)
        order, cands, needs, cards, runs, upright = candidates(layout, mode)
        keep = labels.fits(order, cands, needs, cards)[0]
        free = [i for i in sorted(order) if len(keep[i]) > 1]
        groups = labels.components(free, keep)
        self.assertEqual(tuple(tuple(g) for g in groups), want,
                         f"premise: the labels of {name} no longer fall into these groups")
        self.assertEqual(sum(1 for g in groups if len(g) > 1), 2,
                         "premise: the two groups of more than one label this case is named for "
                         "are gone")
        whole, spent = labels.search(order, cands, needs, cards, runs, upright)
        took = {c.edge: c.cand for c in whole}
        apart = 0
        for group in groups:
            alone = {i: (cands[i] if i in group else [took[i]]) for i in order}
            one, cost = labels.search(order, alone, needs, cards, runs, upright)
            apart += cost
            self.assertEqual(one, whole, f"group {group} answers differently on its own")
        self.assertEqual(apart, spent)

    def test_a_label_greedy_leaves_crossed_goes_under_the_segment_or_to_its_far_end(self):
        """The places the table of spec 7.2 added and greedy reaches only when `fits` hands them to
        it: the places over a horizontal second segment and the one under it have one room between
        them wherever all three stand in the gutter row, so greedy takes the first and answers for
        the lines through it afterwards. The search prices those lines, and every label greedy
        leaves crossed over such a segment is `SEEDED_CROSSED`, with the place it ends in."""
        want = {(name, edge) for name, edge, _, _ in SEEDED_CROSSED}
        found = []
        for name, mode, layout, _ in planned(seeded()):
            at = {f"{e['a']} -> {e['b']}": i for i, e in enumerate(layout["edges"])}
            now = {c.edge: c for c in chosen(layout, mode)}
            for was in greedily(layout, mode):
                if (was.cand.where, was.cand.rank) != (labels.OVER, 0):
                    continue
                if not [c for c in was.clashes if c.kind == labels.CROSSED]:
                    continue
                e = layout["edges"][was.edge]
                edge = f"{e['a']} -> {e['b']}"
                self.assertIn((name, edge), want,
                              f"premise: greedy leaves {edge} of {name} crossed over its segment "
                              f"and the record does not name it")
                found.append((name, edge, place(dict(e, la=now[was.edge].cand.la)),
                              len([c for c in now[was.edge].clashes if c.kind == labels.CROSSED])))
                self.assertEqual(at[edge], was.edge)
        self.assertEqual(tuple(sorted(found, key=lambda r: (int(r[0].split("#")[1]), r[1]))),
                         SEEDED_CROSSED)
        # and what the record is there to show: the search takes some of them off the line and
        # leaves the rest where they are, never onto a place whose text would stand on a card
        self.assertTrue([r for r in SEEDED_CROSSED if r[3] == 0], SEEDED_CROSSED)
        self.assertTrue([r for r in SEEDED_CROSSED if r[3]], SEEDED_CROSSED)

    def test_two_labels_greedy_leaves_in_one_place_are_moved_apart(self):
        """The one warning the corpus no longer hears from a plan, and why: a pair of labels costs
        more than any number of lines or ranks, so the search parts two labels wherever either of
        them can move at all. The model named for the case is where greedy still leaves them in one
        place, told once and on the later of the two in the model's order (spec 7.3 as amended)."""
        model = next(m for n, m, mode in label_models()
                     if n == "two labels in one place widget" and mode == "widget")
        layout, _ = flow.plan(copy.deepcopy(model), "widget", draft=True)
        was = {c.edge: c for c in greedily(layout, "widget")}
        same = [(c.edge, x.owner) for c in was.values() for x in c.clashes
                if x.kind == labels.SAME_PLACE]
        self.assertEqual(len(same), 1, same)
        late, early = same[0]
        self.assertLess(early, late, "the pair is told on the earlier of the two")
        self.assertEqual(was[late].cand.key, was[early].cand.key)
        now = {c.edge: c for c in chosen(layout, "widget")}
        self.assertNotEqual(now[late].cand.key, now[early].cand.key)
        self.assertEqual([x for c in now.values() for x in c.clashes
                          if x.kind == labels.SAME_PLACE], [])


# A stage for the cost of spec 7.3, built by hand. No plan of the corpus ever has to choose between
# parting a pair of labels and taking a line on, or between a line and a place the label prefers:
# the choice `place` returns never keeps an overlapping pair, so the order of the terms is a
# trade-off nothing a plan reaches ever makes, and nothing a plan reaches can hold it. These places
# make it. One lattice row, a text as wide as it is asked for, and a run wherever a text is to lie
# on a line — the search reads nothing else of a place.
STAGE_ROW = 1
STAGE_WIDE = 40.0


def stage_text(i, rank, x, need=STAGE_WIDE, where=labels.DOWN):
    """One place of label `i` on the stage: its text `need` px wide from `x` rightwards, in the one
    row. `where` is the family the place belongs to, which decides whether `greedy` measures it
    against the lines at all; the limit is wide enough that `fits` keeps every place, the stage
    drawing no card unless a case puts one there."""
    return labels.Candidate(where, rank,
                            (labels.Rect(STAGE_ROW, -1.0, 1.0, x, x + need, labels.LABEL, i),),
                            x, "R", 1000.0, (i, x), frozenset(), (0, "p", 0, 0, 0, "start"))


def stage_run(owner, x):
    """A vertical run of the stage at `x`, named by (path, segment) as `occupancy` names one: the
    text it passes through lies on it."""
    return labels.Rect(STAGE_ROW, -labels.INF, labels.INF, x - 1, x + 1, labels.LINE, owner)


def staged(cands, runs, cards=()):
    """(what the search chooses on the stage, what greedy chooses): `cands` is {label: its places,
    preferred first}, `runs` the lines under them and `cards` whatever ends the room. Each label's
    text is as wide as its first place draws it."""
    order = sorted(cands)
    needs = {i: cands[i][0].rects[0].x1 - cands[i][0].rects[0].x0 for i in order}
    args = (order, cands, needs, list(cards), list(runs), frozenset())
    return labels.search(*args)[0], labels.greedy(*args)


class TheCostTheSearchMinimises(unittest.TestCase):
    """Spec 7.3, gate finding G1 and the qa review's Q1: the cost is (pairs of chosen labels that
    overlap, line owners overlapped, sum of preference ranks), compared lexicographically, and "a
    line edge counts once per candidate however many of its rectangles are hit". One function
    prices a place for both roads — `labels.cost`, which prices a finished choice, and the search,
    which prices a half-built one — so what the search minimises is what the cost compares."""

    def test_a_line_counts_once_however_many_of_its_segments_a_text_meets(self):
        """The preferred place lies on two segments of one edge, the place after it on one segment
        of another: one line edge each, so the label keeps the place it prefers. A cost that counted
        the rectangles would read the first as two lines and move the label off it — which is what
        it did on three of the seeded hundred (`SEEDED_PRICED`)."""
        cands = {0: [stage_text(0, 0, 100.0), stage_text(0, 1, 300.0)]}
        runs = [stage_run((9, 0), 110.0), stage_run((9, 1), 130.0), stage_run((4, 2), 320.0)]
        now, was = staged(cands, runs)
        self.assertEqual(now[0].hits, frozenset({(9, 0), (9, 1)}),
                         "premise: the preferred place no longer meets two segments of one edge")
        self.assertEqual(now[0].cand.rank, 0)
        self.assertEqual(labels.cost(now), (0, 1, 0))
        self.assertEqual(now, was, "greedy already stands there: neither place has the room for "
                                   "its text, so it keeps the first")

    def test_a_pair_is_parted_though_the_place_that_parts_it_lies_on_a_line(self):
        """The first term before the second: one label can stand clear of every line in the very
        place another label took, or alone on a line. A pair costs more than any number of lines,
        so it moves."""
        cands = {0: [stage_text(0, 0, 100.0), stage_text(0, 1, 300.0)],
                 1: [stage_text(1, 0, 120.0)]}
        now, was = staged(cands, [stage_run((9, 0), 320.0)])
        self.assertEqual([c.cand.rank for c in was], [0, 0],
                         "premise: greedy no longer takes the first place of each")
        self.assertEqual(labels.cost(was), (1, 0, 0))
        self.assertEqual([c.cand.rank for c in now], [1, 0])
        self.assertEqual(labels.cost(now), (0, 1, 1))
        self.assertLess(labels.cost(now), labels.cost(was))

    def test_a_line_is_given_up_for_a_place_the_label_prefers_less(self):
        """The second term before the third: the place the label prefers lies on a line and the one
        after it on none. Greedy takes the first of the three places of a horizontal second segment
        whatever runs through it — they have one room between them — and the search prices the
        lines, which is the whole of why the table's new places are ever reached."""
        cands = {0: [stage_text(0, 0, 100.0, where=labels.OVER),
                     stage_text(0, 1, 300.0, where=labels.BENEATH)]}
        now, was = staged(cands, [stage_run((9, 0), 120.0)])
        self.assertEqual(was[0].cand.rank, 0,
                         "premise: greedy no longer takes the first place of the segment")
        self.assertEqual(labels.cost(was), (0, 1, 0))
        self.assertEqual(now[0].cand.rank, 1)
        self.assertEqual(labels.cost(now), (0, 0, 1))
        self.assertLess(labels.cost(now), labels.cost(was))

    def test_a_choice_of_equal_cost_leaves_greedys_standing(self):
        """The search answers greedy wherever nothing is strictly cheaper (spec 7.3: never worse
        than greedy, and the same input always gives the same choice). Two places of one label that
        cost the same — one line each and the same rank — are such a nothing, and the incumbent is
        the one greedy left."""
        cands = {0: [stage_text(0, 0, 100.0, where=labels.OVER),
                     stage_text(0, 0, 300.0, where=labels.OVER)]}
        now, was = staged(cands, [stage_run((9, 0), 120.0), stage_run((4, 1), 320.0)])
        self.assertEqual(labels.cost(now), labels.cost(was),
                         "premise: the two places no longer cost the same")
        self.assertEqual(now[0].cand.start, 100.0)
        self.assertEqual(now, was)


# A model whose two labelled edges leave one card, turn at one bend and run the same way along one
# row: the same place of the table of spec 7.2, but for the offset each segment is drawn at. It is
# instance 4 of the seeded stream, whose labels are the two that make the shape — no model of the
# corpus reaches it, since a labelled edge there is every third one.
ONE_BEND = cases.exit_model(["n00 .   n01", ".   n02 n03", "n04 .   ."],
                            ["n01 -> n00", "n01 -> n02 : да", "n01 -> n04 : нет", "n03 -> n01",
                             "n03 -> n04", "n04 -> n00", "n04 -> n02"])


class WhatALabelAnswersFor(unittest.TestCase):
    """Spec 7.3: a pair of labels whose texts overlap is told about once, on the later of the two in
    the model's order — as the same place where the two took the very same place, and inside that
    label's one "ляжет" where they merely meet. So a label answers for the labels before it and
    never for the ones after, and what "the very same place" means is the place's own key."""

    def test_two_labels_at_one_bend_and_two_offsets_are_not_one_place(self):
        """Two labels on horizontal second segments starting at one bend and running one way, the
        segments drawn at two offsets: the two keys differ however near the texts stand. Both pairs
        here stand on opposite sides of their segments, so the side tells their places apart as
        well; the pair on one side, where the offset is all that does, is the case after this one.

        On `ONE_BEND` the one segment is drawn below the base of its gutter row and the other above
        it, so since spec 7.1 as amended a third time one label keeps only the place over its
        segment and the other only the place under its own, and the two texts no longer come near
        each other at all. Where they do — the page of `two labels in one place`, whose two
        segments are spread far enough for the places left to overlap — the later of the two says
        once that it lies on something, and not that the two took one place, which would be two
        warnings where the drawing has one thing wrong with it and `advice.evaluate` (spec 6)
        counts them.

        Greedy is what holds it: the search parts the two, which is the whole of its first term."""
        layout, _ = flow.plan(copy.deepcopy(ONE_BEND), "widget", draft=True)
        order, cands, needs, cards, runs, upright = candidates(layout, "widget")
        first, second = labels.greedy(order, cands, needs, cards, runs, upright)
        paths, edges = layout["paths"], layout["edges"]
        self.assertEqual({c.cand.where for c in (first, second)}, {labels.OVER, labels.BENEATH},
                         "premise: the two labels no longer take opposite sides of their segments")
        self.assertEqual(paths[first.edge][1], paths[second.edge][1],
                         "premise: the two segments no longer start at one bend")
        self.assertNotEqual(edges[first.edge]["path"][1][3], edges[second.edge]["path"][1][3],
                            "premise: the two segments are no longer drawn at different offsets")
        self.assertNotEqual(first.cand.key, second.cand.key)
        self.assertFalse(labels.meet(first.cand, second.cand))
        # and the pair that does meet, on the model whose spread is wide enough for it
        model = next(m for n, m, mode in label_models()
                     if n == "two labels in one place page" and mode == "page")
        layout, _ = flow.plan(copy.deepcopy(model), "page", draft=True)
        order, cands, needs, cards, runs, upright = candidates(layout, "page")
        took = labels.greedy(order, cands, needs, cards, runs, upright)
        pair = [(a, b) for k, a in enumerate(took) for b in took[k + 1:]
                if a.cand.where in labels.SECOND_RUN and b.cand.where in labels.SECOND_RUN
                and layout["paths"][a.edge][1] == layout["paths"][b.edge][1]
                and labels.meet(a.cand, b.cand)]
        self.assertEqual(len(pair), 1, "premise: that model no longer has one such pair")
        first, second = pair[0]
        self.assertNotEqual(layout["edges"][first.edge]["path"][1][3],
                            layout["edges"][second.edge]["path"][1][3],
                            "premise: the two segments are no longer drawn at different offsets")
        self.assertNotEqual(first.cand.key, second.cand.key)
        self.assertEqual([c.kind for c in second.clashes].count(labels.ON_LINE), 1, second.clashes)
        self.assertEqual([c for c in second.clashes if c.kind == labels.SAME_PLACE], [])

    def test_two_labels_over_one_bend_at_two_offsets_are_not_one_place(self):
        """The same pair on one side: two segments leave one bend along one gutter row the same way,
        drawn 0 and 5 px off its base, and each label stands over its own, just after the bend. The
        two anchors are one and the same, so the offset each segment is drawn at is the one thing
        that tells the two places apart — it is where each text hangs from since spec 7.2 as
        amended. The texts meet, and the later label says so once: that it lies on something, and
        not that the two took one place, which would be two warnings for one overlap."""
        paths = [[(1, 3), (1, 4), (3, 4), (3, 5)], [(1, 3), (1, 4), (5, 4), (5, 5)]]
        offsets = [[(0.0, 0.0)] * 4, [(0.0, 0.0), (0.0, 5.0), (0.0, 5.0), (0.0, 0.0)]]
        _, cards, runs, places = scene("widget", ["x . .", "a . .", ". c d"], paths, offsets)
        first, second = places(0, "a", "c")[0], places(1, "a", "d")[0]
        self.assertEqual({(c.where, c.rank) for c in (first, second)}, {(labels.OVER, 0)},
                         "premise: the two places are no longer both over the segment after the bend")
        self.assertEqual(first.la, second.la, "premise: the two texts no longer hang alike")
        self.assertNotEqual(first.rects[0].y0, second.rects[0].y0,
                            "premise: the two segments are no longer drawn at different offsets")
        self.assertTrue(labels.meet(first, second), "premise: the two texts no longer meet")
        later = labels.verdicts([0, 1], {0: first, 1: second}, {}, cards, runs,
                                labels.uprights(paths))[1]
        self.assertEqual([c.kind for c in later.clashes], [labels.ON_LINE], later.clashes)
        self.assertNotEqual(first.key, second.key)

    def test_the_error_of_a_label_names_nothing_placed_after_it(self):
        """Which label a fit error may name: the nearest thing of all is the text of the label
        placed next, and the error names the card that ends the room instead."""
        cands = {0: [stage_text(0, 0, 100.0)], 1: [stage_text(1, 0, 105.0, need=10.0)]}
        cards = [labels.Rect(STAGE_ROW, -labels.INF, labels.INF, 120.0, 260.0, labels.CARD, "t")]
        now, _ = staged(cands, [], cards)
        self.assertIsNone(now[1].room, "premise: the label placed next fits nowhere either")
        self.assertEqual(now[0].room, 120.0 - 100.0 - labels.LABEL_CLEAR)
        self.assertEqual(labels.met(now[0].cand, cards + list(now[1].cand.rects)),
                         labels.Clash(labels.LABEL, 1),
                         "premise: the label placed next no longer stands nearer than the card")
        self.assertEqual(now[0].blocked, labels.Clash(labels.CARD, "t"))


class TheSegmentALabelHangsFrom(unittest.TestCase):
    """Spec 7.2 as amended on 2026-09-21: a place over or under a horizontal second segment is read
    from that segment as it is drawn, not from the base of its row. The script hung such a text
    LABEL_OVER over `base(Y)` whatever the segment's own offset, so a segment spread far enough off
    the base ran through its own label."""

    def far_off_the_base(self, corpus):
        """[(model, mode, edge, the px the labelled segment is drawn off the base of its row, the
        text's box relative to that base)] for every label on a horizontal second segment whose own
        line is drawn at least LABEL_OVER px off the base — far enough that a text measured from
        the base would meet it."""
        out = []
        for name, mode, layout, _ in planned(corpus):
            for choice in chosen(layout, mode):
                p = layout["paths"][choice.edge]
                if len(p) < 3 or p[2][1] != p[1][1]:
                    continue
                e = layout["edges"][choice.edge]
                text, seg = choice.cand.rects[0], e["path"][1][3]
                if abs(seg) >= labels.LABEL_OVER:
                    out.append((name, mode, f"{e['a']} -> {e['b']}", seg, (text.y0, text.y1)))
        return out

    def test_a_segment_drawn_above_the_base_of_its_row_takes_its_label_with_it(self):
        """The named case: the widest-spread labelled segment of the corpus, drawn 17.5 px above the
        base of its row, with its text under it and clear of it — where a text measured from the
        base would have had that line through it. Under, because over a segment drawn that far above
        the base the text would leave the gutter onto the card above it (spec 7.1 as amended a third
        time), and that place is dropped before the choice is made."""
        found = {(name, edge): (seg, box) for name, mode, edge, seg, box
                 in self.far_off_the_base(label_models()) if mode == "page"}
        seg, box = found[("two labels in one place page", "n04 -> n01")]
        self.assertEqual(seg, -17.5, "premise: that segment is no longer the widest spread one")
        self.assertEqual(box, (seg + labels.LABEL_UNDER - labels.LABEL_DROP - labels.TEXT_HALF,
                               seg + labels.LABEL_UNDER - labels.LABEL_DROP + labels.TEXT_HALF))
        self.assertGreater(box[0], seg + 1, "the text stands under the segment, clear of it")
        # and the rule it replaced: the script hung such a text LABEL_OVER over `base(Y)` whatever
        # the segment's own offset, and measured from that base this segment runs through its label
        was = (-labels.LABEL_OVER - labels.LABEL_DROP - labels.TEXT_HALF,
               -labels.LABEL_OVER - labels.LABEL_DROP + labels.TEXT_HALF)
        self.assertTrue(was[0] < seg + 1 and seg - 1 < was[1], (was, seg))

    def test_no_label_of_the_corpus_lies_on_its_own_second_segment(self):
        """And over the whole corpus: no label on a horizontal second segment has its own line
        through its box, where before this commit 34 of them did — every one whose segment is drawn
        more than TEXT_HALF - LABEL_DROP px off the base of its row."""
        struck, far = [], self.far_off_the_base(examples() + label_models() + seeded())
        for name, mode, edge, seg, box in far:
            if box[0] < seg + 1 and seg - 1 < box[1]:
                struck.append(f"{name} {mode} {edge}")
        self.assertEqual(struck, [])
        self.assertGreater(len(far), 20, f"harness: only {len(far)} segments are spread far enough "
                                         f"off the base for this to say anything")


# The three labelled horizontal second segments of `tests/test_label_lines.UP`, each drawn at a
# different place in its own gutter row: (the edge, the lattice row its segment runs along, the px
# it is drawn off the base of that row). `a? -> c` is the case the third round of the branch gate
# reported — under a segment drawn below the middle of a 40 px gutter the text spans 10.5 to 23.5
# and its baseline stands inside the card below. `b -> d` is the same the other way up, and
# `d -> b` the segment on the middle of its own gutter, which keeps every place it has.
UP_SEGMENTS = {"a? -> c": (2, 4.0), "b -> d": (2, -4.0), "d -> b": (4, 0.0)}


class TheRowsATextReaches(unittest.TestCase):
    """Spec 7.1, amended a third time on 2026-09-21 after the third round of the branch gate: a text
    stands in every row it reaches, not only in the row of the line it hangs from.

    A gutter is `row_gap` high about its base and an outer row margin `margin` deep, so a place over
    or under a horizontal second segment drawn off that base can leave its row. Cards align to the
    top of their row, so the row under such a line begins with its cards and a text reaching into it
    lies on whatever card it shares px with; the row over it ends with its tallest card, whose height
    is unknown here, and a text reaching into that one is read the same way.

    The three cases below are the three segments of `UP_SEGMENTS`, in widget mode, where the gutter
    is 40 px and a text over or under a segment on the base of one fills it with half a px to spare.
    """

    def up(self, mode="widget"):
        """(the layout, what the plan said, {edge: its index}) of `tests/test_label_lines.UP`, with
        the premise of every case here asserted: each of the three labels hangs from a horizontal
        second segment running along the lattice row `UP_SEGMENTS` names, drawn the px off the base
        of that row it names, and the gutter that row is has the height `Geometry` gives it."""
        layout, warnings = flow.plan(copy.deepcopy(cases.UP), mode, draft=True)
        at = {f"{e['a']} -> {e['b']}": i for i, e in enumerate(layout["edges"])}
        geo = inputs(layout, mode)[0]
        for edge, (Y, seg) in UP_SEGMENTS.items():
            p, e = layout["paths"][at[edge]], layout["edges"][at[edge]]
            self.assertEqual((len(p) >= 3 and p[1][1] == p[2][1], p[1][1], e["path"][1][3]),
                             (True, Y, seg),
                             f"premise: {edge} no longer turns into a horizontal second segment "
                             f"along row {Y} drawn {seg} off its base: {e['path']}")
            self.assertEqual(Y % 2, 0, f"premise: row {Y} is no longer a gutter")
        self.assertEqual(geo.row_gap, 40, "premise: a widget's row gap is no longer 40 px")
        return layout, warnings, at

    def places(self, layout, mode, edge, at):
        """{(family, rank): the place} of one label, and the choice it took."""
        cands = candidates(layout, mode)[1][at[edge]]
        took = next(c for c in chosen(layout, mode) if c.edge == at[edge])
        return {(c.where, c.rank): c for c in cands}, took

    def test_a_text_under_a_segment_below_the_middle_of_its_gutter_reaches_the_card_row(self):
        """The reported case. `a? -> c` hangs from a segment drawn 4 px below the base of gutter
        row 2: the place under it spans 10.5 to 23.5, past the 20 px the gutter has, and the card a?
        of row 3 begins there and covers the whole of the text across. So the place is dropped
        (spec 7.3), the label takes the one over the segment, and the plan says what stands there."""
        layout, warnings, at = self.up()
        geo, _, _, _, occupied = inputs(layout, "widget")
        cards = [r for r in labels.occupancy(layout["cells"], layout["paths"],
                                             [[(pt[2], pt[3]) for pt in e["path"]]
                                              for e in layout["edges"]], geo, occupied)
                 if r.kind == labels.CARD]
        spots, took = self.places(layout, "widget", "a? -> c", at)
        under = spots[labels.BENEATH, 1]
        text, reach = under.rects[0], under.rects[1:]
        self.assertEqual((text.Y, text.y0, text.y1), (2, 10.5, 23.5))
        self.assertGreater(text.y1, geo.row_gap / 2, "the text no longer leaves its gutter")
        self.assertEqual([r.Y for r in reach], [3], under.rects)
        # the card that covers it there, and the room it leaves the text: none at all
        covers = [r.owner for r in cards if r.Y == 3 and r.x0 < text.x1 and text.x0 < r.x1]
        self.assertEqual(covers, ["a?"], "premise: a? no longer stands under that text")
        need = label_width(layout["edges"][at["a? -> c"]]["label"])
        self.assertLess(labels.room(under, cards), need)
        # so the label stands over its own segment instead, and answers for what is there
        self.assertEqual((took.cand.where, took.cand.rank), (labels.OVER, 0))
        self.assertEqual(layout["edges"][at["a? -> c"]]["la"],
                         (1, "p", 0, -labels.LABEL_BEND, -labels.LABEL_OVER, "end"))
        self.assertEqual(sorted(c.kind for c in took.clashes), [labels.CROSSED, labels.ON_LINE])
        self.assertEqual([w for w in warnings if w.startswith("связь a? -> c:")],
                         ["связь a? -> c: подпись 'да' над вторым отрезком ляжет на другую линию "
                          "или подпись; переставьте узлы или уберите подпись в сноску",
                          "связь a? -> c: подпись 'да' пересечёт линию b -> d; переставьте узлы "
                          "или уберите подпись в сноску"], warnings)

    def test_a_text_over_a_segment_above_the_middle_of_its_gutter_reaches_the_row_over_it(self):
        """The same reading the other way up: `b -> d` hangs from a segment drawn 4 px above the
        base of gutter row 2, so the place over it spans -23.5 to -10.5 and reaches into row 1,
        which ends with its tallest card. The card b covers that text across, so the label takes
        the place under its segment — where the row under the gutter is the one out of reach."""
        layout, warnings, at = self.up()
        geo = inputs(layout, "widget")[0]
        spots, took = self.places(layout, "widget", "b -> d", at)
        over, under = spots[labels.OVER, 0], spots[labels.BENEATH, 1]
        self.assertEqual((over.rects[0].y0, over.rects[0].y1), (-23.5, -10.5))
        self.assertLess(over.rects[0].y0, -geo.row_gap / 2, "the text no longer leaves its gutter")
        self.assertEqual([r.Y for r in over.rects], [2, 1], over.rects)
        self.assertEqual([r.Y for r in under.rects], [2],
                         "the place under that segment reaches nowhere, and is the one left")
        self.assertEqual((took.cand.where, took.cand.rank), (labels.BENEATH, 1))
        self.assertEqual(layout["edges"][at["b -> d"]]["la"],
                         (1, "p", 0, -labels.LABEL_BEND, labels.LABEL_UNDER, "end"))
        self.assertEqual([w for w in warnings if w.startswith("связь b -> d:")],
                         ["связь b -> d: подпись 'да' под вторым отрезком ляжет на другую линию "
                          "или подпись; переставьте узлы или уберите подпись в сноску"], warnings)

    def test_a_segment_on_the_middle_of_its_gutter_keeps_every_place_it_has(self):
        """And the segment drawn on the base of its own gutter row: LABEL_OVER, LABEL_DROP and
        TEXT_HALF come to half a px less than half a widget's row gap, so all three places of the
        table stand in that row and nowhere else, and the label keeps the one it prefers."""
        layout, warnings, at = self.up()
        geo = inputs(layout, "widget")[0]
        spots, took = self.places(layout, "widget", "d -> b", at)
        self.assertEqual(sorted(spots), sorted({(labels.OVER, 0), (labels.BENEATH, 1),
                                                (labels.OVER, 2)}))
        for key, spot in spots.items():
            with self.subTest(place=key):
                self.assertEqual([r.Y for r in spot.rects], [4], spot.rects)
                self.assertEqual(labels.reached(geo, 4, spot.rects[0].y0, spot.rects[0].y1), ())
        self.assertEqual(labels.LABEL_OVER + labels.LABEL_DROP + labels.TEXT_HALF,
                         geo.row_gap / 2 - 0.5)
        self.assertEqual((took.cand.where, took.cand.rank), (labels.OVER, 0))
        self.assertEqual([w for w in warnings if w.startswith("связь d -> b:")], [], warnings)

    def test_what_reached_says_of_each_kind_of_row(self):
        """`reached` itself, over the rows of one geometry: a gutter between two rows of cards is
        `row_gap` high about its base and an outer row margin `margin` deep, so a text that leaves
        either stands in the row of cards it reaches. A row of cards states no height here and
        neither does a row line beside an empty row, whose place `tracks()` invents, so a text of
        one of those keeps the model's uncertainty inside its own row; the lines of a band of empty
        rows state theirs through `Geometry.frame`."""
        geo = flow.Geometry(flow.mode_for("flow", "widget", None), 200.0, 3, rows=4, empty=(2,))
        half, margin = geo.row_gap / 2, geo.margin
        wide = (-half - 1, half + 1)
        self.assertEqual(labels.reached(geo, 2, *wide), (1, 3))      # a plain gutter, both ways
        self.assertEqual(labels.reached(geo, 2, -half, half), ())    # a text that fills it exactly
        self.assertEqual(labels.reached(geo, 0, *wide), (1,))        # the top margin: cards below
        self.assertEqual(labels.reached(geo, 0, -margin, margin), ())
        self.assertEqual(labels.reached(geo, 8, *wide), (7,))        # the bottom margin: above
        self.assertEqual(labels.reached(geo, 8, -margin, margin), ())
        self.assertEqual(labels.reached(geo, 3, *wide), ())          # a row of cards
        # the band of the empty row is read in its own frame (spec 7.1 as amended a fourth time):
        # its first gutter stands 20 px under the cards over it and its last 20 px over the cards
        # under it, and the empty row's own line 40 px from either
        self.assertEqual(labels.reached(geo, 4, *wide), (3,))        # the gutter over the empty row
        self.assertEqual(labels.reached(geo, 6, *wide), (7,))        # and the one under it
        self.assertEqual(labels.reached(geo, 5, *wide), ())          # the empty row's own line
        self.assertEqual(labels.reached(geo, 5, -2 * half - 1, 2 * half + 1), (3, 7))
        # the two margins are `margin` from the cards and not half a row gap, which is what tells
        # this case from one that read every even row the same way
        self.assertNotEqual(margin, half)
        self.assertEqual(labels.reached(geo, 0, -half, half), (1,))

    def test_every_place_of_the_corpus_stands_in_the_rows_its_text_reaches(self):
        """The rectangles of every place on a horizontal second segment, over the whole corpus,
        against `reached`: a place whose box leaves its row carries one rectangle per row it leaves
        into and none otherwise, and the rows it reaches are read as whole rows, since what ends
        them is a card height."""
        stayed = left = 0
        for name, mode, layout, _ in planned(examples() + label_models() + seeded()):
            geo = inputs(layout, mode)[0]
            for i, cs in candidates(layout, mode)[1].items():
                # a segment along a row of cards states no px, and what its text reaches past the
                # row is `TheFrameATextIsReadIn`'s
                for c in (c for c in cs if c.where in labels.SECOND_RUN
                          and geo.frame(c.rects[0].Y) is not None):
                    text = c.rects[0]
                    want = labels.reached(geo, text.Y, text.y0, text.y1)
                    with self.subTest(model=name, edge=i, place=(c.where, c.rank)):
                        self.assertEqual(tuple(r.Y for r in c.rects[1:]), want)
                        self.assertEqual({(r.y0, r.y1) for r in c.rects[1:]},
                                         {(-labels.INF, labels.INF)} if want else set())
                    stayed, left = stayed + (not want), left + bool(want)
        self.assertGreater(left, 100, f"harness: only {left} places of the corpus leave their row")
        self.assertGreater(stayed, 100, f"harness: only {stayed} places stay inside it")

    def test_a_text_is_measured_against_the_cards_alone_in_a_row_it_only_reaches(self):
        """What a text meets in a row it only pokes into: the cards it shares px with, and nothing
        else. It stands past the edge of that row, and everything else drawn there — the lines
        along it, the texts standing on its base — is a card height away from that edge, which this
        side does not know; a line that crosses the row passes the text's own row on its way and is
        met there. So every run and every label of a reached row is the place's own `exempt`."""
        checked = framed = 0
        for name, mode, layout, _ in planned(label_models() + seeded()):
            paths = layout["paths"]
            geo = inputs(layout, mode)[0]
            blind = set(labels.drawn_owners(paths))
            for i, cs in candidates(layout, mode)[1].items():
                for c in (c for c in cs if c.where in labels.SECOND_RUN and len(c.rects) > 1):
                    checked += 1
                    for rect in c.rects[1:]:
                        with self.subTest(model=name, edge=i, row=rect.Y):
                            if geo.frame(rect.Y) is None:
                                self.assertEqual((rect.y0, rect.y1), (-labels.INF, labels.INF))
                                self.assertEqual({o for o in blind if (rect.Y, o) not in c.exempt},
                                                 set())
                                continue
                            # a row line the text only pokes into from a row of cards is read in
                            # its frame, and what is drawn there counts but the label's own path
                            # (spec 7.1 as amended a fourth time)
                            framed += 1
                            self.assertEqual({o for o in blind if (rect.Y, o) in c.exempt},
                                             {(i, k) for k in range(len(paths[i]) - 1)})
        self.assertGreater(checked, 100, f"harness: only {checked} places reach another row")


# The bases of the lines of a band of empty rows, in px from the top of the cards under it, as the
# class answer of the fourth round of the branch gate worked them out by hand from tracks() of
# template/js/head.js and by() of template/js/flow.js: one per lattice row line of the band in
# ascending order — the line over the band, then each empty row's own line and the gutter under it.
# `M` is the mode's margin and `G` its row gap. A leading band has the top margin over it and no
# cards; an interior one has the cards of the row over it end at -(k + 1) G.
LEADING_BASES = {1: lambda M, G: [-20 - M, -20, -10],
                 2: lambda M, G: [-20 - M, -20, -15, -10, -5],
                 3: lambda M, G: [-20 - M, -20, -15, -10, -7.5, -5, -2.5]}
INTERIOR_BASES = {1: lambda M, G: [G * f for f in (-1.5, -1, -0.5)],
                  2: lambda M, G: [G * f for f in (-2.25, -1.5, -1.125, -0.75, -0.375)],
                  3: lambda M, G: [G * f for f in (-3, -2, -1.5, -1, -0.75, -0.5, -0.25)]}

SCENE_W = 100.0


def scene(mode, grid, paths, offsets):
    """A plan made by hand: the cards of `grid`, the lattice paths and their offsets as given, and
    the geometry of a flow of that mode. (geo, the cards and bounds, the lines, and a function giving
    the places of one path's label as `candidates` offers them.)"""
    cells = {nid: (r, c) for r, row in enumerate(grid) for c, nid in enumerate(row.split())
             if nid != "."}
    empty = [r for r, row in enumerate(grid) if set(row.split()) == {"."}]
    geo = flow.Geometry(flow.mode_for("flow", mode, None), SCENE_W, len(grid[0].split()),
                        len(grid), empty=empty)
    occupied = set(cells.values())
    rects = labels.occupancy(cells, paths, offsets, geo, occupied)

    def places(i, a, b, need=40.0):
        return labels.candidates(i, {"a": a, "b": b}, paths[i], need, paths, offsets, geo, cells,
                                 occupied, SCENE_W)
    return (geo, [r for r in rects if r.kind in (labels.CARD, labels.BOUND)],
            [r for r in rects if r.kind == labels.LINE], places)


def from_cards(geo, Y, y):
    """The px `y` of a rectangle of row `Y` stands at from the top of the cards under the frame
    that row is read in — the one scale the bases above are written in."""
    frame = geo.frame(Y)
    return y + frame.at - frame.bottom


class TheFrameATextIsReadIn(unittest.TestCase):
    """Spec 7.1, amended a fourth time on 2026-09-21, after the class ask of the fourth round of the
    branch gate: wherever the page's geometry is known here — an interior gutter, an outer margin
    and every line of a band of empty rows — every object is read in one frame, `Geometry.frame`,
    and a text is compared with the lines, the labels and the cards of every line it reaches in it;
    where the page's y depends on a card height the rectangle holds every y it can be drawn at.

    The members the gate's map named are each held here by the case it gave: a place on a
    horizontal second segment and a pinned place on a band line reaching the cards (the band models
    of tests/test_label_lines.py), a text on one band line against a line and a label on another, a
    straight exit across a band of two or three rows, the middle of a vertical second segment, the
    text of a sideways exit reaching the gutter, a text over a segment clamped into its row — in
    that row and in the gutter past its edge — and a text carried out of a row of cards by its
    segment's offset. The confirmation rounds of the qa review asked for two more, held here as well: a
    vertical run carried out of such a row by the bend it turns at, and the text under a clamped
    segment reaching the gutter below its row."""

    def test_every_band_line_stands_where_tracks_puts_it(self):
        for mode in MODES:
            spec = flow.mode_for("flow", mode, None)
            for k in (1, 2, 3):
                for lead, rows, empty, first, want in (
                        (True, k + 1, range(k), 0, LEADING_BASES[k]),
                        (False, k + 2, range(1, k + 1), 2, INTERIOR_BASES[k])):
                    geo = flow.Geometry(spec, SCENE_W, 3, rows, empty=empty)
                    M, G = geo.margin, geo.row_gap
                    lines = range(first, first + 2 * k + 1)
                    with self.subTest(mode=mode, k=k, lead=lead):
                        self.assertEqual([from_cards(geo, Y, 0.0) for Y in lines], want(M, G))
                        self.assertEqual({geo.frame(Y).row for Y in lines}, {lines[-1]})
                        self.assertEqual({geo.frame(Y).first for Y in lines}, {first})
                        top = geo.frame(first).top - geo.frame(first).bottom
                        self.assertEqual(top, -labels.INF if lead else -(k + 1) * G)
                        # the rows of cards around it state nothing: their base is a card's middle
                        self.assertIsNone(geo.frame(lines[-1] + 1))
                        self.assertTrue(lead or geo.frame(first - 1) is None)
        geo = flow.Geometry(flow.mode_for("flow", "widget", None), SCENE_W, 3, 2)
        half, margin = geo.row_gap / 2, geo.margin
        self.assertEqual(tuple(geo.frame(0)), (0, 0.0, -labels.INF, margin, 0))
        self.assertEqual(tuple(geo.frame(2)), (2, 0.0, -half, half, 2))
        self.assertEqual(tuple(geo.frame(4)), (4, 0.0, -margin, labels.INF, 4))

    def test_the_band_models_draw_no_text_on_a_card(self):
        """Every band model of tests/test_label_lines.py, planned, and each chosen place whose text
        the page draws from a band line — pinned to one, or hanging from a point drawn on one —
        read down the page from the bases above and not from the model: no such text shares px with
        a card of the rows around the band. The places the answer found are candidates still, and
        are the ones the cards now drop."""
        found = {"a leading band of one": ("a -> c", "p", 2),
                 "a leading band of two": ("a -> c", "r", 4),
                 "a leading band of three": ("a -> d", "r", 5),
                 "a leading band of three, turning back": ("a -> c", "r", 5)}
        dropped = checked = 0
        per = {}
        for name, (grid, edges, k, lead, modes) in sorted(cases.BAND_MODELS.items()):
            for mode in modes:
                layout, _ = flow.plan(cases.band_model(grid, edges), mode, draft=True)
                geo, paths, offsets, cells, occupied = inputs(layout, mode)
                first = 0 if lead else 2
                bases = dict(zip(range(first, first + 2 * k + 1),
                                 (LEADING_BASES if lead else INTERIOR_BASES)[k](geo.margin,
                                                                                geo.row_gap)))
                below = {c for r, c in occupied if 2 * r + 1 == first + 2 * k + 1}
                above = {c for r, c in occupied if 2 * r + 1 == first - 1}
                on_band = 0
                for choice in chosen(layout, mode):
                    e, p = layout["edges"][choice.edge], paths[choice.edge]
                    pt, ref, Y, _, dy, _ = e["la"]
                    if ref == "r" and Y in bases:
                        mid = bases[Y]
                    elif ref == "p" and p[pt][1] in bases and pt not in (0, len(p) - 1):
                        mid = bases[p[pt][1]] + offsets[choice.edge][pt][1] + dy - labels.LABEL_DROP
                    else:
                        continue
                    on_band += 1
                    top, bottom = mid - labels.TEXT_HALF, mid + labels.TEXT_HALF
                    x0 = min(r.x0 for r in choice.cand.rects)
                    x1 = max(r.x1 for r in choice.cand.rects)
                    hit = [c for c in below if bottom > 0 and geo.left(c) < x1 and x0 < geo.right(c)]
                    hit += [c for c in above
                            if top < -(k + 1) * geo.row_gap and geo.left(c) < x1 and x0 < geo.right(c)]
                    with self.subTest(model=name, mode=mode, edge=f"{e['a']} -> {e['b']}"):
                        self.assertEqual(hit, [], f"the text {top}..{bottom} is drawn on a card")
                checked += on_band
                per[name] = per.get(name, 0) + on_band
                if name not in found or mode != modes[0]:
                    continue
                edge, ref, Y = found[name]
                i = next(j for j, x in enumerate(layout["edges"])
                         if f"{x['a']} -> {x['b']}" == edge and any(
                             c.la[1] == ref and (c.la[2] == Y if ref == "r" else paths[j][1][1] == Y)
                             for c in candidates(layout, mode)[1].get(j, ())))
                order, cands, needs, cards, _, _ = candidates(layout, mode)
                witness = [c for c in cands[i] if c.la[1] == ref
                           and (c.la[2] == Y if ref == "r" else True)
                           and any(r.kind == labels.LABEL and r.y0 == -labels.INF
                                   and r.y1 == labels.INF and r.Y == first + 2 * k + 1
                                   for r in c.rects)]
                with self.subTest(model=name, witness=(edge, ref, Y)):
                    self.assertTrue(witness, "the place the answer found no longer reaches the cards")
                    self.assertTrue(all(labels.room(c, cards) < needs[i] for c in witness))
                dropped += len(witness)
        self.assertGreater(checked, 20, f"harness: only {checked} labels stand on a band")
        self.assertEqual([n for n, count in per.items() if not count], [],
                         "harness: a band model puts no label on its band in any mode")
        self.assertGreaterEqual(dropped, len(found))

    def test_a_text_on_one_band_line_meets_a_line_and_a_label_on_another(self):
        """The answer's example: over a leading band of one row, a text over a segment on the
        gutter at -10 spans -29.5 to -16.5 and a line on the empty row's own line at -20 spans -21
        to -19. Each stands on a lattice row of its own, and both are read in the one frame.

        A text and a horizontal line are written in the frame by `_stands`, which reads
        `Geometry.frame` itself; a vertical run is written by `_column`, row by row through `_key`.
        So the frame is held here on a vertical run as well, read as `occupancy` writes it: b's line
        up through the gutter to its bend on the empty row's line, drawn at -20, stands in the
        frame from -21 down — through the lower text and clear of the upper one, which a run
        written in its own rows would cover, the gutter's row whole."""
        paths = [[(1, 3), (1, 2), (5, 2), (5, 3)], [(3, 3), (3, 1), (0, 1), (0, 3), (1, 3)],
                 [(5, 3), (5, 1), (1, 1), (1, 3)]]
        offsets = [[(0.0, 0.0)] * len(q) for q in paths]
        geo, _, runs, places = scene("widget", [". . . .", "a b c d"], paths, offsets)
        over = places(0, "a", "c")[0]
        text = over.rects[0]
        self.assertEqual((over.where, over.rank), (labels.OVER, 0))
        self.assertEqual((from_cards(geo, text.Y, text.y0), from_cards(geo, text.Y, text.y1)),
                         (-29.5, -16.5))
        line = next(r for r in runs if r.owner == (1, 1))
        self.assertEqual((from_cards(geo, line.Y, line.y0), from_cards(geo, line.Y, line.y1)),
                         (-21.0, -19.0))
        self.assertIn((1, 1), labels.hits(over, runs))
        # and a label over a segment on that line, -39.5 to -26.5, meets the first one's text
        wide = [places(0, "a", "c", 130.0)[0], places(2, "c", "a", 130.0)[0]]
        self.assertEqual([from_cards(geo, c.rects[0].Y, c.rects[0].y0) for c in wide], [-29.5, -39.5])
        self.assertTrue(labels.meet(*wide))
        column = [(r.Y, from_cards(geo, r.Y, r.y0), from_cards(geo, r.Y, r.y1))
                  for r in runs if r.owner == (1, 0) and geo.frame(r.Y) is not None]
        self.assertEqual(column, [(2, -21.0, labels.INF)])
        self.assertIn((1, 0), labels.hits(wide[0], runs))
        self.assertEqual(labels.hits(wide[1], runs), frozenset())

    def test_a_straight_exit_across_a_band_is_bounded_by_its_own_card(self):
        """A straight exit down hangs its text LABEL_BELOW under its card, 16.5 px down to the text's
        far edge; one up stands its text 16.5 px over the card. Across a band of two or three rows
        the first gutter is not half a row gap under the cards over it, nor the last one over the
        cards under it, so the bound is the card's and not the gutter's. A band of one row keeps
        both at half a row gap, and so its bounds where they were."""
        for mode in MODES:
            for k in (1, 2, 3):
                grid = ["a . ."] + [". . ."] * k + ["b . c"]
                last = 2 * k + 2
                paths = [[(1, 1), (1, last + 1)], [(1, last + 1), (1, 1)],
                         [(5, last + 1), (5, 2), (0, 2), (0, 1), (1, 1)],
                         [(5, last + 1), (5, last), (0, last), (0, 1), (1, 1)]]
                offsets = [[(0.0, 0.0)] * 2, [(0.0, 0.0)] * 2,
                           [(0.0, 0.0), (0.0, -8.0), (0.0, -8.0), (0.0, 0.0), (0.0, 0.0)],
                           [(0.0, 0.0), (0.0, -1.0), (0.0, -1.0), (0.0, 0.0), (0.0, 0.0)]]
                geo, _, runs, places = scene(mode, grid, paths, offsets)
                G = geo.row_gap
                down, up = places(0, "a", "b")[0].rects[0], places(1, "b", "a")[0].rects[0]
                with self.subTest(mode=mode, k=k):
                    self.assertEqual(from_cards(geo, down.Y, down.y1), -(k + 1) * G + 16.5)
                    self.assertEqual(from_cards(geo, up.Y, up.y0), -16.5)
                if mode != "widget" or k == 1:
                    continue
                # a line 8 px over the first gutter's base runs past a text that stops above it,
                # and one 1 px over the last gutter's base runs through a text that reaches it
                with self.subTest(mode=mode, k=k, conflict=True):
                    self.assertNotIn((2, 1), labels.hits(places(0, "a", "b")[0], runs))
                    self.assertIn((3, 1), labels.hits(places(1, "b", "a")[0], runs))

    def test_the_middle_of_a_vertical_segment_is_read_wherever_it_can_be_drawn(self):
        """The answer's example, widget: a sideways exit from a 32 px card at the middle of its row,
        -96 px from the cards under a band of one row, turning down to a bend on the band's last
        gutter at -20. The script draws the text at the middle of the two drawn points, -58, so it
        spans -64.5 to -51.5; a line 7.5 px under the band's first gutter, at -60, spans -53.5 to
        -51.5 and runs through it. That middle depends on the card's height: the model keeps every
        row between the two ends whole and meets the line."""
        paths = [[(1, 1), (2, 1), (2, 4), (5, 4), (5, 5)], [(3, 5), (3, 2), (0, 2), (0, 1), (1, 1)]]
        offsets = [[(0.0, 0.0)] * 5,
                   [(0.0, 0.0), (0.0, 7.5), (0.0, 7.5), (0.0, 0.0), (0.0, 0.0)]]
        geo, _, runs, places = scene("widget", ["a . .", ". . .", ". d c"], paths, offsets)
        mid = (-96 + -20) / 2
        text = (mid - labels.TEXT_HALF, mid + labels.TEXT_HALF)
        line = (-60 + 7.5 - 1, -60 + 7.5 + 1)
        self.assertEqual((text, line), ((-64.5, -51.5), (-53.5, -51.5)))
        self.assertTrue(text[0] < line[1] and line[0] < text[1])
        middle = places(0, "a", "c")[0]
        self.assertEqual((middle.where, middle.la[1]), (labels.BESIDE, "m"))
        self.assertIn((1, 1), labels.hits(middle, runs))

    def test_the_middle_of_a_segment_through_a_band_is_read_over_the_whole_band(self):
        """The middle again, where the rows between the two ends share no frame with either of
        them: a sideways exit from a card of the row over a band of one empty row, turning down
        through the band onto the top edge of a card under it. The script draws the text at the
        middle of the two drawn points — the base of the source card's row, half that card's height
        over the band, and the top of the target card — so the taller the source card, the nearer
        the band's top the text: at 100 px it meets a line 8 px over the base of the band's first
        gutter. A text of TEXT_HALF about the base of each row the segment passes stands clear of
        that line, however those rows are merged into the frame; the model keeps them whole and
        meets it, in both modes."""
        for mode in MODES:
            paths = [[(1, 1), (3, 1), (3, 5)], [(5, 5), (5, 2), (0, 2), (0, 1), (1, 1)]]
            offsets = [[(0.0, 0.0)] * 3,
                       [(0.0, 0.0), (0.0, -8.0), (0.0, -8.0), (0.0, 0.0), (0.0, 0.0)]]
            geo, _, runs, places = scene(mode, ["a . .", ". . .", ". c d"], paths, offsets)
            bases = INTERIOR_BASES[1](geo.margin, geo.row_gap)
            run = next(r for r in runs if r.owner == (1, 1))
            line = (from_cards(geo, run.Y, run.y0), from_cards(geo, run.Y, run.y1))
            # the drawn points: the middle of a 100 px source card, whose row ends where the band
            # begins, and the top edge of the target card, which is 0 on this scale
            mid = (-2 * geo.row_gap - 100 / 2 + 0.0) / 2
            text = (mid - labels.TEXT_HALF, mid + labels.TEXT_HALF)
            finite = (bases[0] - labels.TEXT_HALF, bases[-1] + labels.TEXT_HALF)
            middle = places(0, "a", "c")[0]
            with self.subTest(mode=mode):
                self.assertEqual(line, (bases[0] - 9, bases[0] - 7))
                self.assertTrue(text[0] < line[1] and line[0] < text[1], f"{text} misses {line}")
                self.assertLessEqual(line[1], finite[0], "premise: the finite reading meets it")
                self.assertEqual((middle.where, middle.la[1]), (labels.BESIDE, "m"))
                self.assertIn((1, 1), labels.hits(middle, runs))

    def test_the_text_of_a_sideways_exit_is_read_in_the_gutter_it_reaches(self):
        """The answer's example, widget: a 32 px card, its line drawn at 22 — 6 px under the middle
        — and the text below that line spanning 24.5 to 37.5, 5.5 px into the gutter under the card.
        A line 16 px over that gutter's base, at 36, spans 35 to 37 and runs through it."""
        paths = [[(1, 1), (3, 1)], [(1, 3), (1, 2), (3, 2), (3, 3)]]
        offsets = [[(0.0, 6.0)] * 2, [(0.0, 0.0), (0.0, -16.0), (0.0, -16.0), (0.0, 0.0)]]
        geo, _, runs, places = scene("widget", ["a b", "c d"], paths, offsets)
        line_y = 16 + 6
        text = (line_y + labels.LABEL_SINK - labels.LABEL_DROP - labels.TEXT_HALF,
                line_y + labels.LABEL_SINK - labels.LABEL_DROP + labels.TEXT_HALF)
        run = 32 + geo.row_gap / 2 - 16
        self.assertEqual((text, (run - 1, run + 1)), ((24.5, 37.5), (35.0, 37.0)))
        below = places(0, "a", "b", 15.0)[1]
        self.assertEqual((below.where, below.rank), (labels.SIDEWAYS, 1))
        self.assertIn((1, 1), labels.hits(below, runs))

    def test_a_text_over_a_clamped_segment_covers_every_place_the_clamp_leaves_it(self):
        """The answer's example, widget: a horizontal second segment along a row of cards banded by
        its own end, at +24 from the base of a 32 px band — clamped to 22, 6 px from the base. The
        text over it spans -13.5 to -0.5 from the base, and a line along the row at the base runs
        through it; the model reads the text over the line's unclamped offset, where the two part."""
        paths = [[(3, 1), (3, 3), (5, 3)], [(1, 3), (5, 3)]]
        offsets = [[(0.0, 0.0), (0.0, 24.0), (0.0, 24.0)], [(0.0, 0.0)] * 2]
        geo, _, runs, places = scene("widget", [". s .", "a . c"], paths, offsets)
        drawn = min(24, 32 / 2 - 10)
        text = (drawn - labels.LABEL_OVER - labels.LABEL_DROP - labels.TEXT_HALF,
                drawn - labels.LABEL_OVER - labels.LABEL_DROP + labels.TEXT_HALF)
        self.assertEqual(text, (-13.5, -0.5))
        over = places(0, "s", "c", 30.0)[0]
        self.assertEqual((over.where, over.rank), (labels.OVER, 0))
        self.assertIn((1, 0), labels.hits(over, runs))

    def test_a_text_over_a_segment_clamped_near_its_rows_edge_reaches_the_gutter_beyond(self):
        """The other half of the same place: the segment drawn 24 px over the base of its banded row,
        which the clamp holds 10 px inside the top edge of a band as short as a card is drawn —
        4 px over the base. The text over it spans -23.5 to -10.5 from the base, 9.5 px past that
        edge into the gutter over the row: 10.5 to 20 in the gutter's frame. A line along the
        gutter 14 px under its base, 13 to 15, runs through the text; one on the base stays clear."""
        for gutter, through in ((14.0, True), (0.0, False)):
            paths = [[(3, 1), (3, 3), (5, 3)], [(3, 1), (3, 2), (5, 2), (5, 3)]]
            offsets = [[(0.0, 0.0), (0.0, -24.0), (0.0, -24.0)],
                       [(0.0, 0.0), (0.0, gutter), (0.0, gutter), (0.0, 0.0)]]
            geo, _, runs, places = scene("widget", [". s .", "a . c"], paths, offsets)
            drawn = max(-24.0, -labels.CARD_LEAST / 2 + labels.CLAMP)
            top = drawn - labels.LABEL_OVER - labels.LABEL_DROP - labels.TEXT_HALF
            edge = geo.frame(2).bottom
            over = places(0, "s", "c", 30.0)[0]
            with self.subTest(gutter=gutter):
                self.assertEqual((drawn, top), (-4.0, -23.5))
                self.assertEqual((over.where, over.rank), (labels.OVER, 0))
                self.assertEqual([(r.y0, r.y1) for r in runs if r.owner == (1, 1)],
                                 [(gutter - 1, gutter + 1)])
                (self.assertIn if through else self.assertNotIn)((1, 1), labels.hits(over, runs))
                self.assertEqual([(r.y0, r.y1) for r in over.rects if r.Y == 2],
                                 [(edge - (-top - labels.CARD_LEAST / 2), edge)])

    def test_a_text_under_a_segment_clamped_near_its_rows_edge_reaches_the_gutter_below(self):
        """And the place under it, a row of cards over a gutter: the segment drawn on the base of its
        banded row, or 24 px under it, which the clamp holds 10 px inside the bottom edge of a band
        as short as a card is drawn — 4 px under the base. The text under it spans 6.5 to 19.5 from
        the base, or 10.5 to 23.5: 5.5 or 9.5 px past that edge into the gutter under the row, -20
        to -14.5 or -10.5 in the gutter's frame. A line along the gutter 16 px over its base, -17 to
        -15, runs through the text either way; one on the base stays clear."""
        for seg, want in ((0.0, (0.0, 19.5)), (24.0, (4.0, 23.5))):
            for gutter, through in ((-16.0, True), (0.0, False)):
                paths = [[(3, 1), (3, 3), (5, 3)], [(1, 3), (1, 4), (5, 4), (5, 5)]]
                offsets = [[(0.0, 0.0), (0.0, seg), (0.0, seg)],
                           [(0.0, 0.0), (0.0, gutter), (0.0, gutter), (0.0, 0.0)]]
                geo, _, runs, places = scene("widget", [". s .", "a . c", ". . d"], paths, offsets)
                drawn = min(seg, labels.CARD_LEAST / 2 - labels.CLAMP)
                bottom = drawn + labels.LABEL_UNDER - labels.LABEL_DROP + labels.TEXT_HALF
                edge = geo.frame(4).top
                under = places(0, "s", "c", 30.0)[1]
                with self.subTest(segment=seg, gutter=gutter):
                    self.assertEqual((drawn, bottom), want)
                    self.assertEqual((under.where, under.rank), (labels.BENEATH, 1))
                    self.assertEqual([(r.y0, r.y1) for r in runs if r.owner == (1, 1)],
                                     [(gutter - 1, gutter + 1)])
                    (self.assertIn if through else self.assertNotIn)((1, 1),
                                                                     labels.hits(under, runs))
                    self.assertEqual([(r.y0, r.y1) for r in under.rects if r.Y == 4],
                                     [(edge, edge + bottom - labels.CARD_LEAST / 2)])

    def test_a_text_carried_out_of_a_row_of_cards_is_read_in_the_next_one(self):
        """The answer's example: a segment along a row of cards no line enters sideways, 48 px under
        the middle of a card as short as a card is drawn, takes the text under it past the gutter
        into the next row, onto the card there; 48 px over the middle, the text over it onto the
        card of the row above. On the middle, both stay where they were."""
        grid = [". s . .", "a . . .", ". u . t"]
        for off, where, rank in ((48.0, labels.BENEATH, 1), (-48.0, labels.OVER, 0),
                                 (0.0, labels.BENEATH, 1), (0.0, labels.OVER, 0)):
            paths = [[(3, 1), (3, 3), (7, 3), (7, 5)]]
            offsets = [[(0.0, 0.0), (0.0, off), (0.0, off), (0.0, 0.0)]]
            geo, cards, _, places = scene("widget", grid, paths, offsets)
            place = places(0, "s", "t", 30.0)[rank]
            self.assertEqual(place.where, where)
            with self.subTest(offset=off, place=where):
                if off:
                    row = 5 if off > 0 else 1
                    self.assertIn(row, [r.Y for r in place.rects])
                    self.assertLess(labels.room(place, cards), 30.0)
                else:
                    self.assertGreaterEqual(labels.room(place, cards), 30.0)

    def test_a_run_turning_past_a_row_of_cards_is_read_in_the_next_frame(self):
        """The same reading for the run that turns at such a segment's bend. Drawn 20 or 48 px off
        the middle of a row of cards no line enters sideways, the bend stands past the edge of a
        card as short as a card is drawn, and so does the end of the vertical run that comes to it:
        it goes on into the gutter beside the row, as the horizontal run leaving the bend does. A
        text standing on that gutter's side of a segment along it has the run through it as well as
        the segment — a "пересечёт" beside the "ляжет" — whether the run comes down to the bend or
        leaves it upwards. At 13 px the bend stays inside the row, and so do both runs."""
        rows = (("down", [". s . .", "a . . .", ". u . t"], [(3, 1), (3, 3), (7, 3), (7, 5)],
                 [(3, 5), (3, 4), (1, 4), (1, 3)], 4, 1, labels.OVER, 0),
                ("up", [". u . t", "a . . .", ". s . ."], [(3, 5), (3, 3), (7, 3), (7, 1)],
                 [(3, 1), (3, 2), (1, 2), (1, 3)], 2, -1, labels.BENEATH, 1))
        for way, grid, turning, along, R, sign, where, rank in rows:
            for off in (20.0, 48.0, 13.0):
                paths = [turning, along]
                offsets = [[(0.0, 0.0), (0.0, sign * off), (0.0, sign * off), (0.0, 0.0)],
                           [(8.0, 0.0), (8.0, 0.0), (0.0, 0.0), (0.0, 0.0)]]
                geo, cards, runs, places = scene("widget", grid, paths, offsets)
                frame = geo.frame(R)
                past = off + 1 - labels.CARD_LEAST / 2
                text = places(1, "u", "a")[rank]
                end = [(r.y0, r.y1) for r in runs if r.owner == (0, 0) and r.Y == R]
                kinds = sorted(c.kind for c in labels.verdicts(
                    [1], {1: text}, {}, cards, runs, labels.uprights(paths))[0].clashes)
                with self.subTest(way=way, offset=off):
                    self.assertEqual((text.where, [r.Y for r in text.rects]), (where, [R]))
                    if past <= 0:
                        self.assertEqual(end, [])
                        self.assertEqual(labels.hits(text, runs), frozenset())
                        continue
                    self.assertEqual(kinds, [labels.CROSSED, labels.ON_LINE])
                    self.assertEqual(sorted(labels.hits(text, runs)), [(0, 0), (0, 1)])
                    self.assertEqual(end, [(frame.top, frame.top + past) if sign > 0
                                           else (frame.bottom - past, frame.bottom)])

    def test_an_end_clamped_past_the_base_covers_what_the_clamp_leaves(self):
        """A vertical run that turns into a banded row ends at its bend, which the clamp draws
        somewhere between the base of that row and the bend's own offset: the run covers the half
        row it comes from and on to the offset where that lies past the base."""
        for off in (8.0, -8.0):
            paths = [[(3, 1), (3, 2), (2, 2), (2, 3), (1, 3)]]
            offsets = [[(0.0, 0.0), (0.0, 0.0), (0.0, 0.0), (0.0, off), (0.0, off)]]
            _, _, runs, _ = scene("widget", [". s", "a b"], paths, offsets)
            end = next(r for r in runs if r.owner == (0, 2) and r.Y == 3)
            with self.subTest(offset=off):
                self.assertEqual((end.y0, end.y1), (-labels.INF, max(0.0, off) + 1))


class TheLabelsAlreadyPlacedAreConsulted(unittest.TestCase):
    """The hole the switch left, found by the controller's mutation probe: `greedy` measures a place
    beside a vertical second segment against the labels already placed, and no test failed when that
    measurement was dropped. This is the case that does."""

    def test_a_label_gives_way_to_the_one_placed_before_it(self):
        layout, warnings = flow.plan(copy.deepcopy(GIVE_WAY), "widget", draft=True)
        order, cands, needs, cards, runs, upright = candidates(layout, "widget")
        choices = labels.greedy(order, cands, needs, cards, runs, upright)
        took = {f"{layout['edges'][c.edge]['a']} -> {layout['edges'][c.edge]['b']}": c
                for c in choices}
        first, second = took["e -> d"], took["d -> c"]
        self.assertLess(choices.index(first), choices.index(second),
                        "premise: e -> d is no longer placed before d -> c")
        self.assertEqual(first.cand.where, labels.SIDEWAYS,
                         "premise: e -> d no longer leaves its card sideways")
        # the place d -> c would take with nothing else in the way: the middle of its own segment,
        # which reaches into the row e -> d's text stands in and has the room until that text counts
        middle = cands[second.edge][0]
        self.assertEqual((middle.where, middle.rank, middle.grow), (labels.BESIDE, 0, "R"))
        self.assertGreaterEqual(min(labels.room(middle, cards), labels.room(middle, runs)),
                                needs[second.edge])
        self.assertLess(labels.room(middle, list(first.cand.rects)), needs[second.edge])
        # so it pins its text to a row of that segment instead, and says nothing about it
        self.assertEqual((second.cand.where, second.cand.la[1]), (labels.BESIDE, "r"))
        self.assertEqual(second.clashes, ())
        self.assertEqual(said(warnings), [], warnings)


class TheTwoReadingsTheSwitchCarries(unittest.TestCase):
    """Spec 7.1 as amended on 2026-09-21. Each is a check the code before the switch made one way in
    one place and another way elsewhere; the model makes it everywhere, and each case states the
    rule it replaced."""

    def test_a_row_a_vertical_second_segment_ends_in_is_read_past_its_bend(self):
        """The code before the switch kept, in such a row, every line that crossed it wherever it
        stopped and dropped every line that ran along it wherever it ran. The text stands at the
        middle of the segment, half a lattice row from the bend drawn there, so the model gives it
        the row past that bend and no more — which is what every unpinned candidate of the corpus
        says here, and what moves the five instances of `SEEDED_MOVED`."""
        ends = 0
        for name, mode, layout, _ in planned(examples() + label_models() + seeded()):
            paths, offsets = inputs(layout, mode)[1:3]
            cands = candidates(layout, mode)[1]
            for i, cs in cands.items():
                p, off = paths[i], offsets[i]
                if len(p) < 3 or p[2][1] == p[1][1]:
                    continue
                lo, hi = min(p[1][1], p[2][1]), max(p[1][1], p[2][1])
                bend = {p[1][1]: off[1][1], **({p[2][1]: off[2][1]} if len(p) >= 4 else {})}
                geo = inputs(layout, mode)[0]
                frames = {Y: geo.frame(Y) for Y in (lo, hi)}
                for rect in (r for c in cs if c.la[1] == "m" for r in c.rects):
                    Y = next((Y for Y in (lo, hi) if Y in bend
                              and rect.Y == (Y if frames[Y] is None else frames[Y].row)), None)
                    # a band line near its cards can leave a short segment's text no px past the
                    # bend; there the frame decides, and `TheFrameATextIsReadIn` holds it
                    if Y is None or (frames[Y] is not None and frames[Y].row != Y):
                        continue
                    ends += 1
                    want = ((bend[Y] + 1, labels.INF) if Y == lo else (-labels.INF, bend[Y] - 1))
                    self.assertEqual((rect.y0, rect.y1), want,
                                     f"{name}: the text of edge {i} does not stay past the bend")
        self.assertGreater(ends, 10, f"harness: only {ends} end rows are read at all")

    def test_a_label_over_a_horizontal_second_segment_is_checked_by_its_text(self):
        """The check before the switch warned once per line whose lattice column lay inside that
        segment and which spanned its row, wherever along it the text stood; the model warns once
        per line that runs through the text's own rectangle. So the old one answered for lines the
        text never reaches, and missed the line that comes down into the row and turns there, which
        stops on the text instead of passing it.

        The two are compared over greedy's places, which are the ones both checks were written
        about: the search of spec 7.3 moves a struck label off the place the line runs through, so
        over its choice there is barely a crossed label left to compare anything on."""
        only_before = only_now = both = 0
        for name, mode, layout, _ in planned(examples() + label_models() + seeded()):
            geo, paths, offsets, cells, occupied = inputs(layout, mode)
            rects = labels.occupancy(cells, paths, offsets, geo, occupied)
            choices = greedily(layout, mode)
            took = {choice.edge: choice.cand for choice in choices}
            now = {(choice.edge, c.owner) for choice in choices
                   for c in choice.clashes if c.kind == labels.CROSSED}
            was = set(post_check(layout))
            both += len(was & now)
            for i, j in was - now:
                only_before += 1
                met = [r for r in rects if r.kind == labels.LINE and r.owner[0] == j
                       and any(labels.overlaps(t, r) for t in took[i].rects)]
                self.assertEqual(met, [], f"{name}: that line does run through the text")
            for i, j in now - was:
                only_now += 1
                p = paths[i]
                spans = [(lo, hi) for axis, line, lo, hi in router.segments(paths[j])
                         if axis == "v" and min(p[1][0], p[2][0]) < line < max(p[1][0], p[2][0])]
                self.assertTrue(all(not (lo < p[1][1] < hi) for lo, hi in spans),
                                f"{name}: {i} and {j} cross inside the segment, so both warn")
        self.assertGreater(both, 0, "harness: the two checks never agree at all")
        self.assertGreater(only_before, 0, "harness: the old check never reaches past the text")
        self.assertGreater(only_now, 0, "harness: no line ever stops on a text the old check missed")


# The two seeded instances that show what an end read down to the base of its row costs, as (the
# instance, the label read, the line whose run ends off the base, the lattice column that run
# stands in, the row it ends in, the px its bend is drawn off the base of that row). Each is one
# half of the amendment's claim:
#
# INVENTED — the turn of n08 -> n01 is drawn 12 px above the base of gutter row 4 and the left place
# of n12 -> n08's text stands on that base, so a turn read down to the base covers a text the line
# never reaches: the search took the right place, which lies on another line, and the plan warned.
# HIDDEN — n05 -> n14 turns down out of gutter row 8 four px above its base, at the x of the text of
# n10 -> n05, which stands over its own second segment above that base: a turn read down to the base
# stops under the text and the plan says nothing about a line drawn through it.
RUN_END_INVENTED = ("seeded #15", "n12 -> n08", "n08 -> n01", 9, 4, -12.0)
RUN_END_HIDDEN = ("seeded #87", "n10 -> n05", "n05 -> n14", 3, 8, -4.0)


class TheEndOfAVerticalRun(unittest.TestCase):
    """Spec 7.1, amended on 2026-09-21 after the second round of the branch gate: a vertical run
    that ends at a bend ends where that bend is drawn — the offset of that point, the line's own
    half-width kept — and not at the base of the row it ends in. Half of that row stays where
    nothing on this side says where the end is drawn: a row clamped into the band of its cards,
    whose every line is drawn off its own offset by an amount that depends on card heights, and a
    run that ends on a card, whose height is unknown here as well."""

    def named(self, case):
        """(the layout, the mode, what the plan said, the label's edge index, the other line's edge
        index, the px x its run is drawn at) of one of the two cases above, and its premise
        asserted: that run stands in the lattice column the case names and ends in the row it
        names, at a bend drawn the px off the base of that row that it names."""
        name, mine, other, X, Y, oy = case
        layout, mode, said = next((lay, m, w) for n, m, lay, w in planned(seeded()) if n == name)
        where = {f"{e['a']} -> {e['b']}": i for i, e in enumerate(layout["edges"])}
        i, j = where[mine], where[other]
        p, off = layout["paths"][j], [(pt[2], pt[3]) for pt in layout["edges"][j]["path"]]
        at = [k for k in range(len(p) - 1)
              if p[k][0] == p[k + 1][0] == X and Y in (p[k][1], p[k + 1][1])]
        self.assertEqual(len(at), 1, f"premise: {other} of {name} no longer has one run in column "
                                     f"{X} ending in row {Y}: {p}")
        k = at[0]
        self.assertEqual(off[k if p[k][1] == Y else k + 1][1], oy,
                         f"premise: the bend {other} of {name} turns at in row {Y} is no longer "
                         f"drawn {oy} px off the base of it: {off}")
        return layout, mode, said, i, j, inputs(layout, mode)[0].x(X) + off[k][0]

    def ends(self, layout, mode):
        """([(what the model reads an end of a vertical run as, what the amendment asks for, the
        end)], the tally of the three kinds of end) over one plan."""
        geo, paths, offsets, cells, occupied = inputs(layout, mode)
        banded = labels.banded_rows(paths)
        rects = {(r.owner, r.Y): r for r in labels.occupancy(cells, paths, offsets, geo, occupied)
                 if r.kind == labels.LINE}
        read, kinds = [], {"at a bend": 0, "off the base": 0, "half the row": 0, "clamped": 0}
        for j, (q, off) in enumerate(zip(paths, offsets)):
            for k in range(len(q) - 1):
                if q[k][0] != q[k + 1][0]:
                    continue
                lo = min(q[k][1], q[k + 1][1])
                for at in (k, k + 1):
                    Y, oy = q[at][1], off[at][1]
                    # the two the amendment leaves at the base: the clamp of a banded row, and an
                    # end on a card, which is an end of the path itself
                    known = Y not in banded and 0 < at < len(q) - 1
                    clamped = Y in banded and 0 < at < len(q) - 1
                    kinds["at a bend" if known else "clamped" if clamped else "half the row"] += 1
                    kinds["off the base"] += int(known and oy != 0)
                    # a row line of a known frame is read in it: its rectangles stand in the
                    # frame's own row, shifted by where this line's base stands there
                    frame = geo.frame(Y)
                    shift = 0.0 if frame is None else frame.at
                    rect = rects[(j, k), Y if frame is None else frame.row]
                    # a bend the clamp of a banded row draws between the base and its own offset
                    want = ((oy - 1 if Y == lo else oy + 1) + shift if known
                            else (min(0.0, oy) - 1 if Y == lo else max(0.0, oy) + 1) if clamped
                            else 0.0)
                    read.append((rect.y0 if Y == lo else rect.y1, want, (j, k, Y)))
        return read, kinds

    def test_every_end_of_the_corpus_is_read_where_its_bend_is_drawn(self):
        """End by end over the whole corpus: the offset of the bend where the run turns in a plain
        row, and the half row it comes from where the row is banded or the run ends on a card."""
        wrong, tally = [], {"at a bend": 0, "off the base": 0, "half the row": 0, "clamped": 0}
        for name, mode, layout, _ in planned(examples() + label_models() + seeded()):
            read, kinds = self.ends(layout, mode)
            wrong += [f"{name} run {end}: {got} for {want}" for got, want, end in read
                      if got != want]
            for kind, count in kinds.items():
                tally[kind] += count
        self.assertEqual(wrong[:10], [], f"{len(wrong)} ends are read elsewhere; the first of them")
        # the case exists only while the corpus holds ends of both kinds, and while the ends at a
        # bend are drawn off the base often enough for the two readings to differ at all
        self.assertGreater(tally["off the base"], 100,
                           f"harness: too few ends are drawn off the base: {tally}")
        self.assertGreater(tally["half the row"], 100,
                           f"harness: too few ends keep the half row: {tally}")

    def test_an_end_off_the_base_no_longer_covers_a_place_it_never_reaches(self):
        """The half of the amendment about a conflict invented: read down to the base, the turn of
        n08 -> n01 covers the left place of n12 -> n08's text, which stands on that base 12 px under
        it, and the search takes the right place — which lies on another line and is warned about.
        Read where it is drawn, that place is clear and the label takes it."""
        layout, mode, said, i, _, turn = self.named(RUN_END_INVENTED)
        mine, Y = RUN_END_INVENTED[1], RUN_END_INVENTED[4]
        _, cands, _, _, runs, _ = candidates(layout, mode)
        # the middle of the segment depends on card heights and covers the gutter whole since spec
        # 7.1 was amended a fourth time; the place pinned to that gutter stands on its base
        left = next(c for c in cands[i] if c.la[1] == "r" and c.la[2] == Y and c.grow == "L")
        text = next(r for r in left.rects if r.Y == Y)
        self.assertEqual((text.y0, text.y1), (-labels.TEXT_HALF, labels.TEXT_HALF),
                         f"premise: that place no longer stands on the base of row {Y}")
        self.assertTrue(text.x0 < turn < text.x1,
                        f"premise: the turn at {turn} is no longer drawn at the x of the text "
                        f"{text.x0}..{text.x1}")
        self.assertEqual(sorted(labels.hits(left, runs)), [])
        choice = next(c for c in chosen(layout, mode) if c.edge == i)
        self.assertEqual(choice.clashes, ())
        self.assertEqual([w for w in said if w.startswith(f"связь {mine}:")], [], said)

    def test_an_end_off_the_base_no_longer_hides_a_line_through_a_text(self):
        """The other half, a conflict hidden: n05 -> n14 turns down out of gutter row 8 four px
        above its base, through the text of n10 -> n05, which stands over its own second segment
        above that base. Read down to the base the turn stops under the text and the plan says
        nothing; read where it is drawn the line crosses the text and the plan says so."""
        layout, mode, said, i, j, turn = self.named(RUN_END_HIDDEN)
        mine, other, Y = RUN_END_HIDDEN[1], RUN_END_HIDDEN[2], RUN_END_HIDDEN[4]
        choice = next(c for c in chosen(layout, mode) if c.edge == i)
        text = next(r for r in choice.cand.rects if r.Y == Y)
        self.assertEqual(choice.cand.where, labels.OVER,
                         "premise: that label no longer stands over its own second segment")
        self.assertLess(text.y1, 0, f"premise: its text no longer stands above the base of row {Y}")
        self.assertTrue(text.x0 < turn < text.x1,
                        f"premise: the turn at {turn} is no longer drawn at the x of the text "
                        f"{text.x0}..{text.x1}")
        self.assertIn(labels.Clash(labels.CROSSED, j), choice.clashes)
        self.assertIn(f"связь {mine}: подпись {layout['edges'][i]['label']!r} пересечёт линию "
                      f"{other}; переставьте узлы или уберите подпись в сноску", said)


class TheCardALabelHangsFromIsExempt(unittest.TestCase):
    """Plan gate finding G4: a candidate hanging from its own source card is not measured against
    that card, nor against the lines drawn within its height, and the exemption is by (row, owner)
    rather than by a branch of the checking code. It carries the whole of `under_card`, so taking it
    away is what shows what it holds."""

    def test_without_it_the_labels_that_hang_from_a_card_have_no_room_at_all(self):
        differ = 0
        for name, mode, layout, _ in planned(label_models()):
            if chosen(layout, mode) != chosen(layout, mode, exempt=False):
                differ += 1
        self.assertGreater(differ, 30, f"only {differ} of the label-case plans need the exemption")

    def test_the_lines_at_the_source_cards_own_height_are_what_it_leaves_out(self):
        """A line leaving the card sideways and one coming down the gutter into its side are drawn
        within the card's height, above the text hanging under it: with the exemption the label
        stands, without it the very same place offers no room at all. The plan says nothing about
        the label under the card, because of the exemption. The sideways one has the room under
        its own line (spec 7.2) in a page; in a widget the text there, clamped with its line into
        a? — a card as short as a card is drawn — reaches the gutter under it by up to 5.5 px, where
        the text under the card begins 3.5 px down, and takes the room over its line instead (spec
        7.1 as amended a fourth time)."""
        model = cases.exit_model(["p q . .", "a? . t .", "b . . ."],
                                 ["a? -> b : ручная проверка", "a? -> t : нет", "p -> a?",
                                  "q -> a?"], nodes=cases.TALL)
        layout, warnings = flow.plan(copy.deepcopy(model), "widget", draft=True)
        self.assertEqual(said([w for w in warnings if w.startswith("связь a? -> b:")]), [], warnings)
        self.assertEqual(said(warnings), [LIES], warnings)
        under = next(c for c in chosen(layout, "widget") if c.cand.where == labels.DOWN)
        self.assertIsNone(under.room, "the label under a? no longer stands where this case reads it")
        bare = next(c for c in chosen(layout, "widget", exempt=False) if c.cand.where == labels.DOWN)
        self.assertEqual(bare.room, 0)


class TheNumbersComeFromThisModule(unittest.TestCase):
    """Spec 7.4: the label block of the script applies the anchor `flow.plan` emits and holds no
    placement rule and no offset of its own, so every number a label is drawn with lives in
    diagrams/labels.py, in one copy. What holds those numbers to the drawing is no longer a pattern
    over the script but the browser test of criterion E5, which measures the box the page draws."""

    SCRIPT = (support.SKILL / "template" / "js" / "flow.js").read_text(encoding="utf-8")
    SOURCE = (support.SKILL / "diagrams" / "flow.py").read_text(encoding="utf-8")

    def label_block(self):
        found = re.search(r"if\(e\.label\)\{.*?g\.appendChild\(t\)\}", self.SCRIPT, re.S)
        self.assertIsNotNone(found, "template/js/flow.js has no label block to read")
        return found.group(0)

    def test_the_label_block_holds_no_offset_of_its_own(self):
        """Every number a label is drawn with reaches the script inside the anchor. What the block
        still spells, once the positions are taken out of it — which point of the path the anchor
        hangs from, which field of the anchor each part is — is the halving that makes the middle
        of a segment, and that is what the `m` reference means, not an offset."""
        bare = re.sub(r"\[\d\]", "[]", self.label_block())
        self.assertEqual(sorted({int(n) for n in re.findall(r"\d+", bare)}), [2], bare)

    def test_the_label_block_holds_no_placement_rule(self):
        """It reads the anchor and the points the page drew, and nothing about the shape of the
        route: the side a line leaves by, the lattice path and the two fields the anchor replaced
        are all gone from it."""
        block = self.label_block()
        for name in ("e.sa", "e.sb", "e.path", "e.ls", "e.ly"):
            with self.subTest(name=name):
                self.assertNotIn(name, block)

    def test_every_offset_of_the_model_reaches_the_drawing_through_an_anchor(self):
        """Each number is emitted as the `dx` or `dy` of some anchor, and the label cases take a
        place that carries every one of them: a number the model measures with and never emits
        would be one the script could not draw with."""
        seen = set()
        for _, _, layout, _ in planned(label_models()):
            for e in layout["edges"]:
                if e["label"]:
                    seen |= {("dx", abs(e["la"][3])), ("dy", e["la"][4])}
        self.assertEqual(seen, {("dx", labels.LABEL_SIDE), ("dx", labels.LABEL_BESIDE),
                                ("dx", labels.LABEL_BEND), ("dy", -labels.LABEL_LIFT),
                                ("dy", labels.LABEL_SINK), ("dy", labels.LABEL_BELOW),
                                ("dy", -labels.LABEL_ABOVE), ("dy", -labels.LABEL_OVER),
                                ("dy", labels.LABEL_UNDER), ("dy", labels.LABEL_DROP)})

    def test_the_offset_under_a_segment_is_reached_two_ways_and_chosen_by_neither_alone(self):
        """LABEL_UNDER was the exception to the test above while `greedy` was the whole choice: the
        place under a horizontal second segment has the same room as the one over it wherever both
        stand in the gutter row, so greedy could never tell them apart and no plan emitted the
        number it is drawn with. It is reached two ways now. The search of spec 7.3 prices the
        lines through the place over the segment, which is what the test above rests on; and
        `fits` drops the place over a segment drawn far enough above the base of its row, whose
        text would stand on the card above it (spec 7.1 as amended a third time), so greedy is
        handed the one under.

        Which is which: wherever greedy emits the offset, the place over that segment was dropped
        before it chose, and greedy never chose between two places that both had the room."""
        offered, by_greedy = set(), []
        for _, mode, layout, _ in planned(label_models()):
            order, cands, needs, cards, _, _ = candidates(layout, mode)
            for cs in cands.values():
                offered |= {("dy", c.la[4]) for c in cs}
            keep = labels.fits(order, cands, needs, cards)[0]
            for choice in greedily(layout, mode):
                if choice.cand.la[4] != labels.LABEL_UNDER:
                    continue
                by_greedy.append(choice.edge)
                self.assertEqual([c for c in keep[choice.edge]
                                  if (c.where, c.rank) == (labels.OVER, 0)], [],
                                 "greedy reached the place under a segment with the one over it "
                                 "still standing")
        self.assertIn(("dy", labels.LABEL_UNDER), offered)
        self.assertTrue(by_greedy, "no label case hands greedy the place under a segment")
        # and the other way round, which `SEEDED_CROSSED` records instance by instance: there
        # greedy stands the label over its segment and the search walks it onto the place under
        self.assertTrue([r for r in SEEDED_CROSSED if r[2] == "U"], SEEDED_CROSSED)

    def test_there_is_one_copy_of_each_and_it_is_this_module_s(self):
        """diagrams/flow.py carries the names the tests that measure a drawn label reach for, and
        carries them by import: a second definition there could drift from the model that measures
        with it. LINE_CLEAR and the rest of the capacity numbers are flow.py's own and stay there."""
        for name in ("LABEL_BEND", "LABEL_SIDE", "LABEL_LIFT", "LABEL_SINK", "LABEL_BESIDE",
                     "LABEL_BELOW", "LABEL_ABOVE", "LABEL_OVER", "LABEL_UNDER", "LABEL_DROP",
                     "LABEL_CLEAR", "LINE_REACH", "LABEL_WORD"):
            with self.subTest(constant=name):
                self.assertEqual(getattr(flow, name), getattr(labels, name))
                self.assertIsNone(re.search(rf"^{name} = ", self.SOURCE, re.M),
                                  f"diagrams/flow.py defines {name} again")
        self.assertIsNotNone(re.search(r"^LINE_CLEAR = ", self.SOURCE, re.M))


def print_record():
    """The four frozen values above, printed from this tree as Python source: run

        cd PLUGIN && python3 -B tests/test_labels.py --record

    and paste what it prints over `LABEL_CASES`, `SEEDED_PLACES`, `SEEDED_SAID` and `SEEDED_MOVED`.
    The generator lives beside the record it writes, so a commit that moves a label regenerates it
    here rather than by hand; what the places were before that commit belongs in its report."""
    def wrapped(text, indent):
        """One digest as source: a single string while it fits the file's width, else cut at the
        `|` between two labels and continued on the next line."""
        out, line = [], ""
        for part in re.split(r"(?<= \| )", text):
            if line and len(indent) + len(line) + len(part) + 2 > 110:
                out.append(line)
                line = ""
            line += part
        out.append(line)
        return f"\n{indent}".join(repr(x) for x in out)

    cases_now = {}
    for name, mode, layout, warnings in planned(label_models()):
        cases_now.setdefault(name.rsplit(" ", 1)[0], {})[mode] = digest(layout, warnings)
    print("LABEL_CASES = {")
    for case in sorted(cases_now):
        per, key = cases_now[case], f"    {case!r}: "
        if per["widget"] == per["page"]:
            one = f"{key}{per['widget']!r},"
            print(one if len(one) <= 110 else
                  f"    {case!r}:\n        {wrapped(per['widget'], ' ' * 8)},")
        else:
            print(f"    {case!r}:\n        ({wrapped(per['widget'], ' ' * 9)},\n"
                  f"         {wrapped(per['page'], ' ' * 9)}),")
    print("}")
    places, words, beside_now = {}, [], {}
    for name, mode, layout, warnings in planned(seeded()):
        for choice in chosen(layout, mode):
            places[choice.cand.where] = places.get(choice.cand.where, 0) + 1
        words += said(warnings)
        if name in SEEDED_MOVED:
            edge = SEEDED_MOVED[name][0]
            e = next(x for x in layout["edges"] if f"{x['a']} -> {x['b']}" == edge)
            beside_now[name] = beside(e)
    ranked = [f"{k!r}: {places[k]}" for k in sorted(places, key=places.get, reverse=True)]
    print("SEEDED_PLACES = {" + ", ".join(ranked[:3]) + ",\n"
          + " " * 17 + ", ".join(ranked[3:]) + "}")
    named = {LIES: "LIES", NO_FIT: "NO_FIT", CROSSES: "CROSSES", SAME: "SAME"}
    print("SEEDED_SAID = {"
          + ", ".join(f"{named[w]}: {words.count(w)}" for w in sorted(set(words))) + "}")
    print("# SEEDED_MOVED keeps the place each one took before the switch as well, which this tree")
    print("# cannot know. The place each of them takes in it:")
    for name, (side, row) in sorted(beside_now.items()):
        print(f"#     {name}: {side}{'' if row is None else row}")


if __name__ == "__main__":
    if "--record" in sys.argv:
        print_record()
    else:
        unittest.main()
