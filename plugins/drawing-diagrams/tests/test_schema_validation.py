"""Every validation check of schema.plan, each held by its exact message: the group, grid, table,
column, placement and edge checks of plan() and of the helpers it calls to validate — parse_grid,
check_placement and parse_edge.

schema.plan takes `draft` and does nothing with it. A layout error — a grid too wide, a line with
nowhere to attach, an anchor already taken — is raised exactly like a model error, with draft on as
with it off, and the layout it returns carries no draft flag; flow.plan instead lays the plan out
and turns those errors into «черновик: » warnings. schema.plan also marks no error a fit error: the
key row too long for its card, the check whose counterpart in flow is fatal, is an ordinary warning
here. Both are asserted as they stand today.

A message that carries numbers or advice is written out whole, per mode, never computed from the
code under test."""
import copy
import unittest

import support  # noqa: F401
from diagrams import schema
from diagrams.common import ModelError

MODES = ("widget", "page")


def per_mode(spec):
    """One message both modes raise, a list of them, or a mode -> list mapping of what differs."""
    if isinstance(spec, dict):
        return {mode: list(spec[mode]) for mode in MODES}
    if isinstance(spec, str):
        return {mode: [spec] for mode in MODES}
    return {mode: list(spec) for mode in MODES}


def model():
    """One table, one key column, one cell: the smallest schema that plans without a warning."""
    return {"kind": "schema", "groups": {"g": {"label": "G", "ramp": "teal"}},
            "tables": [{"id": "t", "name": "T", "group": "g",
                        "columns": [{"name": "id", "type": "uuid", "flags": ["PK"]}]}],
            "grid": ["t"]}


def table(tid, columns=("k",)):
    return {"id": tid, "name": tid.upper(), "group": "g",
            "columns": [{"name": name, "flags": ["PK"]} for name in columns]}


def tables_model(tables, grid, edges=()):
    return {"kind": "schema", "groups": {"g": {"label": "G", "ramp": "teal"}},
            "tables": list(tables), "grid": list(grid), "edges": list(edges)}


def edge_model(edges, grid=("a b",), a_columns=("k",), b_columns=("m",)):
    """Two tables side by side, adjacent cells, a key row each: every edge check but the ones about
    the grid sees a pair a line could be drawn between."""
    return tables_model([table("a", a_columns), table("b", b_columns)], grid, edges)


def key_name_model(name):
    """Three tables in one row — the narrowest schema card of both modes — and the key name goes to
    the first, so the row of that one key is the only thing a check can object to."""
    return tables_model([{"id": "t", "name": "T", "group": "g",
                          "columns": [{"name": name, "type": "uuid", "flags": ["PK"]}]},
                         table("u"), table("v")], ["t u v"])


