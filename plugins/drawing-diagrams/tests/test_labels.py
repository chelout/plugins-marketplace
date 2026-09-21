"""The occupancy model against the verdicts `flow.plan` gives now.

`diagrams/labels.py` states as rectangles what `flow.room_beside`, `flow.band_obstacles`,
`flow.under_card`, `flow.label_spots` and the label loop of `flow.plan` state as branches. Nothing
calls it yet, so the thing worth asserting is that it says the same: for the shipped examples, for
the models of `tests/test_label_lines.py` and for a hundred seeded labelled instances, the walk
below — today's order, today's first fit, today's messages, over `labels.today`, `labels.occupancy`
and `labels.room` — produces the very messages `flow.plan` produces and puts every label in the
very place it puts it.

The walk is today's policy, not the model's: which rectangles a place is measured against, and what
is said about the answer, stay in `flow.plan` until the switch. Where the two differ the difference
has a test of its own below, stating both sides; there is one such class, and it is the rows a
vertical second segment ends in.
"""
import copy
import functools
import re
import unittest

import support
import bench_routing
import instances
from diagrams import flow, labels, router
from diagrams.common import ModelError, fit_prefix, label_width

import test_label_lines as cases

MODES = ("widget", "page")

# The hundred seeded labelled instances of the equivalence, and the labels they carry: every third
# edge, as the rest of the suite labels an instance (`tests/test_drawn_property.py`), with texts of
# four widths so the room is read at more than one length.
SEEDED = (20260921, 100)
SEEDED_MODE = "page"
TEXTS = ("да", "нет", "по ошибке", "ручная сверка данных")

# The seeded instances where the two readings answer differently, and what moves in each. Every one
# of them is the class `WhereTheModelReadsMoreThanTodayDoes` states: a row the second segment ends
# in. They are named rather than counted, so a sixth one is a failure and not a number.
SEEDED_DIFFER = {
    "seeded #12": "n00 -> n03 keeps the middle place on the left instead of pinning to row 2",
    "seeded #40": "n00 -> n04 keeps the middle place on the right instead of pinning to row 4",
    "seeded #57": "n09 -> n03 keeps the middle place, and n00 -> n04 then meets it",
    "seeded #61": "n05 -> n03 pins to row 6 instead of keeping the middle place",
    "seeded #97": "n08 -> n06 keeps the middle place instead of pinning to row 6",
}

# What `flow.plan` says about a label, as it says it. The walk composes the same strings, so a
# difference of place, of room — which the fit error carries as the prefix that still fits — or of
# wording is one comparison and not three.
WARN = ("связь {a} -> {b}: подпись {text!r} {where} ляжет на другую линию или подпись; "
        "переставьте узлы или уберите подпись в сноску")
FIT = ("связь {a} -> {b}: подпись {text!r} {n} симв. не помещается {where}, влезает ~{prefix}; "
       "сократите, вынесите в сноску [n] или переставьте узлы так, чтобы линия уходила вниз")
SAME = ("связи {first} и {a} -> {b}: подписи встанут в одно место и наложатся; "
        "переставьте узлы или уберите одну подпись в сноску")

LABEL_MESSAGE = re.compile(r"^(связь .*: подпись |связи .* и .*: подписи встанут )")
OVER = "над вторым отрезком"
BESIDE = "рядом со вторым отрезком"


def label_messages(warnings):
    """The messages `flow.plan` wrote about where a label stands, with the draft prefix taken off —
    a draft plan reports its layout errors as warnings, and a fit error is a layout error. The
    post-check that follows the label loop is not one of them: it has its own comparison below."""
    out = []
    for w in warnings:
        text = w[len(flow.DRAFT):] if w.startswith(flow.DRAFT) else w
        if LABEL_MESSAGE.match(text) and "пересечёт" not in text:
            out.append(text)
    return sorted(out)


def inputs(layout, mode_name):
    """What `flow.plan` hands its label loop, read back off the layout it returns: the geometry, the
    paths of the edges that routed, their offsets, the cells of the grid and the occupied ones."""
    geo = flow.Geometry(layout["mode"], layout["card_w"], layout["grid_cols"], layout["grid_rows"],
                        *flow.margin_room(layout["kind"], mode_name, layout["footnotes"]),
                        empty=layout["empty_rows"])
    offsets = [[(pt[2], pt[3]) for pt in e["path"]] for e in layout["edges"]]
    occupied = {rc for nid, rc in layout["cells"].items() if nid in layout["nodes"]}
    return geo, layout["paths"], offsets, layout["cells"], occupied


