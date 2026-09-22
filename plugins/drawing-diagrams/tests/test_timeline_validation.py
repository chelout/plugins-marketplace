"""Entity and moment checks of timeline.plan, each held by its exact message: model errors stay
fatal even when layout errors may be drafted, layout errors turn into draft warnings, warnings leave
the plan laid out. A fit error is a layout error that plan() also lists as a fit: fatal without
draft, a draft warning with it, and its message carries the numbers of each mode.

A timeline has no grid and no edges, so the checks here are those of the entity loop (id, label,
the list itself and its width in chips) and those of the moment loop (id, the rail mark, the
required title, what the card fits, the states named and how wide a chip value is)."""
import copy
import unittest

import support  # noqa: F401
from diagrams import timeline
from diagrams.common import ModelError

DRAFT = "черновик: "


def model():
    """One entity and two moments: the least a timeline accepts, with nothing to object to."""
    return {"kind": "timeline", "entities": [{"id": "e", "label": "E"}],
            "moments": [{"id": "m1", "label": "t1", "title": "Ок", "states": {"e": "да"}},
                        {"id": "m2", "label": "t2", "title": "Ок", "states": {"e": "нет"}}]}


def moment_model(**first):
    """The same timeline with the fields given applied to its first moment."""
    m = model()
    m["moments"][0].update(first)
    return m


def entities_model(count):
    """`count` entities and no states, so the chip count is the only thing past a limit."""
    m = model()
    m["entities"] = [{"id": f"e{i}", "label": f"E{i}"} for i in range(count)]
    for moment in m["moments"]:
        del moment["states"]
    return m


def many_moments_model(count):
    """`count` moments, each valid on its own, so their number is the only thing past a limit."""
    m = model()
    m["moments"] = [{"id": f"m{i}", "label": f"t{i}", "title": "Ок"} for i in range(count)]
    return m


