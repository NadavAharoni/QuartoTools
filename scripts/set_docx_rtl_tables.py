#!/usr/bin/env python3
"""Make Word lay tables out right to left, in a .docx or in a reference template.

`dir: rtl` reaches paragraphs but not tables. A Word table is laid out left to
right unless its properties carry `w:bidiVisual`, and the text inside its cells
follows the cell paragraphs, which need `w:bidi`. Pandoc gives every table it
writes the style named `Table` from the reference document, so setting both on
that style is enough for every table in every document rendered from it.

Run it once on the template; the change is then part of `hebrew.docx` and no
document has to know about it.

Usage:
    python quarto/scripts/set_docx_rtl_tables.py quarto/templates/hebrew.docx
    python quarto/scripts/set_docx_rtl_tables.py <file>.docx --style TableGrid
    python quarto/scripts/set_docx_rtl_tables.py <file>.docx --check
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

STYLES = 'word/styles.xml'
BIDI_VISUAL = '<w:bidiVisual/>'
BIDI_PARA = '<w:pPr><w:bidi/></w:pPr>'


def style_block(xml: str, style_id: str) -> re.Match | None:
    """The whole <w:style> element for this style id, or None."""
    return re.search(
        r'<w:style\b[^>]*w:styleId="%s".*?</w:style>' % re.escape(style_id),
        xml, re.S)


def patch_style(block: str) -> tuple[str, list[str]]:
    """Add bidiVisual and a right-to-left cell paragraph to one style element."""
    done = []

    # Schema order inside w:tblPr puts bidiVisual before tblInd, so it goes
    # first, straight after the opening tag.
    if BIDI_VISUAL not in block:
        if '<w:tblPr>' in block:
            block = block.replace('<w:tblPr>', '<w:tblPr>' + BIDI_VISUAL, 1)
        elif '<w:tblPr/>' in block:
            block = block.replace('<w:tblPr/>', '<w:tblPr>' + BIDI_VISUAL + '</w:tblPr>', 1)
        else:
            block = block.replace('</w:style>', '<w:tblPr>' + BIDI_VISUAL + '</w:tblPr></w:style>', 1)
        done.append('table laid out right to left')

    # w:pPr precedes w:tblPr in a style element.
    if '<w:bidi/>' not in block:
        if '<w:pPr>' in block:
            block = block.replace('<w:pPr>', '<w:pPr><w:bidi/>', 1)
        else:
            anchor = '<w:tblPr>' if '<w:tblPr>' in block else '</w:style>'
            block = block.replace(anchor, BIDI_PARA + anchor, 1)
        done.append('cell text right to left')

    return block, done


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('docx', help='.docx file or reference template to patch')
    ap.add_argument('--style', default='Table',
                    help='table style to patch (default: Table, the one pandoc uses)')
    ap.add_argument('--check', action='store_true',
                    help='report whether the style is already right to left, change nothing')
    args = ap.parse_args()

    path = Path(args.docx)
    if not path.is_file():
        sys.exit(f'no such file: {path}')

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        if STYLES not in names:
            sys.exit(f'{path} has no {STYLES}; is it a .docx?')
        payload = {name: zf.read(name) for name in names}

    xml = payload[STYLES].decode('utf-8')
    found = style_block(xml, args.style)
    if not found:
        sys.exit(f'no table style named {args.style!r} in {path}')

    patched, done = patch_style(found.group(0))

    if args.check:
        print(f'{path}: style {args.style} is '
              + ('already right to left' if not done else 'left to right (' + ', '.join(done) + ' missing)'))
        return

    if not done:
        print(f'{path}: style {args.style} is already right to left, nothing to do')
        return

    xml = xml[:found.start()] + patched + xml[found.end():]
    payload[STYLES] = xml.encode('utf-8')

    backup = path.with_suffix(path.suffix + '.bak')
    shutil.copy2(path, backup)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as out:
        for name in names:
            out.writestr(name, payload[name])

    print(f'{path}: {", ".join(done)} (previous file kept at {backup.name})')


if __name__ == '__main__':
    main()
