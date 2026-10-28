"""Check spacing and premature wrapping of paragraph lead-ins in a reflowed PDF.

Requires PyMuPDF. Example:
python fix_track/check_leadin_spacing.py output.pdf --expected-lines 6
Use --reference before.pdf to verify ordered text retention against an earlier
conversion, not against the unreflowed source PDF.
"""

import argparse
import json
import re
from statistics import median

import fitz


def check_spacing(document, leadins, max_gap_heights=2.0):
    checked = []
    errors = []
    for page_number, page in enumerate(document, start=1):
        rows = []
        page_words = page.get_text("words")
        if not page_words:
            continue
        right_edge = min(page.rect.x1, max(word[2] for word in page_words))
        for word in sorted(page_words, key=lambda word: (word[1], word[0])):
            if not rows or abs(rows[-1][0][1] - word[1]) > 1.5:
                rows.append([word])
            else:
                rows[-1].append(word)
        for row_number, row in enumerate(rows):
            words = sorted(row, key=lambda word: word[0])
            label = words[0][4].rstrip(":.")
            if label not in leadins:
                continue
            if len(words) < 2:
                errors.append(f"Page {page_number}: {label} is isolated from its paragraph")
                continue
            gaps = []
            for previous, following in zip(words, words[1:]):
                height = max(previous[3] - previous[1], following[3] - following[1])
                gap = following[0] - previous[2]
                gaps.append(round(gap, 3))
                if gap > height * max_gap_heights:
                    errors.append(
                        f"Page {page_number}: {label} line has {gap:.2f}pt gap "
                        f"between {previous[4]!r} and {following[4]!r} "
                        f"(limit {height * max_gap_heights:.2f}pt)"
                    )
            line_result = {"page": page_number, "lead_in": label, "gaps_pt": gaps}
            if row_number + 1 < len(rows) and not words[-1][4].endswith((".", "!", "?", ":", ";")):
                following_row = sorted(rows[row_number + 1], key=lambda word: word[0])
                next_word = following_row[0]
                height = max(word[3] - word[1] for word in words)
                if (abs(next_word[0] - words[0][0]) < height * 1.5
                        and 0 < next_word[1] - words[0][1] < height * 2.5):
                    normal_gaps = [gap for gap in gaps if 0 < gap < height]
                    space = median(normal_gaps) if normal_gaps else height * 0.3
                    needed = next_word[2] - next_word[0] + space
                    available = right_edge - words[-1][2]
                    line_result["remaining_width_pt"] = round(available, 3)
                    line_result["next_word"] = next_word[4]
                    if needed + 0.5 < available:
                        errors.append(
                            f"Page {page_number}: {label} line ends prematurely; "
                            f"next word {next_word[4]!r} needs {needed:.2f}pt "
                            f"but {available:.2f}pt remains"
                        )
            checked.append(line_result)
    if not checked:
        errors.append("No paragraph lead-in lines checked")
    return {"lines": checked, "errors": errors}


def normalized_text(document):
    return re.sub(r"\s+", "", "".join(page.get_text() for page in document))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf")
    parser.add_argument("--lead-in", action="append", dest="leadins")
    parser.add_argument("--max-gap-heights", type=float, default=2.0)
    parser.add_argument("--expected-lines", type=int, required=True)
    parser.add_argument("--reference")
    args = parser.parse_args()
    if args.max_gap_heights <= 0 or args.expected_lines < 1:
        parser.error("Gap limit and expected line count must be positive")
    with fitz.open(args.pdf) as document:
        result = check_spacing(document, set(args.leadins or ["Results", "Analysis"]),
                               args.max_gap_heights)
        if len(result["lines"]) != args.expected_lines:
            result["errors"].append(
                f"Found {len(result['lines'])} lead-in lines, expected {args.expected_lines}"
            )
        if args.reference:
            with fitz.open(args.reference) as reference:
                result["ordered_text_preserved"] = normalized_text(document) == normalized_text(reference)
            if not result["ordered_text_preserved"]:
                result["errors"].append("Ordered text differs from the reference conversion")
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result["errors"] else 0)


if __name__ == "__main__":
    main()