def walk(layout, mode_name):
    """The labels of a layout placed the way `flow.plan` places them, over the model. Returns its
    messages, the place it chose per edge as (`ls`, `ly`), the (label, path) pairs whose text a
    line runs through — what the post-check of `flow.plan` looks for after the loop — and the
    candidate each label was given."""
    geo, paths, offsets, cells, occupied = inputs(layout, mode_name)
    edges, card_w = layout["edges"], layout["card_w"]
    rects = labels.occupancy(cells, paths, offsets, geo, occupied)
    cards = [r for r in rects if r.kind in (labels.CARD, labels.BOUND)]
    runs = [r for r in rects if r.kind == labels.LINE]
    upright = {(j, k) for j, q in enumerate(paths) for k in range(len(q) - 1)
               if q[k][0] == q[k + 1][0]}
    # labels with a single place first, so that the ones choosing a row see them all
    order = sorted((i for i, e in enumerate(edges) if e["label"]),
                   key=lambda i: len(paths[i]) >= 3 and paths[i][2][1] != paths[i][1][1])
    out, keys, placed, chosen, crossed, picked = [], {}, [], {}, [], {}
    for i in order:
        e, text = edges[i], edges[i]["label"]
        need = label_width(text)
        cands = labels.today(i, e, paths[i], need, paths, offsets, geo, cells, occupied, card_w)
        # `room` counts the cards and the bounds, `line_room` the lines as well — and the labels
        # already placed only beside a vertical second segment, which is where `flow.plan` consults
        # them. A label over a horizontal second segment has no `line_room`: the lines that cross it
        # are looked for once every label stands somewhere
        wide = [labels.room(c, cards) for c in cands]
        tight = [w if c.where == OVER else
                 min(w, labels.room(c, runs + (placed if c.where == BESIDE else [])))
                 for c, w in zip(cands, wide)]
        spot = next((c for c, t in zip(cands, tight) if need <= t), None)
        if spot is None:
            spot = next((c for c, w in zip(cands, wide) if need <= w), None)
            if spot is not None:
                out.append(WARN.format(a=e["a"], b=e["b"], text=text, where=spot.where))
        if spot is None:
            at = max(range(len(cands)), key=lambda k: wide[k])
            spot, room = cands[at], max(wide[at], 0)
            out.append(FIT.format(a=e["a"], b=e["b"], text=text, n=len(text), where=spot.where,
                                  prefix=fit_prefix(text, lambda s: label_width(s) <= room)))
        chosen[i], picked[i] = (spot.ls, spot.ly), spot
        placed += list(spot.rects)
        if spot.key in keys:
            out.append(SAME.format(first=keys[spot.key], a=e["a"], b=e["b"]))
        keys[spot.key] = f"{e['a']} -> {e['b']}"
        if spot.where == OVER:
            crossed += [(i, run.owner[0]) for run in runs if run.owner in upright
                        and any(labels.overlaps(r, run) for r in spot.rects)]
    return sorted(out), chosen, sorted(crossed), picked


def post_check(layout):
    """The (label, path) pairs the post-check of `flow.plan` warns about: a line whose lattice
    column lies strictly inside a horizontal second segment and which spans the row of that
    segment."""
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


def places(layout):
    """The place `flow.plan` chose per labelled edge, as (`ls`, `ly`)."""
    return {i: (e["ls"], e.get("ly")) for i, e in enumerate(layout["edges"]) if e["label"]}


def planned(corpus):
    """Every model of a corpus planned as a draft — the only plan that answers for a model whose
    label does not fit — with what today said and what the walk says."""
    for name, model, mode in corpus:
        layout, warnings = flow.plan(copy.deepcopy(model), mode, draft=True)
        yield name, mode, layout, label_messages(warnings), walk(layout, mode)


def disagreements(corpus):
    """The models where the messages or the places differ, as (name, today, the model)."""
    out = []
    for name, mode, layout, today, (said, chosen, _, _) in planned(corpus):
        if said != today or chosen != places(layout):
            out.append((name, (today, places(layout)), (said, chosen)))
    return out


def report(bad, total):
    text = [f"{len(bad)} of {total} planned models answer differently:"]
    for name, today, said in bad[:5]:
        text += [f"  {name}", f"    flow.plan: {today}", f"    labels:    {said}"]
    return "\n".join(text)


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
            # from the seeded stream past the hundred of the equivalence (instance 104 of
            # `instances.small(SEEDED[0], …)`), which is where two labels first take one place: no
            # shipped example and no case of test_label_lines.py reaches that warning
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


