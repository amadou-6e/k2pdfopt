"""Native ruled-table regressions; requires PyMuPDF.

Set K2PDFOPT_BINARY to the new executable. K2PDFOPT_BASELINE_BINARY enables
pixel-exact negative controls. Optional K2PDFOPT_REFLEXION_SOURCE and
K2PDFOPT_REFLEXION_OUTPUT check Tables 1-3 in a full paper conversion.
Run: python -m unittest discover -s fix_track -p test_table_geometry.py -v
"""

import os
import statistics
import subprocess
import tempfile
import unittest
from pathlib import Path

import fitz


def ordered_words(words):
    lines = []
    for word in sorted(words, key=lambda item: (item[1], item[0])):
        if not lines or abs(word[1] - lines[-1][0][1]) > 3:
            lines.append([word])
        else:
            lines[-1].append(word)
    return [word for line in lines for word in sorted(line, key=lambda item: item[0])]


class TableGeometryTests(unittest.TestCase):
    def setUp(self):
        self.binary = os.environ.get("K2PDFOPT_BINARY")
        if not self.binary:
            self.skipTest("Set K2PDFOPT_BINARY to run native integration tests")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def make_source(self, rules=True, missing_rule=False, misaligned=False, varied=False,
                    outside=False, second=False, extra_rule=False):
        document = fitz.open()
        page = document.new_page(width=612, height=792)
        page.insert_text((100, 100), "Ordinary prose before the table stays in reading order.")
        for offset in ([0, 300] if second else [0]):
            if rules:
                for index, height in enumerate([150, 174, 246]):
                    if missing_rule and index == 1:
                        continue
                    left = 200 if misaligned and index == 1 else 100
                    right = 496 if varied and index == 0 else 500
                    page.draw_line((left, height + offset), (right, height + offset), width=0.8)
                if extra_rule:
                    page.draw_line((100, 210 + offset), (500, 210 + offset), width=0.8)
            for position, text in [(108, "Benchmark"), (300, "Base"), (410, "Reflexion")]:
                page.insert_text((position, 165 + offset), text, fontsize=11, fontname="hebo")
            for index in range(4):
                height = 190 + index * 16 + offset
                label = f"Row{chr(65 + index + offset // 300 * 4)}"
                for position, text in [(108, label), (300, f"0.{index + 1}1"),
                                       (410, f"0.{index + 9}1")]:
                    page.insert_text((position, height), text, fontsize=11)
            if outside:
                page.insert_text((55, 206 + offset), "OUTSIDE", fontsize=9)
            page.insert_text((80, 259 + offset),
                             "Table 1: complete caption stays below all numeric cells.", fontsize=10)
        for index in range(7):
            page.insert_text((100, 660 + index * 15),
                             f"Following ordinary prose line {index} remains unchanged.")
        page = document.new_page(width=612, height=792)
        for index in range(35):
            page.insert_text((100, 100 + index * 16),
                             f"Trailing guard paragraph line {index} for native output flushing.")
        source = self.directory / "source.pdf"
        document.save(source)
        document.close()
        return source

    def convert(self, source, baseline=False, color=False):
        binary = os.environ.get("K2PDFOPT_BASELINE_BINARY") if baseline else self.binary
        if not binary:
            self.skipTest("Set K2PDFOPT_BASELINE_BINARY for pixel-exact negative controls")
        output = self.directory / f"output-{baseline}-{color}.pdf"
        command = [binary, str(source), "-fc-", "-x", "-ui-", "-y", "-ow",
                   "-stretch", "-stretchr", "1.35", "-stretchmax", "1.35",
                   "-c" if color else "-c-", "-o", str(output)]
        result = subprocess.run(command, capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        return output

    def assert_atomic_region(self, source, bounds, output):
        expected = ordered_words([word for word in source.get_text("words")
                                  if bounds.contains(fitz.Point((word[0] + word[2]) / 2,
                                                               (word[1] + word[3]) / 2))])
        expected_text = [word[4] for word in expected]
        self.assertGreater(len(expected), 8)
        for page in output:
            words = ordered_words(page.get_text("words"))
            for start in range(len(words) - len(expected) + 1):
                actual = words[start:start + len(expected)]
                if [word[4] for word in actual] != expected_text:
                    continue
                source_mean = statistics.mean(word[0] for word in expected)
                output_mean = statistics.mean(word[0] for word in actual)
                scale = sum((before[0] - source_mean) * (after[0] - output_mean)
                            for before, after in zip(expected, actual)) / sum(
                                (word[0] - source_mean) ** 2 for word in expected)
                horizontal = statistics.median(after[0] - scale * before[0]
                                               for before, after in zip(expected, actual))
                vertical = statistics.median(after[1] - scale * before[1]
                                             for before, after in zip(expected, actual))
                for before, after in zip(expected, actual):
                    self.assertAlmostEqual(after[0], scale * before[0] + horizontal, delta=1.0)
                    self.assertAlmostEqual(after[1], scale * before[1] + vertical, delta=1.0)
                captions = page.search_for("Table")
                last_cell = max(word[3] for word in actual)
                self.assertTrue(any(caption.y0 >= last_cell - 1 for caption in captions),
                                "Caption must follow, not interleave with, the table")
                return
        self.fail(f"Complete table cells not found in source reading order: {expected_text}")

    def check_table(self, color=False, varied=False, second=False):
        source = self.make_source(varied=varied, second=second)
        output = self.convert(source, color=color)
        with fitz.open(source) as original, fitz.open(output) as converted:
            for offset in ([0, 300] if second else [0]):
                self.assert_atomic_region(original[0], fitz.Rect(99, 149 + offset, 501, 247 + offset),
                                          converted)
            text = "".join("".join(page.get_text().split()) for page in converted)
            caption = "Table1:completecaptionstaysbelowallnumericcells."
            self.assertEqual(text.count(caption), 2 if second else 1)

    def test_ruled_table_geometry_and_caption(self):
        self.check_table()

    def test_color_table_geometry(self):
        self.check_table(color=True)

    def test_small_rule_length_variation(self):
        self.check_table(varied=True)

    def test_two_tables_on_one_page(self):
        self.check_table(second=True)

    def check_unchanged(self, **options):
        source = self.make_source(**options)
        baseline = self.convert(source, baseline=True)
        output = self.convert(source)
        with fitz.open(baseline) as before, fitz.open(output) as after:
            self.assertEqual(len(before), len(after))
            for before_page, after_page in zip(before, after):
                self.assertEqual(before_page.get_text(), after_page.get_text())
                self.assertEqual(before_page.get_pixmap().samples, after_page.get_pixmap().samples)

    def test_borderless_table_unchanged(self):
        self.check_unchanged(rules=False)

    def test_missing_header_rule_unchanged(self):
        self.check_unchanged(missing_rule=True)

    def test_misaligned_rules_unchanged(self):
        self.check_unchanged(misaligned=True)

    def test_outlying_cells_not_cropped(self):
        self.check_unchanged(outside=True)

    def test_complex_grid_not_partially_grouped(self):
        self.check_unchanged(extra_rule=True)

    def test_reflexion_tables(self):
        source = os.environ.get("K2PDFOPT_REFLEXION_SOURCE")
        output = os.environ.get("K2PDFOPT_REFLEXION_OUTPUT")
        if not source or not output:
            self.skipTest("Set K2PDFOPT_REFLEXION_SOURCE and K2PDFOPT_REFLEXION_OUTPUT")
        with fitz.open(source) as original, fitz.open(output) as converted:
            for page_number in [7, 8]:
                page = original[page_number - 1]
                rules = sorted([drawing["rect"] for drawing in page.get_drawings()
                                if drawing["rect"].width > 100 and drawing["rect"].height < 1],
                               key=lambda bounds: bounds.y0)
                for start in range(0, len(rules), 3):
                    group = rules[start:start + 3]
                    self.assertEqual(len(group), 3)
                    bounds = fitz.Rect(min(rule.x0 for rule in group), group[0].y0 - 1,
                                       max(rule.x1 for rule in group), group[-1].y1 + 1)
                    self.assert_atomic_region(page, bounds, converted)
            text = "".join("".join(page.get_text().split()) for page in converted)
            caption_count = 0
            for page_number in [7, 8]:
                lines = sorted([line for block in original[page_number - 1].get_text("dict")["blocks"]
                                if "lines" in block for line in block["lines"]],
                               key=lambda line: line["bbox"][1])
                for start, line in enumerate(lines):
                    caption = "".join(span["text"] for span in line["spans"])
                    if not caption.startswith(("Table 1:", "Table 2:", "Table 3:")):
                        continue
                    previous_top = line["bbox"][1]
                    for following in lines[start + 1:]:
                        if following["bbox"][1] - previous_top > 15:
                            break
                        caption += "".join(span["text"] for span in following["spans"])
                        previous_top = following["bbox"][1]
                    self.assertIn("".join(caption.split()), text)
                    caption_count += 1
            self.assertEqual(caption_count, 3)


if __name__ == "__main__":
    unittest.main()