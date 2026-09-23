#!/usr/bin/env python3
"""Set the direction of the tables and captions the filter could not reach.

Word lays a table out left to right unless the table itself carries
`w:bidiVisual`, so a Hebrew table comes out with its first column on the left.
Two things about this are easy to get wrong, and both were measured:

* Setting `w:bidiVisual` on the `Table` **style** does nothing. Word ignores it
  there, and worse, it then cancels the same setting on the table itself, so a
  template carrying it prevents the fix from ever working.
* `w:bidiVisual` must therefore go on each `w:tbl` that needs it, which no
  pandoc filter can do -- a filter cannot reach a table's properties.

So `filters/auto-direction.lua` writes a comment into the output before each
table that must be right to left, and this script turns those comments into the
real thing. Tables with no marker are left alone, which is the point: a document can
hold both right-to-left and left-to-right tables.

`render.py` runs this after rendering to docx. To run it by hand:

    python scripts/set_docx_direction.py <file>.docx
    python scripts/set_docx_direction.py <file>.docx --check
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

DOCUMENT = 'word/document.xml'
CAPTION_STYLE = re.compile(r'<w:pStyle w:val="\w*Caption\w*"\s*/>')
PARAGRAPH = re.compile(r'<w:p\b.*?</w:p>', re.S)
TEXT = re.compile(r'<w:t[^>]*>([^<]*)</w:t>')
BIDI = re.compile(r'<w:bidi\s*/>')
RTL_RUN = re.compile(r'<w:rtl\s*/>')
PPR_OPEN = re.compile(r'<w:pPr\s*>')

# The same ranges the Lua filter uses, so both agree on where a line starts.
RTL_RANGES = ((0x0590, 0x05FF), (0x0600, 0x07BF), (0x0860, 0x08FF),
              (0xFB1D, 0xFDFF), (0xFE70, 0xFEFF),
              (0x10800, 0x10FFF), (0x1E800, 0x1EFFF))
LTR_RANGES = ((0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x02B8),
              (0x0370, 0x058F), (0x0900, 0x10FF), (0x1E00, 0x1FFF),
              (0x2C00, 0x2DFF), (0xA000, 0xD7FF))


def direction(text: str) -> str | None:
    """The direction of the first strong character, or None if there is none."""
    for char in text:
        code = ord(char)
        if any(low <= code <= high for low, high in RTL_RANGES):
            return 'rtl'
        if any(low <= code <= high for low, high in LTR_RANGES):
            return 'ltr'
    return None


def set_paragraph_direction(paragraph: str, wanted: str) -> str:
    """Make one paragraph read in `wanted`, properties and runs together."""
    if wanted == 'ltr':
        # `w:bidi` is the paragraph's direction and `w:rtl` the runs'; both have
        # to go, or the text flows one way inside a paragraph laid out the other.
        paragraph = BIDI.sub('', paragraph)
        return RTL_RUN.sub('', paragraph)
    if BIDI.search(paragraph):
        return paragraph
    opening = PPR_OPEN.search(paragraph)
    if not opening:
        return paragraph
    at = opening.end()
    return paragraph[:at] + '<w:bidi/>' + paragraph[at:]


def fix_captions(xml: str) -> tuple[str, int]:
    """Give each caption the direction of its own first strong character."""
    changed = 0

    def one(match: re.Match) -> str:
        nonlocal changed
        paragraph = match.group(0)
        if not CAPTION_STYLE.search(paragraph):
            return paragraph
        wanted = direction(''.join(TEXT.findall(paragraph)))
        if wanted is None:
            return paragraph
        fixed = set_paragraph_direction(paragraph, wanted)
        if fixed != paragraph:
            changed += 1
        return fixed

    return PARAGRAPH.sub(one, xml), changed
MARKER = '<!--RTL-TABLE-->'
BIDI_VISUAL = '<w:bidiVisual/>'

# `w:tblStyle` must stay first inside `w:tblPr`; `w:bidiVisual` belongs right
# after it. Anywhere else and Word drops the element on open.
TBL_STYLE = re.compile(r'<w:tblStyle\b[^>]*/>')
TBL_PR = re.compile(r'<w:tblPr\s*>')


def add_bidi_visual(table: str) -> tuple[str, bool]:
    """Put `w:bidiVisual` in this table's properties. Returns (xml, changed)."""
    if 'bidiVisual' in table:
        return table, False
    style = TBL_STYLE.search(table)
    if style:
        at = style.end()
    else:
        opening = TBL_PR.search(table)
        if not opening:
            return table, False
        at = opening.end()
    return table[:at] + BIDI_VISUAL + table[at:], True


def convert(xml: str) -> tuple[str, int]:
    """Apply every marker, and remove the markers. Returns (xml, count)."""
    done = 0
    while True:
        at = xml.find(MARKER)
        if at < 0:
            break
        start = xml.find('<w:tbl>', at)
        if start < 0:
            sys.exit(f'a {MARKER} marker is not followed by a table')
        end = xml.index('</w:tbl>', start) + len('</w:tbl>')
        table, changed = add_bidi_visual(xml[start:end])
        done += changed
        xml = xml[:at] + xml[at + len(MARKER):start] + table + xml[end:]
    return xml, done


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('docx', type=Path, help='the rendered .docx to fix up')
    parser.add_argument('--check', action='store_true',
                        help='report what is there, change nothing')
    parser.add_argument('--if-exists', action='store_true',
                        help='do nothing when the file is missing, rather than fail')
    args = parser.parse_args()

    if not args.docx.is_file():
        if args.if_exists:
            return
        sys.exit(f'no such file: {args.docx}')

    with zipfile.ZipFile(args.docx) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    xml = parts[DOCUMENT].decode('utf-8')

    if args.check:
        captions = sum(bool(CAPTION_STYLE.search(p)) for p in PARAGRAPH.findall(xml))
        print(f'{args.docx.name}: {xml.count("<w:tbl>")} tables, '
              f'{xml.count(MARKER)} still marked, '
              f'{xml.count("bidiVisual")} laid out right to left; '
              f'{captions} captions')
        return

    fixed, tables = convert(xml)
    fixed, captions = fix_captions(fixed)
    if fixed == xml:
        print(f'{args.docx.name}: nothing to do')
        return

    parts[DOCUMENT] = fixed.encode('utf-8')
    backup = args.docx.with_suffix('.docx.orig')
    shutil.copy2(args.docx, backup)
    with zipfile.ZipFile(args.docx, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, blob in parts.items():
            archive.writestr(name, blob)
    backup.unlink()
    print(f'{args.docx.name}: {tables} table(s) laid out right to left, '
          f'{captions} caption(s) given their own direction')


if __name__ == '__main__':
    main()
