"""Focused arithmetic checks for missing browser tracks; browser layout is tested separately."""
import json
import shutil
import subprocess
import unittest

import support


NODE = shutil.which("node")


@unittest.skipUnless(NODE, "node is not installed")
class MissingColumnTracks(unittest.TestCase):
    def tracks(self, widths, cards):
        # Execute the production function with resolved CSS values and measured card rectangles.
        source = (support.SKILL / "template" / "js" / "head.js").read_text()
        function = source[source.index(" function tracks(){"):]
        harness = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const sec = {};
const grid = {
  getBoundingClientRect: () => ({left: 101, top: 203}),
  querySelectorAll: () => input.cards.map(c => ({
    getAttribute: name => name === 'data-c' ? c.col : c.row,
    getBoundingClientRect: () => ({left: c.l + 101, right: c.r + 101,
                                  top: c.t + 203, bottom: c.b + 203})
  }))
};
function getComputedStyle(element) {
  return element === grid ? {
    gridTemplateColumns: input.widths.map(w => w + 'px').join(' '),
    columnGap: '31.5px', paddingLeft: '38.25px'
  } : {getPropertyValue: name => ({'--dg-cols': input.widths.length,
                                 '--dg-gap': '31.5px'})[name]};
}
"""
        result = subprocess.run([NODE, "-e", harness + function + "\nconsole.log(JSON.stringify(tracks()));"],
                                input=json.dumps({"widths": widths, "cards": cards}),
                                text=True, capture_output=True, check=True)
        return json.loads(result.stdout)

    def test_missing_tracks_use_resolved_grid_widths_and_origin(self):
        # Several leading holes plus an internal and trailing hole. Unequal resolved widths also
        # guard the shared schema renderer against assuming every track has the first width.
        result = self.tracks([173.5, 210, 180, 192.25, 205, 160], [
            {"col": 2, "row": 0, "l": 484.75, "r": 664.75, "t": 8, "b": 48},
            {"col": 4, "row": 0, "l": 920, "r": 1125, "t": 8, "b": 48},
        ])
        self.assertEqual(result["cols"], {
            "0": {"l": 38.25, "r": 211.75},
            "1": {"l": 243.25, "r": 453.25},
            "2": {"l": 484.75, "r": 664.75},
            "3": {"l": 696.25, "r": 888.5},
            "4": {"l": 920, "r": 1125},
            "5": {"l": 1156.5, "r": 1316.5},
        })
        self.assertEqual(result["C"], 6)

    def test_measured_bounds_and_empty_rows_are_preserved(self):
        result = self.tracks([173.5] * 3, [
            {"col": 1, "row": 1, "l": 244, "r": 416, "t": 8, "b": 48},
            {"col": 1, "row": 3, "l": 243.75, "r": 417.25, "t": 140, "b": 185},
        ])
        self.assertEqual(result["cols"]["1"], {"l": 243.75, "r": 417.25})
        self.assertEqual(result["rows"], {
            "0": {"t": -12, "b": -12}, "1": {"t": 8, "b": 48},
            "2": {"t": 94, "b": 94}, "3": {"t": 140, "b": 185},
        })
        self.assertEqual(result["R"], 4)


if __name__ == "__main__":
    unittest.main()