class TimelineValidation(unittest.TestCase):
    def assertValid(self, model):
        for mode in ("widget", "page"):
            for draft in (False, True):
                with self.subTest(mode=mode, draft=draft):
                    _, warnings = timeline.plan(copy.deepcopy(model), mode, draft=draft)
                    self.assertEqual(warnings, [])

    def assertInvalid(self, model, message):
        for mode in ("widget", "page"):
            for draft in (False, True):
                with self.subTest(mode=mode, draft=draft):
                    with self.assertRaises(ModelError) as ctx:
                        timeline.plan(copy.deepcopy(model), mode, draft=draft)
                    self.assertEqual(ctx.exception.errors, [message])
                    self.assertEqual(ctx.exception.layout, [])
                    self.assertEqual(ctx.exception.fit, [])

    def assertWarning(self, model, message):
        """The one warning both modes raise, with the plan laid out and no draft."""
        for mode in ("widget", "page"):
            for draft in (False, True):
                with self.subTest(mode=mode, draft=draft):
                    layout, warnings = timeline.plan(copy.deepcopy(model), mode, draft=draft)
                    self.assertFalse(layout["draft"])
                    self.assertEqual(warnings, [message])

    def assertDrafted(self, model, messages, fit, alone):
        """`messages` maps each mode to the layout errors it expects, in order: fatal without draft,
        each of them also a fit error when `fit`; with draft the plan is laid out as a draft and the
        leading warnings are those errors behind the draft prefix. `alone` holds them to be every
        warning the plan raises, otherwise the warnings without the prefix are not compared."""
        for mode in ("widget", "page"):
            expected = messages[mode]
            with self.subTest(mode=mode, draft=False):
                with self.assertRaises(ModelError) as ctx:
                    timeline.plan(copy.deepcopy(model), mode)
                self.assertEqual(ctx.exception.errors, expected)
                self.assertEqual(ctx.exception.layout, expected)
                self.assertEqual(ctx.exception.fit, expected if fit else [])
            with self.subTest(mode=mode, draft=True):
                layout, warnings = timeline.plan(copy.deepcopy(model), mode, draft=True)
                self.assertTrue(layout["draft"])
                drafted = [DRAFT + m for m in expected]
                if alone:
                    self.assertEqual(warnings, drafted)
                else:
                    self.assertEqual([w for w in warnings if w.startswith(DRAFT)], drafted)

    def assertLayout(self, model, **messages):
        """Layout errors that are no fit errors; warnings besides the drafted ones may come too."""
        self.assertDrafted(model, messages, fit=False, alone=False)

    def assertFit(self, model, **messages):
        """Fit errors, each the whole message of its mode, with nothing else raised beside them."""
        self.assertDrafted(model, messages, fit=True, alone=True)

    def test_entity_id_charset(self):
        # a timeline entity has no decision form, so a trailing ? is refused like any other character
        valid = model()
        self.assertValid(valid)
        for eid, message in (("E2", "сущность 'E2': id только из строчных латинских букв, цифр и _"),
                             ("e-2", "сущность 'e-2': id только из строчных латинских букв, цифр и _"),
                             ("e2?", "сущность 'e2?': id только из строчных латинских букв, цифр и _")):
            with self.subTest(eid=eid):
                invalid = copy.deepcopy(valid)
                invalid["entities"].append({"id": eid, "label": "X"})
                self.assertInvalid(invalid, message)

    def test_entity_id_missing_or_empty(self):
        # an entity that is no mapping at all has no id either, and is reported as one without
        valid = model()
        self.assertValid(valid)
        message = "сущность None: id только из строчных латинских букв, цифр и _"
        for case, entity in (("absent", {"label": "X"}), ("null", {"id": None, "label": "X"}),
                             ("not a mapping", "e2")):
            with self.subTest(entity=case):
                invalid = copy.deepcopy(valid)
                invalid["entities"].append(entity)
                self.assertInvalid(invalid, message)
        invalid = copy.deepcopy(valid)
        invalid["entities"].append({"id": "", "label": "X"})
        self.assertInvalid(invalid, "сущность '': id только из строчных латинских букв, цифр и _")

    def test_duplicate_entity_id(self):
        valid = model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["entities"].append({"id": "e", "label": "E2"})
        self.assertInvalid(invalid, "сущность e: id повторяется")

    def test_entity_label_required(self):
        # white space alone is a label here, unlike a moment's title
        valid = model()
        self.assertValid(valid)
        for case, label in (("absent", None), ("null", None), ("empty", "")):
            with self.subTest(label=case):
                invalid = copy.deepcopy(valid)
                if case == "absent":
                    del invalid["entities"][0]["label"]
                else:
                    invalid["entities"][0]["label"] = label
                self.assertInvalid(invalid, "сущность e: нет label")

    def test_entities_required(self):
        valid = model()
        self.assertValid(valid)
        for entities in (None, []):
            with self.subTest(entities=entities):
                invalid = copy.deepcopy(valid)
                invalid["entities"] = entities
                for moment in invalid["moments"]:
                    del moment["states"]
                self.assertInvalid(invalid, "timeline: нужен список entities, чьи состояния показываются чипами")

    def test_too_many_entities_warns(self):
        self.assertValid(entities_model(4))
        self.assertWarning(entities_model(5), "сущностей 5: больше четырёх чипов в карточке читаются плохо")

    def test_two_moments_required(self):
        valid = model()
        self.assertValid(valid)
        for count in (0, 1):
            with self.subTest(moments=count):
                invalid = copy.deepcopy(valid)
                invalid["moments"] = invalid["moments"][:count]
                self.assertInvalid(invalid, "timeline: нужно хотя бы два момента")

    def test_too_many_moments(self):
        self.assertValid(many_moments_model(12))
        self.assertLayout(
            many_moments_model(25),
            widget=["моментов 25, режим widget допускает до 12; разбейте историю"],
            page=["моментов 25, режим page допускает до 24; разбейте историю"])

    def test_moment_id_charset(self):
        # a moment with an invalid id is skipped, so its own fields raise nothing beside the id
        valid = model()
        self.assertValid(valid)
        for mid, message in (("M2", "момент 'M2': id только из строчных латинских букв, цифр и _"),
                             ("m-2", "момент 'm-2': id только из строчных латинских букв, цифр и _"),
                             ("m2?", "момент 'm2?': id только из строчных латинских букв, цифр и _")):
            with self.subTest(mid=mid):
                invalid = copy.deepcopy(valid)
                invalid["moments"][1]["id"] = mid
                self.assertInvalid(invalid, message)

    def test_moment_id_missing_or_empty(self):
        valid = model()
        self.assertValid(valid)
        for case, message in (("absent", "момент None: id только из строчных латинских букв, цифр и _"),
                              ("null", "момент None: id только из строчных латинских букв, цифр и _"),
                              ("empty", "момент '': id только из строчных латинских букв, цифр и _")):
            with self.subTest(mid=case):
                invalid = copy.deepcopy(valid)
                if case == "absent":
                    del invalid["moments"][1]["id"]
                else:
                    invalid["moments"][1]["id"] = None if case == "null" else ""
                self.assertInvalid(invalid, message)

    def test_duplicate_moment_id(self):
        valid = model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["moments"][1]["id"] = "m1"
        self.assertInvalid(invalid, "момент m1: id повторяется")

    def test_moment_label_must_fit_the_rail(self):
        # the rail is 64 px in widget and 80 in page, 18 of them the mark's own margin; this mark is
        # wider than both rails, so one message answers for both modes
        self.assertValid(moment_model(label="t1"))
        message = "момент m1: метка 'Очень длинная метка' шире рельса; укоротите"
        self.assertLayout(moment_model(label="Очень длинная метка"), widget=[message], page=[message])

    def test_moment_label_defaults_to_the_id(self):
        # the mark the width check reads, and the one the rail draws, is the id when none is given
        valid = model()
        del valid["moments"][0]["label"]
        self.assertValid(valid)
        layout, _ = timeline.plan(copy.deepcopy(valid), "widget")
        self.assertEqual([r["label"] for r in layout["rows"]], ["m1", "t2"])

    def test_title_required(self):
        # absent, null, empty and white space alone are one missing title
        valid = model()
        self.assertValid(valid)
        for case, title in (("absent", None), ("null", None), ("empty", ""), ("blank", " \t ")):
            with self.subTest(title=case):
                invalid = copy.deepcopy(valid)
                if case == "absent":
                    del invalid["moments"][0]["title"]
                else:
                    invalid["moments"][0]["title"] = title
                self.assertInvalid(invalid, "момент m1: нет title")

    def test_title_must_fit(self):
        self.assertValid(moment_model(title="Короткий заголовок"))
        self.assertFit(moment_model(title=("Заголовок момента " * 9).strip()),
                       widget=["момент m1: заголовок 161 симв., влезает 74"],
                       page=["момент m1: заголовок 161 симв., влезает 127"])

    def test_text_word_must_fit(self):
        self.assertValid(moment_model(text="Короткий текст"))
        self.assertFit(moment_model(text="w" * 170),
                       widget=["момент m1: слово 170 симв., влезает ~86"],
                       page=["момент m1: слово 170 симв., влезает ~149"])

    def test_text_must_fit_two_lines(self):
        self.assertFit(moment_model(text=("слово " * 60).strip()),
                       widget=["момент m1: текст 359 симв., в две строки влезает ~171"],
                       page=["момент m1: текст 359 симв., в две строки влезает ~300"])

    def test_state_entity_must_be_described(self):
        valid = model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["moments"][0]["states"]["x"] = "1"
        self.assertInvalid(invalid, "момент m1: состояние для неизвестной сущности 'x'")

    def test_long_chip_value_warns(self):
        self.assertValid(moment_model(states={"e": "з" * 28}))
        self.assertWarning(moment_model(states={"e": "з" * 29}),
                           "момент m1: состояние e длиннее 28 символов, чип станет широким")


if __name__ == "__main__":
    unittest.main()
