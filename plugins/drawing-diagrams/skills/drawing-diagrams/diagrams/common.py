"""Shared vocabulary for every diagram kind: colours, icons, labels, helpers."""
import html
import re

# Colour ramps, stops: 50, 100, 200, 400, 600, 800, 900.
RAMPS = {
    "purple": ("#EEEDFE", "#CECBF6", "#AFA9EC", "#7F77DD", "#534AB7", "#3C3489", "#26215C"),
    "teal": ("#E1F5EE", "#9FE1CB", "#5DCAA5", "#1D9E75", "#0F6E56", "#085041", "#04342C"),
    "coral": ("#FAECE7", "#F5C4B3", "#F0997B", "#D85A30", "#993C1D", "#712B13", "#4A1B0C"),
    "pink": ("#FBEAF0", "#F4C0D1", "#ED93B1", "#D4537E", "#993556", "#72243E", "#4B1528"),
    "gray": ("#F1EFE8", "#D3D1C7", "#B4B2A9", "#888780", "#5F5E5A", "#444441", "#2C2C2A"),
    "blue": ("#E6F1FB", "#B5D4F4", "#85B7EB", "#378ADD", "#185FA5", "#0C447C", "#042C53"),
    "green": ("#EAF3DE", "#C0DD97", "#97C459", "#639922", "#3B6D11", "#27500A", "#173404"),
    "amber": ("#FAEEDA", "#FAC775", "#EF9F27", "#BA7517", "#854F0B", "#633806", "#412402"),
    "red": ("#FCEBEB", "#F7C1C1", "#F09595", "#E24B4A", "#A32D2D", "#791F1F", "#501313"),
}

# Inline 24x24 stroke glyphs (no icon font dependency).
ICONS = {
    "connection": '<path d="M9 3v5M15 3v5M5 8h14l-1 5a6 6 0 0 1-12 0z"/><path d="M12 19v3"/>',
    "user": '<path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "profile": '<path d="M3 5h18v14H3z"/><path d="M7 9h3v3H7z"/><path d="M13 9h5M13 13h5"/>',
    "attempt": '<path d="M4 12V9a3 3 0 0 1 3-3h13"/><path d="M17 3l3 3-3 3"/><path d="M20 12v3a3 3 0 0 1-3 3H4"/><path d="M7 15l-3 3 3 3"/>',
    "id": '<path d="M5 9h14M5 15h14M11 4l-2 16M17 4l-2 16"/>',
    "check": '<path d="M4 6l2 2 4-4M4 14l2 2 4-4M13 6h7M13 14h7"/>',
    "external": '<path d="M11 7H6a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-5"/><path d="M10 14L20 4M15 4h5v5"/>',
    "kind": '<path d="M4 4h7l9 9-7 7-9-9z"/><path d="M8.5 8.5h.01"/>',
    "tenant": '<path d="M3 21h18M5 21V7l7-4 7 4v14M9 21v-4h6v4M9 10h.01M15 10h.01M9 14h.01M15 14h.01"/>',
    "key": '<circle cx="8" cy="15" r="4"/><path d="M10.85 12.15L19 4M18 5l2 2M15 8l2 2"/>',
    "link": '<path d="M10 14a3.5 3.5 0 0 0 5 0l4-4a3.5 3.5 0 0 0-5-5l-.5.5"/><path d="M14 10a3.5 3.5 0 0 0-5 0l-4 4a3.5 3.5 0 0 0 5 5l.5-.5"/>',
    "dot": '<circle cx="12" cy="12" r="3"/>',
}
CHEVRON = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
           'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>')

# Total widths and paddings shared by every kind; card widths and gaps are per kind.
# Paddings hold the margin routes (14 px outside the outer cards) inside the grid box,
# otherwise the section's own overflow clips a line that runs along the margin.
BASE_MODES = {
    "widget": {"total": 680, "pad_l": 18, "pad_r": 18},
    "page": {"total": 1100, "pad_l": 24, "pad_r": 24},
}

DEFAULT_LABELS = {
    "more": "ещё {n} {cols}",
    "cols": ["колонка", "колонки", "колонок"],
    "collapse": "свернуть",
    "open_all": "раскрыть все",
    "close_all": "свернуть все",
    "fk": "FK в базе",
    "logical": "связь по ключу, без FK",
    "one": "один",
    "many": "много",
    "draft": "черновик, проверка не пройдена",
    "flow_solid": "переход",
    "flow_dashed": "асинхронно или необязательно",
    "decision": "развилка",
    "routes": "сценарии:",
    "chip": "сущность",
    "changed": "состояние изменилось в этот момент",
}

ID_RE = re.compile(r"^[a-z][a-z0-9_]*\??$")


class ModelError(Exception):
    """Validation failed. `errors` is the list of messages; `layout` marks the ones --draft may
    downgrade to warnings; `fit` marks the layout errors about a text too long for its place."""

    def __init__(self, errors, layout=(), fit=()):
        super().__init__("\n".join("ошибка: " + e for e in errors))
        self.errors = list(errors)
        self.layout = list(layout)
        self.fit = list(fit)


