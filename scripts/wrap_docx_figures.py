#!/usr/bin/env python3
"""Float the figures marked `.wrap-left` / `.wrap-right` in a text box, in Word.

Pandoc places every image in the line of text; it has no way to float one.
Floating the picture by hand in Word floats the picture alone, and its caption,
an ordinary paragraph, stays behind in the text. So `filters/wrap-figure.lua`
leaves comments around each marked figure, and this script moves the figure's
paragraphs -- the picture and its caption -- into a borderless text box anchored
to the paragraph that follows. Text wraps around the box, and the caption stays
under the picture because both are inside it.

The box is as wide as the picture. Its height is the picture's plus an estimate
for the caption, and the box is set to resize to fit its text, so Word corrects
the estimate when it lays the page out.

`render.py` runs this after rendering to docx. To run it by hand:

    python scripts/wrap_docx_figures.py <file>.docx
    python scripts/wrap_docx_figures.py <file>.docx --check
"""

from __future__ import annotations

import argparse
import math
import re
import shutil
import sys
import zipfile
from pathlib import Path

DOCUMENT = 'word/document.xml'
START = re.compile(r'<!--WRAP-FIGURE (left|right)-->')
END = '<!--/WRAP-FIGURE-->'
WPS = 'http://schemas.microsoft.com/office/word/2010/wordprocessingShape'

EMU_PER_PT = 12700
GAP = 228600                  # 0.25 in between the box and the text beside it
CAPTION_PT = 11               # the Image Caption style's size, for the estimate
CAPTION_LINE = 1.25           # line height as a multiple of the font size

EXTENT = re.compile(r'<wp:extent cx="(\d+)" cy="(\d+)"\s*/>')
DOC_PR_ID = re.compile(r'<wp:docPr\b[^>]*\bid="(\d+)"')
CAPTION = re.compile(r'<w:p\b(?:(?!</w:p>).)*w:val="ImageCaption".*?</w:p>', re.S)
TEXT = re.compile(r'<w:t[^>]*>([^<]*)</w:t>')
PPR = re.compile(r'<w:p\b[^>]*>\s*<w:pPr>.*?</w:pPr>', re.S)
P_OPEN = re.compile(r'<w:p\b[^>]*>')


def caption_height(paragraphs: str, width: int) -> int:
    """An estimate of the captions' height, in EMU, at the box's width."""
    line = CAPTION_PT * CAPTION_LINE * EMU_PER_PT
    # A Hebrew letter in David averages a little over half the font size wide.
    per_line = max(1, int(width / (CAPTION_PT * 0.55 * EMU_PER_PT)))
    lines = 0
    for caption in CAPTION.findall(paragraphs):
        for piece in re.split(r'<w:br\s*/>', caption):
            lines += max(1, math.ceil(len(''.join(TEXT.findall(piece))) / per_line))
    # The caption's 12 pt of space after, and a little for the picture's paragraph.
    return int(lines * line + 18 * EMU_PER_PT)


def text_box(paragraphs: str, side: str, shape_id: int) -> str:
    """A run holding a floating, borderless text box with `paragraphs` inside."""
    extent = EXTENT.search(paragraphs)
    if not extent:
        sys.exit('a wrapped figure holds no picture')
    width = int(extent.group(1))
    height = int(extent.group(2)) + caption_height(paragraphs, width)
    dist_l, dist_r = (0, GAP) if side == 'left' else (GAP, 0)
    return (
        '<w:r><w:drawing>'
        f'<wp:anchor distT="0" distB="{GAP // 2}" distL="{dist_l}" distR="{dist_r}" '
        'simplePos="0" relativeHeight="251659264" behindDoc="0" locked="0" '
        'layoutInCell="1" allowOverlap="0">'
        '<wp:simplePos x="0" y="0"/>'
        f'<wp:positionH relativeFrom="margin"><wp:align>{side}</wp:align></wp:positionH>'
        '<wp:positionV relativeFrom="paragraph"><wp:posOffset>0</wp:posOffset></wp:positionV>'
        f'<wp:extent cx="{width}" cy="{height}"/>'
        '<wp:effectExtent l="0" t="0" r="0" b="0"/>'
        '<wp:wrapSquare wrapText="bothSides"/>'
        f'<wp:docPr id="{shape_id}" name="Figure {shape_id}"/>'
        '<wp:cNvGraphicFramePr/>'
        f'<a:graphic><a:graphicData uri="{WPS}">'
        '<wps:wsp><wps:cNvSpPr txBox="1"/>'
        '<wps:spPr><a:xfrm><a:off x="0" y="0"/>'
        f'<a:ext cx="{width}" cy="{height}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        '<a:noFill/><a:ln><a:noFill/></a:ln></wps:spPr>'
        f'<wps:txbx><w:txbxContent>{paragraphs}</w:txbxContent></wps:txbx>'
        '<wps:bodyPr rot="0" vert="horz" wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" '
        'anchor="t" anchorCtr="0"><a:spAutoFit/></wps:bodyPr>'
        '</wps:wsp></a:graphicData></a:graphic>'
        '</wp:anchor></w:drawing></w:r>'
    )


def anchor_into(paragraph_xml: str, run: str) -> str:
    """Put `run` first in the paragraph, after its properties."""
    props = PPR.match(paragraph_xml)
    at = props.end() if props else P_OPEN.match(paragraph_xml).end()
    return paragraph_xml[:at] + run + paragraph_xml[at:]


def convert(xml: str) -> tuple[str, int]:
    """Box every marked figure, and remove the markers. Returns (xml, count)."""
    ids = [int(i) for i in DOC_PR_ID.findall(xml)]
    next_id = max(ids, default=0) + 1000
    done = 0
    while (start := START.search(xml)):
        end = xml.find(END, start.end())
        if end < 0:
            sys.exit('a WRAP-FIGURE marker is never closed')
        inner = xml[start.end():end].strip()
        after = end + len(END)
        # The box anchors to the paragraph after the figure, so text starts
        # beside it rather than below it.
        nxt = P_OPEN.search(xml, after)
        if not nxt or xml[after:nxt.start()].strip():
            sys.exit('a wrapped figure must be followed by a paragraph')
        close = xml.index('</w:p>', nxt.start()) + len('</w:p>')
        anchored = anchor_into(xml[nxt.start():close], text_box(inner, start.group(1), next_id))
        xml = xml[:start.start()] + anchored + xml[close:]
        next_id += 1
        done += 1
    if done and 'xmlns:wps=' not in xml[:2000]:
        xml = xml.replace('<w:document ', f'<w:document xmlns:wps="{WPS}" ', 1)
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
        print(f'{args.docx.name}: {len(START.findall(xml))} figure(s) still marked, '
              f'{xml.count("<w:txbxContent>")} text box(es)')
        return

    fixed, boxes = convert(xml)
    if not boxes:
        print(f'{args.docx.name}: no figures to wrap')
        return

    parts[DOCUMENT] = fixed.encode('utf-8')
    backup = args.docx.with_suffix('.docx.orig')
    shutil.copy2(args.docx, backup)
    with zipfile.ZipFile(args.docx, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, blob in parts.items():
            archive.writestr(name, blob)
    backup.unlink()
    print(f'{args.docx.name}: {boxes} figure(s) floated in a text box')


if __name__ == '__main__':
    main()
