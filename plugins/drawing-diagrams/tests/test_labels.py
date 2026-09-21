"""Where `flow.plan` stands a label, and what it says about it.

`diagrams/labels.py` places every label now: `flow.plan` hands `labels.place` the routed edges and
their texts and gets a `Choice` each — the place it took, the warnings that place raises with their
owners, or the room when the text fits nowhere — and writes the messages from them. The equivalence
this file used to hold, the model walked beside `flow.room_beside`, `flow.band_obstacles`,
`flow.under_card` and `flow.label_spots`, has nothing left to compare against: those functions are
gone with the switch.

What replaces it is a record. The whole corpus below — the shipped examples, the models of
`tests/test_label_lines.py` and a hundred seeded labelled instances, 174 plans — was planned once
with the tree before the switch and once with this one, and the only differences are the two
readings the switch carries (spec 7.1 as amended on 2026-09-21): five seeded instances move a
label, one message follows them, and the check of a label over a horizontal second segment answers
41 times where it answered 149. Everything frozen here is what a reader can check without running
that comparison again — every place of every label of the label cases with what was said about it,
the tally of the seeded corpus, and the five instances that moved — and each of the two readings has
a test that states the rule it replaced.
"""
import copy
import functools
import re
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
# the anchor (`R2` is the right side pinned to lattice row 2, `R` the side with no row of its own),
# and then the messages by their word. One string per model, and one entry per model of
# `tests/test_label_lines.py`; a pair where the two modes answer differently.
LABEL_CASES = {
    'a card alone in its row': 'a?->b R | a?->q R',
    'a line into the next card under a short card':
        ('a?->b R | a?->p R2 ; ляжет',
         'a?->b R | a?->p R2'),
    'a lone exit': 'a?->b R | a?->x R',
    'along the gutter over an exit up':
        ('a?->e R | a?->b R ; ляжет',
         'a?->e R | a?->b R'),
    'along the gutter, 4 away': 'a?->f R | a?->d R | a?->g R',
    'along the gutter, 4 towards':
        ('a?->d R | a?->c R ; ляжет',
         'a?->d R | a?->c R'),
    'along the gutter, 8 towards': 'a?->b R | a?->g R ; ляжет',
    "along the row ['. b d', 'e . f', '. g .']": 'e->f R ; ляжет',
    "along the row ['d b .', 'f . e', '. g .']": 'e->f R ; ляжет',
    'an exit up that does not fit': 'a?->d R | a?->c R | b->d R | c->b R | d->b R | d->c R ; ляжет',
    'beside a second segment, a banded row': 'd->b R2 ; ляжет',
    'beside a second segment, a gutter row': 'a->c R | a->d L2 | e->c R',
    'exit down': 'a?->b R | a?->c R ; ляжет',
    'exit up': 'a?->d R | a?->c R | b->d R | c->b R | d->b R | d->c R ; ляжет',
    "lines at the source card's own height, beside": 'a?->b R | a?->t R',
    "lines at the source card's own height, into": 'a?->b R | a?->t R ; ляжет',
    "loop ['. a', 'c b?', '. d'] c -> a": 'b?->c R | b?->d R ; ляжет',
    "loop ['. a', 'c b?', '. d'] c -> d": 'b?->c R | b?->d R',
    "loop ['a .', 'b? c', 'd .'] c -> a": 'b?->c R | b?->d R ; ляжет',
    "loop ['a .', 'b? c', 'd .'] c -> d": 'b?->c R | b?->d R',
    "loop back ['. a', 'c b?', '. d'] back": 'b?->c R | b?->d R ; ляжет',
    "loop back ['. a', 'c b?', '. d'] last": 'b?->c R | b?->d R ; ляжет',
    "loop back ['a .', 'b? c', 'd .'] back": 'b?->c R | b?->d R',
    "loop back ['a .', 'b? c', 'd .'] last": 'b?->c R | b?->d R',
    "loop below ['. a', 'c b?', 'e d']": 'b?->c R | b?->d R',
    "loop below ['a .', 'b? c', 'd e']": 'b?->c R | b?->d R',
    'past the right edge':
        ('a?->b R | a?->r R ; не помещается',
         'a?->b R | a?->r R'),
    'the next card limits the room':
        ('a?->b R | a?->t R ; не помещается',
         'a?->b R | a?->t R'),
    'through the gutter past the label': 'a?->c R4 | a?->b R ; ляжет',
    'turning from the far side, down': 'a?->b R | a?->c R',
    'turning from the far side, up': 'a?->c R | a?->b R',
    'two labels in one place':
        ('n00->n06 R | n01->n13 R2 | n04->n01 R | n07->n00 R2 | n09->n14 R | n11->n08 R | n14->n03 R4 | '
         'n15->n06 R ; ляжет, не помещается, одно место, пересечёт, пересечёт, пересечёт, пересечёт',
         'n00->n06 R | n01->n13 R | n04->n01 R | n07->n00 R | n09->n14 R | n11->n08 R | n14->n03 R4 | '
         'n15->n06 R ; ляжет, ляжет, одно место, пересечёт, пересечёт, пересечёт, пересечёт, пересечёт'),
    "under the row's own line": 'c->a R',
}

# The 442 labels of the hundred seeded instances, by the place they take and by what is said about
# them. Two labels never fall in one place across the hundred, which is why the label cases above
# carry a model that does (the first instance of the same stream past the hundred).
SEEDED_PLACES = {"над вторым отрезком": 171, "рядом со вторым отрезком": 161, "у выхода вбок": 62,
                 "у выхода вниз": 34, "у выхода вверх": 14}