class TheModelSaysWhatTodaySays(unittest.TestCase):
    """Criterion E2, first half: over today's candidates the occupancy model gives the verdict
    `flow.plan` gives — fits, lies on a line or a label, does not fit, with the room the message
    carries — and puts the label in the same place."""

    def test_the_shipped_examples(self):
        corpus = examples()
        self.assertGreaterEqual(len(corpus), 8, "harness: the examples no longer reach the walk")
        bad = disagreements(corpus)
        self.assertEqual(bad, [], report(bad, len(corpus)))

    def test_the_models_of_the_label_cases(self):
        corpus = label_models()
        bad = disagreements(corpus)
        self.assertEqual(bad, [], report(bad, len(corpus)))

    def test_a_hundred_seeded_labelled_instances(self):
        corpus = seeded()
        self.assertGreaterEqual(len(corpus), 90, "harness: too few seeded instances plan at all")
        bad = disagreements(corpus)
        self.assertEqual(sorted(name for name, *_ in bad), sorted(SEEDED_DIFFER),
                         report(bad, len(corpus)))

    def test_the_corpus_exercises_every_place(self):
        """What the cases above have to hold to read anything: every shape of route a label can hang
        from is among them, a candidate that reaches into a second row is there too, and every kind
        of message the walk composes is heard from `flow.plan` at least once."""
        seen, said = set(), set()
        for name, mode, layout, today, _ in planned(examples() + label_models() + seeded()):
            geo, paths, offsets, cells, occupied = inputs(layout, mode)
            for i, e in enumerate(layout["edges"]):
                if not e["label"]:
                    continue
                spot = labels.today(i, e, paths[i], label_width(e["label"]), paths, offsets, geo,
                                    cells, occupied, layout["card_w"])[0]
                seen.add(spot.where)
                seen.add(len(spot.rects) > 1)
            for m in today:
                said.add("ляжет" if "ляжет" in m else
                         "не помещается" if "не помещается" in m else "одно место")
        self.assertEqual(seen, {"у выхода вниз", "у выхода вверх", "у выхода вбок", OVER, BESIDE,
                                True, False})
        self.assertEqual(said, {"ляжет", "не помещается", "одно место"},
                         "a message the walk composes is never heard from flow.plan")


class WhereTheModelReadsMoreThanTodayDoes(unittest.TestCase):
    """The differences the equivalence above is written around. Each is a check today's code makes
    in one place and not in another; the model makes it everywhere, and each case states both
    sides."""

    def test_the_readings_differ_only_in_a_row_the_second_segment_ends_in(self):
        """In a row a vertical second segment ends in, `flow.band_obstacles` keeps every line that
        crosses the row and drops every line that runs along it, whatever either is drawn at. The
        model keeps what lies past the bend drawn there, whichever way it runs: the text stands at
        the middle of the segment, half a row of the lattice away from that bend.

        Over the whole corpus this is the only place the two readings differ — the rows in between,
        and every other shape of route, read alike."""
        rows, differing = set(), 0
        for name, mode, layout, today, _ in planned(examples() + label_models() + seeded()):
            geo, paths, offsets, cells, occupied = inputs(layout, mode)
            rects = labels.occupancy(cells, paths, offsets, geo, occupied)
            runs = [r for r in rects if r.kind == labels.LINE]
            for i, e in enumerate(layout["edges"]):
                p = paths[i]
                if not e["label"] or len(p) < 3 or p[2][1] == p[1][1]:
                    continue
                lo, hi = min(p[1][1], p[2][1]), max(p[1][1], p[2][1])
                need = label_width(e["label"])
                spots = flow.label_spots(i, e, p, paths, offsets, geo, cells, occupied,
                                         layout["card_w"])
                cands = labels.today(i, e, p, need, paths, offsets, geo, cells, occupied,
                                     layout["card_w"])
                for s, c in zip(spots, cands):
                    for rect in c.rects:
                        # a place pinned to a row reads the lines along it whatever they are
                        # drawn at; the unpinned one reads them only in the rows in between
                        along = s.get("ly") is not None or lo < rect.Y < hi
                        _, lns = flow.band_obstacles(rect.Y, (i, 1), paths, offsets, geo, occupied,
                                                     along)
                        was = flow.room_beside(c.start, c.grow, lns, labels.INF)
                        now = labels.room(c._replace(rects=(rect,), limit=labels.INF), runs)
                        if abs(was - now) > 1e-9:
                            differing += 1
                            rows.add(rect.Y in (lo, hi) and s.get("ly") is None)
        self.assertEqual(rows, {True},
                         "a row that is neither an end of the second segment nor read without a "
                         "pinned row now reads differently")
        self.assertGreater(differing, 10, f"harness: only {differing} rows read differently at all")

    def test_the_post_check_of_today_is_the_segment_and_the_model_is_the_text(self):
        """A label over a horizontal second segment: `flow.plan` warns once per line whose lattice
        column lies inside that segment and which spans its row, wherever the text stands along it;
        the model warns once per line that runs through the text's own rectangle. So today's check
        answers for lines the text never reaches, and misses the line that comes down into the row
        and turns there, which stops on the text rather than passing it."""
        only_today = only_model = both = 0
        for name, mode, layout, today, (_, _, crossed, picked) in planned(
                examples() + label_models() + seeded()):
            geo, paths, offsets, cells, occupied = inputs(layout, mode)
            rects = labels.occupancy(cells, paths, offsets, geo, occupied)
            was, now = set(post_check(layout)), set(crossed)
            both += len(was & now)
            for i, j in was - now:
                only_today += 1
                met = [r for r in rects if r.kind == labels.LINE and r.owner[0] == j
                       and any(labels.overlaps(t, r) for t in picked[i].rects)]
                self.assertEqual(met, [], f"{name}: that line does run through the text")
            for i, j in now - was:
                only_model += 1
                p = paths[i]
                spans = [(lo, hi) for axis, line, lo, hi in router.segments(paths[j])
                         if axis == "v" and min(p[1][0], p[2][0]) < line < max(p[1][0], p[2][0])]
                self.assertTrue(all(not (lo < p[1][1] < hi) for lo, hi in spans),
                                f"{name}: {i} and {j} cross inside the segment, so today warns too")
        self.assertGreater(both, 0, "harness: the two checks never agree at all")
        self.assertGreater(only_today, 0, "harness: today's check never reaches past the text")
        self.assertGreater(only_model, 0, "harness: no line ever stops on a text today misses")

    def test_a_label_placed_already_is_seen_only_beside_a_vertical_second_segment(self):
        """`flow.plan` consults the labels it has placed only where a label has a row to choose —
        beside a vertical second segment. Here the text hanging under a short card runs along the
        row into the text of a line leaving the same card sideways, and nothing is said; the model's
        two rectangles meet."""
        model = cases.exit_model([". q . .", "a? t . .", "b . . ."],
                                 ["a? -> b : ручная сверка", "a? -> t : нет", "q -> t"],
                                 nodes=cases.TALL)
        layout, warnings = flow.plan(copy.deepcopy(model), "widget", draft=True)
        self.assertEqual(label_messages(warnings), [],
                         "today's code no longer keeps quiet about these two labels")
        geo, paths, offsets, cells, occupied = inputs(layout, "widget")
        spots = [labels.today(i, e, paths[i], label_width(e["label"]), paths, offsets, geo, cells,
                              occupied, layout["card_w"])[0]
                 for i, e in enumerate(layout["edges"]) if e["label"]]
        self.assertEqual([s.where for s in spots], ["у выхода вниз", "у выхода вбок"])
        met = [(a, b) for a in spots[0].rects for b in spots[1].rects
               if labels.overlaps(a, b, labels.CLEARANCE[labels.LABEL], 0)]
        self.assertTrue(met, f"the model says these two texts stand clear: {spots[0]}, {spots[1]}")