class SchemaValidation(unittest.TestCase):
    def assertValid(self, model):
        for mode in MODES:
            for draft in (False, True):
                with self.subTest(mode=mode, draft=draft):
                    layout, warnings = schema.plan(copy.deepcopy(model), mode, draft=draft)
                    self.assertEqual(warnings, [])
                    self.assertNotIn("draft", layout)

    def assertRefused(self, model, errors, layout):
        """The closing mechanism: schema.plan raises on any error, model error and layout error
        alike, and `draft` changes nothing — the same refusal whichever way it is called. `errors`
        and `layout` map each mode to what it raises there; the exception lists the model errors
        first and the layout errors after them, marks the layout ones as `layout`, and marks none
        of them a fit error, because schema.plan builds no fit list."""
        for mode in MODES:
            for draft in (False, True):
                with self.subTest(mode=mode, draft=draft):
                    with self.assertRaises(ModelError) as ctx:
                        schema.plan(copy.deepcopy(model), mode, draft=draft)
                    self.assertEqual(ctx.exception.errors, errors[mode] + layout[mode])
                    self.assertEqual(ctx.exception.layout, layout[mode])
                    self.assertEqual(ctx.exception.fit, [])

    def assertInvalid(self, model, message=None, layout=(), **messages):
        """A model error. `message` is the one error both modes raise; a list of them, or
        `messages` mapping each mode to the whole list, where one model brings several or the
        modes differ. `layout` names the layout errors the same model also brings."""
        self.assertRefused(model, per_mode(message if message is not None else messages), per_mode(layout))

    def assertLayout(self, model, message=None, **messages):
        """A layout error, fatal in both modes and with draft on as with it off."""
        self.assertRefused(model, per_mode(()), per_mode(message if message is not None else messages))

    def assertWarning(self, model, message=None, **messages):
        """A warning leaves the plan laid out and is the same with draft on as with it off; the
        layout carries no draft flag, schema.plan sets none. `message` is the one warning both
        modes raise, `messages` maps each mode to the whole list it expects instead."""
        for mode in MODES:
            expected = [message] if message is not None else list(messages[mode])
            for draft in (False, True):
                with self.subTest(mode=mode, draft=draft):
                    layout, warnings = schema.plan(copy.deepcopy(model), mode, draft=draft)
                    self.assertNotIn("draft", layout)
                    self.assertEqual(warnings, expected)

    def assertFit(self, model, **messages):
        """A key row too long for its card. In flow.plan its counterpart is a fit error — fatal
        without draft, a draft warning with it; schema.plan raises no fit error and reports this
        one as an ordinary warning, so it is held as one, with the whole message of each mode: the
        length, the budget and the advice."""
        self.assertWarning(model, **messages)

    # -- the model and its groups --

    def test_model_without_tables(self):
        self.assertValid(model())
        empty = model()
        empty["tables"] = []
        empty["grid"] = ["."]
        self.assertInvalid(empty, "модель без таблиц")

    def test_too_many_groups_warns(self):
        valid = model()
        valid["groups"].update({f"g{i}": {"label": f"G{i}", "ramp": "teal"} for i in range(1, 4)})
        self.assertValid(valid)
        crowded = copy.deepcopy(valid)
        crowded["groups"]["g4"] = {"label": "G4", "ramp": "teal"}
        self.assertWarning(crowded, "групп 5: больше четырёх цветов читаются плохо")

    def test_group_id_charset(self):
        valid = model()
        self.assertValid(valid)
        for gid, message in (("G", "группа 'G': id только из строчных латинских букв, цифр и _"),
                             ("g?", "группа 'g?': id только из строчных латинских букв, цифр и _")):
            with self.subTest(gid=gid):
                invalid = copy.deepcopy(valid)
                invalid["groups"][gid] = {"label": "X", "ramp": "teal"}
                self.assertInvalid(invalid, message)

    def test_group_ramp(self):
        valid = model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["groups"]["g"]["ramp"] = "violet"
        self.assertInvalid(invalid, "группа g: ramp должен быть одним из "
                           "purple, teal, coral, pink, gray, blue, green, amber, red")

    # -- the grid map (parse_grid) --

    def test_grid_must_be_rows_of_text(self):
        # with no map at all every table is unplaced and the width is zero, so the shape error
        # comes with the placement error of the one table and the width layout error of the mode
        valid = model()
        self.assertValid(valid)
        for case, grid in (("absent", None), ("text", "t"), ("empty", []), ("mixed", ["t", 5])):
            with self.subTest(grid=case):
                invalid = copy.deepcopy(valid)
                invalid["grid"] = grid
                self.assertInvalid(
                    invalid,
                    ["grid: нужен список строк, по строке на ряд; токен это id узла, точка это пустая ячейка",
                     "таблица t описан, но не стоит в grid"],
                    layout={"widget": ["grid шириной 0: режим widget допускает от 1 до 3 столбцов"],
                            "page": ["grid шириной 0: режим page допускает от 1 до 4 столбцов"]})

    def test_grid_token_charset(self):
        valid = model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["grid"] = ["t X"]
        self.assertInvalid(invalid, "grid, ряд 0: токен 'X' не похож на id "
                                    "(строчные латинские буквы, цифры, _)")

    def test_grid_token_placed_twice(self):
        valid = model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["grid"] = ["t t"]
        self.assertInvalid(invalid, "grid: узел t стоит в двух ячейках [0, 0] и [0, 1]")

    def test_grid_width(self):
        self.assertValid(tables_model([table(tid) for tid in "abc"], ["a b c"]))
        self.assertLayout(
            tables_model([table(tid) for tid in "abcde"], ["a b c d e"]),
            widget=["grid шириной 5: режим widget допускает от 1 до 3 столбцов"],
            page=["grid шириной 5: режим page допускает от 1 до 4 столбцов"])

    # -- tables and their columns --

    def test_table_id_charset(self):
        # a table with an invalid id is skipped before placement, so it stays out of grid, where it
        # would otherwise be reported as placed but not described
        valid = model()
        self.assertValid(valid)
        for tid, message in (("U", "таблица 'U': id только из строчных латинских букв, цифр и _"),
                             ("u?", "таблица 'u?': id только из строчных латинских букв, цифр и _")):
            with self.subTest(tid=tid):
                invalid = copy.deepcopy(valid)
                invalid["tables"].append({"id": tid, "name": "U", "group": "g",
                                          "columns": [{"name": "k", "flags": ["PK"]}]})
                self.assertInvalid(invalid, message)

    def test_table_id_missing_or_empty(self):
        valid = model()
        self.assertValid(valid)
        for case, message in (("absent", "таблица None: id только из строчных латинских букв, цифр и _"),
                              ("empty", "таблица '': id только из строчных латинских букв, цифр и _")):
            with self.subTest(tid=case):
                invalid = copy.deepcopy(valid)
                added = {"name": "U", "group": "g", "columns": [{"name": "k", "flags": ["PK"]}]}
                if case == "empty":
                    added["id"] = ""
                invalid["tables"].append(added)
                self.assertInvalid(invalid, message)

    def test_duplicate_table_id(self):
        valid = model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["tables"].append({"id": "t", "name": "T2", "group": "g",
                                  "columns": [{"name": "k", "flags": ["PK"]}]})
        self.assertInvalid(invalid, "таблица t: id повторяется")

    def test_table_name_required(self):
        valid = tables_model([table("t"), table("u")], ["t u"])
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        del invalid["tables"][1]["name"]
        self.assertInvalid(invalid, "таблица u: нет name")

    def test_table_group_must_be_described(self):
        # unlike a node of flow.plan, a table without a group at all is refused too: schema.plan
        # colours every card by its group and reads the absent one as an undescribed one
        valid = tables_model([table("t"), table("u")], ["t u"])
        self.assertValid(valid)
        for case, message in (("unknown", "таблица u: группа 'missing' не описана в groups"),
                              ("absent", "таблица u: группа None не описана в groups")):
            with self.subTest(group=case):
                invalid = copy.deepcopy(valid)
                if case == "absent":
                    del invalid["tables"][1]["group"]
                else:
                    invalid["tables"][1]["group"] = "missing"
                self.assertInvalid(invalid, message)

    def test_column_name_required(self):
        valid = model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["tables"][0]["columns"].append({"type": "text"})
        self.assertInvalid(invalid, "таблица t: колонка без name")

    def test_duplicate_column_name(self):
        valid = model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["tables"][0]["columns"].append({"name": "id", "type": "text"})
        self.assertInvalid(invalid, "таблица t: колонка id повторяется")

    def test_column_flags(self):
        valid = model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["tables"][0]["columns"][0]["flags"] = ["PK", "X"]
        self.assertInvalid(invalid, "таблица t.id: неизвестные flags ['X']; "
                                    "допустимы ['PK', 'FK', 'U', 'N']")

    def test_column_key_icon(self):
        valid = model()
        valid["tables"][0]["columns"][0]["key"] = "key"
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["tables"][0]["columns"][0]["key"] = "unicorn"
        self.assertInvalid(invalid, "таблица t.id: key 'unicorn' не из connection, user, profile, "
                                    "attempt, id, check, external, kind, tenant, key, link, dot")

    def test_key_row_must_fit(self):
        self.assertValid(key_name_model("id"))
        self.assertFit(key_name_model("external_correlation_identifier_value"),
                       widget=["таблица t.external_correlation_identifier_value: имя 37 симв., "
                               "влезает ~20; сузьте grid или сократите имя"],
                       page=["таблица t.external_correlation_identifier_value: имя 37 симв., "
                             "влезает ~33; сузьте grid или сократите имя"])

    def test_table_without_key_column_warns(self):
        valid = model()
        self.assertValid(valid)
        flat = copy.deepcopy(valid)
        flat["tables"][0]["columns"] = [{"name": "note", "type": "text", "flags": ["N"]}]
        self.assertWarning(flat, "таблица t: нет ни одной ключевой колонки, линии крепить не к чему")

    # -- where the tables stand --

    def test_table_must_be_placed(self):
        valid = model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["tables"].append(table("u"))
        self.assertInvalid(invalid, "таблица u описан, но не стоит в grid")

    def test_placed_table_must_be_described(self):
        valid = model()
        self.assertValid(valid)
        invalid = copy.deepcopy(valid)
        invalid["grid"] = ["t u"]
        self.assertInvalid(invalid, "grid: u стоит в карте, но не описан")

    def test_empty_row_warns(self):
        self.assertValid(tables_model([table("t"), table("u")], ["t", "u"]))
        self.assertWarning(tables_model([table("t"), table("u")], ["t", ".", "u"]),
                           "пустые ряды в grid: [1]")

    def test_empty_column_warns(self):
        self.assertValid(tables_model([table("t"), table("u")], ["t u"]))
        self.assertWarning(tables_model([table("t"), table("u")], ["t . u"]),
                           "пустые столбцы в grid: [1]")

    def test_row_balance_warns(self):
        # the estimate counts the key rows of a card in both modes, so one tall card among short
        # ones reads the same in widget and in page
        self.assertValid(tables_model([table("t", ("k0", "k1")), table("u")], ["t u"]))
        self.assertWarning(
            tables_model([table("t", tuple(f"k{i}" for i in range(11))), table("u")], ["t u"]),
            "ряд 0: карточка t примерно в 3.5 раза выше u, под короткой останется пустота; "
            "переставьте таблицы или сверните ряд")

    # -- edges: the shorthand and the object form (parse_edge) --

    def test_edge_shorthand_needs_an_arrow(self):
        self.assertValid(edge_model(["a.k -> b.m"]))
        self.assertInvalid(edge_model(["a.k b.m"]), "связь #1: ожидается 'a.col -> b.col'")

    def test_edge_modifier(self):
        self.assertValid(edge_model(["a.k -> b.m | logical"]))
        self.assertInvalid(edge_model(["a.k -> b.m | weird"]),
                           "связь #1: неизвестный модификатор 'weird'; "
                           "допустимы fk, logical, right, left, ends=a/b")

    def test_edge_object_form(self):
        self.assertValid(edge_model([{"from": ["a", "k"], "to": ["b", "m"]}]))
        message = "связь #1: from и to должны быть [table_id, column] или [table_id]"
        for case, edge in (("no to", {"from": ["a", "k"]}), ("not a mapping", 5),
                           ("no table id", {"from": [], "to": []})):
            with self.subTest(edge=case):
                self.assertInvalid(edge_model([edge]), message)

    # -- edges: the tables and columns they name --

    def test_edge_table_must_be_described(self):
        self.assertInvalid(edge_model(["a.k -> c.m"]), "связь a.k -> c.m: неизвестная таблица")

    def test_edge_to_itself(self):
        self.assertInvalid(edge_model(["a.k -> a.k"]),
                           "связь a.k -> a.k: связь таблицы с собой не рисуется")

    def test_edge_kind(self):
        self.assertInvalid(edge_model([{"from": ["a", "k"], "to": ["b", "m"], "kind": "weak"}]),
                           "связь a.k -> b.m: kind должен быть fk или logical")

    def test_edge_ends(self):
        self.assertValid(edge_model([{"from": ["a", "k"], "to": ["b", "m"], "from_end": "plain"}]))
        self.assertInvalid(edge_model([{"from": ["a", "k"], "to": ["b", "m"], "from_end": "both"}]),
                           "связь a.k -> b.m: from_end и to_end из ('plain', 'one', 'many')")

    def test_edge_route_value(self):
        self.assertInvalid(edge_model([{"from": ["a", "k"], "to": ["b", "m"], "route": "up"}]),
                           "связь a.k -> b.m: route из auto, right, left")

    def test_edge_needs_a_column(self):
        self.assertLayout(edge_model(["a -> b.m"]),
                          "связь a.* -> b.m: линия крепится к колонкам, укажите колонку у a")

    def test_edge_column_must_exist(self):
        self.assertInvalid(edge_model(["a.nope -> b.m"]), "связь a.nope -> b.m: у a нет колонки nope")

    def test_edge_column_must_be_a_key_row(self):
        invalid = edge_model(["a.note -> b.m"])
        invalid["tables"][0]["columns"].append({"name": "note", "type": "text"})
        self.assertInvalid(invalid, "связь a.note -> b.m: a.note не ключевая строка "
                                    "(PK/FK/U или key), в свёрнутой карточке её не видно")

    # -- edges: where the line can run --

    def test_stacked_key_rows_taken_on_both_sides(self):
        # stacked cards leave a key row sideways, one line per side; the third has nowhere to go
        stacked = tables_model([table("a"), table("b", ("m",))], ["a", "b"],
                               ["a.k -> b.m", "a.k -> b.m", "a.k -> b.m"])
        self.assertLayout(stacked, "связь a.k -> b.m: строки k и m заняты с обеих сторон другими "
                                   "связями; переставьте таблицы или свяжите через другую колонку")

    def test_edge_cells_must_be_adjacent(self):
        self.assertLayout(edge_model(["a.k -> b.m"], grid=["a . b"]),
                          "связь a.k -> b.m: ячейки [0, 0] и [0, 2] не соседние; "
                          "переставьте таблицы или задайте route: right|left по внешнему краю")

    def test_edge_route_needs_the_edge_column(self):
        for route, column in (("right", 1), ("left", 0)):
            with self.subTest(route=route):
                self.assertLayout(edge_model([f"a.k -> b.m | {route}"]),
                                  f"связь a.k -> b.m: route {route} требует обе таблицы в столбце {column}")

    def test_anchor_point_taken(self):
        # both lines leave a.k along the right margin, and the second finds its anchor occupied
        stacked = tables_model([table("a"), table("b"), table("c")], ["a", "b", "c"],
                               ["a.k -> b.k | right", "a.k -> c.k | right"])
        self.assertLayout(stacked, "связь a.k -> c.k: точка крепления a.k (R) "
                                   "уже занята связью связь a.k -> b.k")

    def test_crossing_lines_warn(self):
        columns = ("k0", "k1", "k2")
        self.assertValid(edge_model(["a.k0 -> b.k0"], a_columns=columns, b_columns=columns))
        self.assertWarning(edge_model(["a.k1 -> b.k1", "a.k0 -> b.k2"],
                                      a_columns=columns, b_columns=columns),
                           "связь a.k1 -> b.k1 пересечёт связь a.k0 -> b.k2; "
                           "переставьте таблицы или свяжите через другую колонку")

    # -- the refusal itself --

    def test_model_and_layout_errors_are_raised_together(self):
        # the exception lists the model errors first and the layout errors after them, and only the
        # layout ones are marked `layout`; with draft on schema.plan raises the very same thing
        both = tables_model([table(tid) for tid in "abcde"], ["a b c d e"])
        both["tables"][4]["group"] = "missing"
        self.assertInvalid(
            both, "таблица e: группа 'missing' не описана в groups",
            layout={"widget": ["grid шириной 5: режим widget допускает от 1 до 3 столбцов"],
                    "page": ["grid шириной 5: режим page допускает от 1 до 4 столбцов"]})


if __name__ == "__main__":
    unittest.main()