SEEDED_SAID = {LIES: 50, NO_FIT: 24, CROSSES: 32}

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
    """The place of a labelled edge as the record below has always named it. Only a place beside a
    vertical second segment hangs from point 1 of the path and has a side and a row to name; every
    other shape of route offers one place, which this record has always called `R`."""
    if e["la"][0] != 1:
        return "R"
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
    """Today's places of every label of a layout, per edge, with what `greedy` measures them
    against: the cards and the bounds, the lines, the widths and the vertical runs."""
    geo, paths, offsets, cells, occupied = inputs(layout, mode_name)
    edges, card_w = layout["edges"], layout["card_w"]
    rects = labels.occupancy(cells, paths, offsets, geo, occupied)
    order = sorted((i for i, e in enumerate(edges) if e["label"]),
                   key=lambda i: len(paths[i]) >= 3 and paths[i][2][1] != paths[i][1][1])
    needs = {i: label_width(edges[i]["label"]) for i in order}
    cands = {i: labels.today(i, edges[i], paths[i], needs[i], paths, offsets, geo, cells, occupied,
                             card_w) for i in order}
    return (order, cands, needs,
            [r for r in rects if r.kind in (labels.CARD, labels.BOUND)],
            [r for r in rects if r.kind == labels.LINE],
            labels.uprights(paths))


def chosen(layout, mode_name, exempt=True):
    """The choices of a layout, by the road `labels.place` itself takes. `exempt=False` takes the
    exemptions of spec 7.1 off every candidate, which is what the test of them needs."""
    order, cands, needs, cards, runs, upright = candidates(layout, mode_name)
    if not exempt:
        cands = {i: [c._replace(exempt=frozenset()) for c in cs] for i, cs in cands.items()}
    return labels.greedy(order, cands, needs, cards, runs, upright)


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
        """What the record above has to hold to read anything: every shape of route a label can hang
        from is taken somewhere in the corpus, a place that reaches into more than one row is taken
        too, and every kind of message is heard at least once."""
        taken, rows, words = set(), set(), set()
        for name, mode, layout, warnings in planned(examples() + label_models() + seeded()):
            for choice in chosen(layout, mode):
                taken.add(choice.cand.where)
                rows.add(len(choice.cand.rects) > 1)
            words |= set(said(warnings))
        self.assertEqual(taken, {labels.DOWN, labels.UP, labels.SIDEWAYS, labels.OVER,
                                 labels.BESIDE})
        self.assertEqual(rows, {True, False})
        self.assertEqual(words, {LIES, NO_FIT, CROSSES, SAME})

    def test_place_is_greedy_over_todays_candidates(self):
        """The interface of this commit: `labels.place` is `labels.greedy` over `labels.today` and
        nothing else, so the road the tests above take is the one `flow.plan` takes."""
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
                for rect in (r for c in cs if c.la[1] == "m" for r in c.rects):
                    if rect.Y not in bend or rect.Y not in (lo, hi):
                        continue
                    ends += 1
                    want = ((bend[rect.Y] + 1, labels.INF) if rect.Y == lo
                            else (-labels.INF, bend[rect.Y] - 1))
                    self.assertEqual((rect.y0, rect.y1), want,
                                     f"{name}: the text of edge {i} does not stay past the bend")
        self.assertGreater(ends, 10, f"harness: only {ends} end rows are read at all")

    def test_a_label_over_a_horizontal_second_segment_is_checked_by_its_text(self):
        """The check before the switch warned once per line whose lattice column lay inside that
        segment and which spanned its row, wherever along it the text stood; the model warns once
        per line that runs through the text's own rectangle. So the old one answered for lines the
        text never reaches, and missed the line that comes down into the row and turns there, which
        stops on the text instead of passing it."""
        only_before = only_now = both = 0
        for name, mode, layout, _ in planned(examples() + label_models() + seeded()):
            geo, paths, offsets, cells, occupied = inputs(layout, mode)
            rects = labels.occupancy(cells, paths, offsets, geo, occupied)
            choices = chosen(layout, mode)
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
        stands, without it the very same place offers no room at all."""
        model = cases.exit_model(["p q . .", "a? . t .", "b . . ."],
                                 ["a? -> b : ручная проверка", "a? -> t : нет", "p -> a?",
                                  "q -> a?"], nodes=cases.TALL)
        layout, warnings = flow.plan(copy.deepcopy(model), "widget", draft=True)
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
                                ("dy", labels.LABEL_BELOW), ("dy", -labels.LABEL_ABOVE),
                                ("dy", -labels.LABEL_OVER), ("dy", labels.LABEL_DROP)})

    def test_there_is_one_copy_of_each_and_it_is_this_module_s(self):
        """diagrams/flow.py carries the names the tests that measure a drawn label reach for, and
        carries them by import: a second definition there could drift from the model that measures
        with it. LINE_CLEAR and the rest of the capacity numbers are flow.py's own and stay there."""
        for name in ("LABEL_BEND", "LABEL_SIDE", "LABEL_LIFT", "LABEL_BESIDE", "LABEL_BELOW",
                     "LABEL_ABOVE", "LABEL_OVER", "LABEL_DROP", "LABEL_CLEAR", "LINE_REACH",
                     "LABEL_WORD"):
            with self.subTest(constant=name):
                self.assertEqual(getattr(flow, name), getattr(labels, name))
                self.assertIsNone(re.search(rf"^{name} = ", self.SOURCE, re.M),
                                  f"diagrams/flow.py defines {name} again")
        self.assertIsNotNone(re.search(r"^LINE_CLEAR = ", self.SOURCE, re.M))


if __name__ == "__main__":
    unittest.main()