def plural(n, forms):
    forms = list(forms) + [forms[-1]] * (3 - len(forms))
    n1, n2 = n % 10, n % 100
    if n1 == 1 and n2 != 11:
        return forms[0]
    if 2 <= n1 <= 4 and not 12 <= n2 <= 14:
        return forms[1]
    return forms[2]


def esc(s):
    return html.escape(str(s), quote=True)


def icon_svg(name):
    return ('<svg class="dg-i" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            + ICONS[name] + "</svg>")


def labels_for(model):
    labels = dict(DEFAULT_LABELS)
    labels.update(model.get("labels") or {})
    return labels


# Text width estimate for the system sans stack, calibrated in a browser at
# 12.5px weight 500 (titles). `scale` 0.88 fits 11.5px weight 400 body text.
def text_width(text, scale=1.0):
    w = 0.0
    for ch in text:
        if "\u0400" <= ch <= "\u04ff":
            w += 8.6 if ch.isupper() else 7.4
        elif ch.isascii() and ch.isalpha():
            w += 8.3 if ch.isupper() else 6.8
        elif ch.isdigit():
            w += 7.0
        elif ch == " ":
            w += 3.6
        elif ch in ",.:;!'|":
            w += 3.8
        else:
            w += 7.0
    return w * scale


# Advance widths of edge labels (`.dg-svg text`: 11px, weight 400), measured glyph by glyph
# in a browser with the sans stack above (macOS system-ui). The label check works in
# pixels, so text_width's classes are too coarse here: they miss digits by 13 % and a
# circled footnote number by 4 px.
_LABEL_MEASURED = (
    "a6.14 b6.83 c6.23 d6.83 e6.35 f4.05 g6.77 h6.54 i2.79 j2.78 k6.04 l2.85 m9.64 n6.48 o6.57 p6.78 q6.77 "
    "r4.26 s5.83 t4.06 u6.48 v6.03 w8.59 x5.84 y6.04 z6 "
    "A7.48 B7.3 C7.95 D8.06 E6.62 F6.36 G8.28 H8.23 I3.01 J5.98 K7.31 L6.31 M9.68 N8.23 O8.55 P7.05 Q8.55 "
    "R7.26 S7.08 T7.04 U8.18 V7.48 W10.71 X7.53 Y7.27 Z7.34 "
    "07 15.17 26.7 36.96 47.15 56.87 67.07 76.33 87.09 97.07 "
    "а6.24 б6.73 в6.09 г5.18 д6.81 е6.46 ё6.46 ж8.7 з5.87 и6.73 й6.73 к6.05 л6.43 м8.34 н6.64 о6.67 п6.59 "
    "р6.89 с6.33 т5.61 у6.15 ф8.2 х5.95 ц6.89 ч6.32 ш9.06 щ9.37 ъ6.79 ы8.09 ь5.75 э6.33 ю8.82 я5.91 "
    "А7.59 Б7.05 В7.41 Г6.3 Д8.23 Е6.73 Ё6.73 Ж11.29 З6.81 И8.34 Й8.34 К7.42 Л7.83 М9.79 Н8.34 О8.66 П8.23 "
    "Р7.16 С8.05 Т7.15 У7.15 Ф9.2 Х7.64 Ц8.55 Ч7.7 Ш10.66 Щ10.97 Ъ8.52 Ы9.91 Ь7.11 Э8.16 Ю11.23 Я7.46 "
    r''',3.34 .3.34 :3.34 ;3.34 !3.49 '3.34 |2.91 "5.32 (4.27 )4.27 [4.27 ]4.27 {4.27 }4.27 /3.42 \3.42 '''
    "_6.48 +7 =7 <7 >7 ?5.71 –6.48 —9.68 -5.26 ·3.34 …8.92 «7.34 »7.34 #7 %10.25 &7.89 *5.26 @10.16 ~7 ^7 "
    "`5.57 $7"
)
LABEL_ADVANCE = {tok[0]: float(tok[1:]) for tok in _LABEL_MEASURED.split()}
LABEL_ADVANCE[" "] = 3.15
CIRCLED_WIDTH = 10.25  # ① … ⑳ come from a fallback font, much wider than a digit


def label_width(text):
    """Width in px of an edge label as template/js/flow.js draws it. A glyph that was not measured
    counts as a circled number: wide rather than optimistic."""
    return sum(LABEL_ADVANCE.get(ch, CIRCLED_WIDTH) for ch in text)


def wrap_lines(text, width, scale=0.88):
    """Lines a greedy word wrap needs for `text` in `width` px."""
    lines, cur = 1, 0.0
    space = text_width(" ", scale)
    for word in text.split():
        w = text_width(word, scale) * 1.05  # browsers measure long words a little wider
        if cur == 0:
            cur = w
        elif cur + space + w <= width:
            cur += space + w
        else:
            lines += 1
            cur = w
    return lines


def fit_chars(n, need, room):
    """Characters of an n-character text that fit `room` px when all n need `need` px."""
    if need <= 0:
        return n
    return max(int(n * room / need), 1)


def two_line_chars(text, width, scale=0.88):
    """About how many characters of `text` fit two word-wrapped lines of `width` px. Wrapping leaves
    the ends of lines short, so a tenth of the room is kept in reserve."""
    return fit_chars(len(text), text_width(text, scale) * 1.05, 2 * width * 0.9)
