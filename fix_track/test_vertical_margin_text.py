"""Native integration regressions for conservative vertical margin filtering.

Requires PyMuPDF and Pillow. Run with K2PDFOPT_BINARY pointing to a freshly
built executable and its runtime libraries on PATH.
"""

import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import fitz
from PIL import Image, ImageChops


class VerticalMarginTextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.binary = os.environ.get("K2PDFOPT_BINARY")
        if not self.binary:
            self.skipTest("Set K2PDFOPT_BINARY to run native integration tests")

    def make_source(self, sidebar=False, interior=False, image=False, scan=False, right=False):
        document = fitz.open()
        page = document.new_page(width=612, height=792)
        for line_number in range(18):
            page.insert_text(
                (100, 220 + line_number * 20),
                f"BODY line {line_number:02d}: preserve horizontal paper content.",
                fontsize=12,
            )
        if image:
            buffer = io.BytesIO()
            Image.new("RGB", (40, 440), "white").save(buffer, format="PNG")
            page.insert_image(fitz.Rect(5, 200, 45, 700), stream=buffer.getvalue())
        if sidebar or interior:
            page.insert_text(
                (200 if interior else 600 if right else 25, 650),
                "SIDEBAR metadata long vertical identifier 123456789",
                fontsize=14,
                rotate=90,
            )
        if scan:
            pixels = page.get_pixmap()
            document.close()
            document = fitz.open()
            page = document.new_page(width=612, height=792)
            page.insert_image(page.rect, pixmap=pixels)
        source = self.directory / "source.pdf"
        document.save(source)
        document.close()
        return source

    def render(self, source, enabled, color=False, rotation=0, native=False):
        output = self.directory / f"output-{enabled}-{color}.pdf"
        command = [
            self.binary, str(source), "-mode", "copy", "-n-", "-t-", "-m", "0",
            "-w", "792p" if rotation else "612p",
            "-h", "612p" if rotation else "792p", "-odpi", "72", "-idpi", "144",
            "-rt", str(rotation), "-ui-", "-y", "-x", "-ow", "-o", str(output),
            "-vmt" if enabled else "-vmt-", "-c" if color else "-c-",
        ]
        if native:
            command.append("-n")
        result = subprocess.run(command, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        with fitz.open(output) as document:
            self.assertEqual(len(document), 1)
            pixels = document[0].get_pixmap(alpha=False)
            return Image.frombytes("RGB", (pixels.width, pixels.height), pixels.samples)

    def assert_unchanged(self, **source_options):
        source = self.make_source(**source_options)
        before = self.render(source, False)
        after = self.render(source, True)
        self.assertEqual(before.size, after.size)
        self.assertIsNone(ImageChops.difference(before, after).getbbox())

    def test_sidebar_removed_without_changing_body_pixels(self):
        source = self.make_source(sidebar=True)
        for color in (False, True):
            with self.subTest(color=color):
                before = self.render(source, False, color)
                after = self.render(source, True, color)
                difference = ImageChops.difference(before, after).getbbox()
                self.assertIsNotNone(difference)
                self.assertLess(difference[2], 60)
                self.assertEqual(after.crop((0, 0, 60, 792)).getextrema(),
                                 ((255, 255),) * 3)
                self.assertEqual(before.crop((60, 0, 612, 792)).tobytes(),
                                 after.crop((60, 0, 612, 792)).tobytes())

    def test_right_sidebar_removed_without_changing_body_pixels(self):
        source = self.make_source(sidebar=True, right=True)
        before, after = self.render(source, False), self.render(source, True)
        difference = ImageChops.difference(before, after).getbbox()
        self.assertIsNotNone(difference)
        self.assertGreater(difference[0], 552)
        self.assertEqual(after.crop((552, 0, 612, 792)).getextrema(), ((255, 255),) * 3)
        self.assertEqual(before.crop((0, 0, 552, 792)).tobytes(),
                         after.crop((0, 0, 552, 792)).tobytes())

    def test_no_sidebar_is_pixel_identical(self):
        self.assert_unchanged()

    def test_interior_vertical_axis_label_is_pixel_identical(self):
        self.assert_unchanged(interior=True)

    def test_image_overlapping_margin_label_is_preserved(self):
        self.assert_unchanged(sidebar=True, image=True)

    def test_scanned_page_is_pixel_identical(self):
        self.assert_unchanged(sidebar=True, scan=True)

    def test_rotated_and_native_output_are_pixel_identical(self):
        source = self.make_source(sidebar=True)
        for options in ({"rotation": 90}, {"native": True}):
            with self.subTest(options=options):
                before = self.render(source, False, **options)
                after = self.render(source, True, **options)
                self.assertEqual(before.size, after.size)
                self.assertIsNone(ImageChops.difference(before, after).getbbox())


if __name__ == "__main__":
    unittest.main()