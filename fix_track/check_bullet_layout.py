"""Check isolated bullet starts and contiguous hanging lines in a reflowed PDF.

Requires PyMuPDF. Intended for reviewed text-list fixtures, not figure/table pages.
Example: python fix_track/check_bullet_layout.py output.pdf --expected-items 4
"""

import argparse
import json

import fitz


def check_layout(document, expected_items, tolerance=1.0):
    lines = []
    for page_number, page in enumerate(document, start=1):
        page_lines = []
        for word in sorted(page.get_text("words"), key=lambda word: (word[1], word[0])):
            if not page_lines or abs(page_lines[-1][0][1] - word[1]) > 1.5:
                page_lines.append([word])
            else:
                page_lines[-1].append(word)
        for words in page_lines:
            lines.append((page_number, sorted(words, key=lambda word: word[0])))

    errors = []
    markers = []
    continuation_count = 0
    text_start = None
    previous_page = previous_top = previous_height = None
    for page_number, words in lines:
        bullet_positions = [index for index, word in enumerate(words)
                            if word[4] in {"\u2022", "\u00b7", "\u25cf"}]
        top = min(word[1] for word in words)
        height = max(word[3] for word in words) - top
        if bullet_positions:
            for position in bullet_positions:
                markers.append({"page": page_number, "x": words[position][0], "y": top})
                if position != 0:
                    errors.append(f"Page {page_number}: bullet follows preceding text")
            position = bullet_positions[-1]
            if position + 1 == len(words):
                errors.append(f"Page {page_number}: isolated marker without item text")
                text_start = None
            else:
                text_start = words[position + 1][0]
        elif text_start is not None:
            if page_number == previous_page and top - previous_top > previous_height * 2:
                text_start = None
            else:
                continuation_count += 1
                if abs(words[0][0] - text_start) > tolerance:
                    errors.append(f"Page {page_number}: hanging line starts at {words[0][0]:.2f}, "
                                  f"expected {text_start:.2f}")
        previous_page, previous_top, previous_height = page_number, top, height
    if len(markers) != expected_items:
        errors.append(f"Found {len(markers)} markers, expected {expected_items}")
    if continuation_count == 0:
        errors.append("No continuation lines checked")
    return {"markers": markers, "continuation_lines_checked": continuation_count,
            "errors": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf")
    parser.add_argument("--expected-items", type=int, required=True)
    parser.add_argument("--tolerance", type=float, default=1.0)
    args = parser.parse_args()
    with fitz.open(args.pdf) as document:
        result = check_layout(document, args.expected_items, args.tolerance)
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result["errors"] else 0)


if __name__ == "__main__":
    main()