class TheNumbersComeFromTheScript(unittest.TestCase):
    SCRIPT = (support.SKILL / "template" / "js" / "flow.js").read_text(encoding="utf-8")

    def test_every_offset_the_model_measures_with_is_the_script_s(self):
        for pattern, name in ((r"lx=rt\?p2\.x-(\d+):", "LABEL_BEND"),
                              (r"ly=base\(e\.path\[1\]\[1\]\)-(\d+)", "LABEL_OVER"),
                              (r"\(p1\.y\+p2\.y\)/2\)\+(\d+);", "LABEL_DROP"),
                              (r"e\.sa==='B'\)\{lx=a0\.x\+(\d+);", "LABEL_BESIDE"),
                              (r"e\.sa==='B'\)\{lx=a0\.x\+\d+;ly=a0\.y\+(\d+)\}", "LABEL_BELOW"),
                              (r"e\.sa==='T'\)\{lx=a0\.x\+\d+;ly=a0\.y-(\d+)\}", "LABEL_ABOVE"),
                              (r"e\.sa==='R'\)\{lx=a0\.x\+(\d+);", "LABEL_SIDE")):
            with self.subTest(constant=name):
                found = re.findall(pattern, self.SCRIPT)
                self.assertEqual(len(found), 1, f"{pattern!r} in template/js/flow.js")
                self.assertEqual(int(found[0]), getattr(labels, name))

    def test_the_two_copies_of_every_number_agree(self):
        """Until the label loop moves over, `diagrams/flow.py` carries its own copy of every number
        but LABEL_OVER, which it has no place for: one of them drifting would leave the model
        measuring a place the planner does not."""
        for name in ("LABEL_BEND", "LABEL_SIDE", "LABEL_BESIDE", "LABEL_BELOW", "LABEL_ABOVE",
                     "LABEL_DROP", "LABEL_CLEAR", "LINE_REACH", "LABEL_WORD"):
            with self.subTest(constant=name):
                self.assertEqual(getattr(labels, name), getattr(flow, name))


if __name__ == "__main__":
    unittest.main()
