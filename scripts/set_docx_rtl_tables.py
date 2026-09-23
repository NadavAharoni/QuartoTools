#!/usr/bin/env python3
"""Lay out right-to-left the tables that `filters/auto-direction.lua` marked.

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

    python scripts/set_docx_rtl_tables.py <file>.docx
    python scripts/set_docx_rtl_tables.py <file>.docx --check
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

DOCUMENT = 'word/document.xml'
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
        tables = xml.count('<w:tbl>')
        print(f'{args.docx.name}: {tables} tables, '
              f'{xml.count(MARKER)} still marked, '
              f'{xml.count("bidiVisual")} laid out right to left')
        return

    fixed, done = convert(xml)
    if not done and fixed == xml:
        print(f'{args.docx.name}: no marked tables, nothing to do')
        return

    parts[DOCUMENT] = fixed.encode('utf-8')
    backup = args.docx.with_suffix('.docx.orig')
    shutil.copy2(args.docx, backup)
    with zipfile.ZipFile(args.docx, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, blob in parts.items():
            archive.writestr(name, blob)
    backup.unlink()
    print(f'{args.docx.name}: {done} table(s) laid out right to left')


if __name__ == '__main__':
    main()
