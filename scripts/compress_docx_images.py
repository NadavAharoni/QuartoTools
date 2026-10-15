#!/usr/bin/env python3
"""Shrink the pictures in a Word file, as Word's Compress Pictures does.

A rendered document carries every photo at the resolution it was taken at, which
makes a file too large to pass around for comments. This writes a copy,
`<name>.compressed.docx`, in which each picture is

* scaled down to what it needs at the size it is shown: 150 ppi by default, Word's
  "Web" setting. A picture already at or below that is left as it is.
* cropped for real when it was cropped in Word: the hidden parts are deleted, as
  Word's "Delete cropped areas of pictures" does.
* stored as JPEG when it is a photo in a PNG with no transparency. A PNG with few
  colours, such as a diagram, stays PNG, where JPEG would blur its edges.

The original is not touched; keep it for print.

    python scripts/compress_docx_images.py <file>.docx
    python scripts/compress_docx_images.py <file>.docx --ppi 220
    python scripts/compress_docx_images.py <file>.docx -o smaller.docx

Needs Pillow (`pip install pillow`).
"""

from __future__ import annotations

import argparse
import io
import posixpath
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit('compress_docx_images.py needs Pillow: pip install pillow')

EMU_PER_INCH = 914400
CROP_UNIT = 100000            # a:srcRect sides are thousandths of a percent
NOT_WORTH_IT = 0.9            # a picture within 10% of its target size is left alone

PIC = re.compile(r'<pic:pic\b.*?</pic:pic>', re.S)
BLIP = re.compile(r'<a:blip\b[^>]*\br:embed="([^"]+)"')
EXT = re.compile(r'<a:ext cx="(\d+)" cy="(\d+)"')
SRC_RECT = re.compile(r'<a:srcRect\b([^>]*?)\s*(?:/>|>\s*</a:srcRect>)')
SIDE = re.compile(r'\b([ltrb])="(-?\d+)"')
RELATIONSHIP = re.compile(r'<Relationship\b[^>]*>')
ATTR = re.compile(r'(\w+)="([^"]*)"')
RELS = re.compile(r'(.*/)?_rels/([^/]+)\.rels$')


@dataclass
class Use:
    """One place a picture is shown: its size on the page and its crop."""
    part: str
    cx: int
    cy: int
    crop: tuple[int, int, int, int]       # l, t, r, b in CROP_UNIT


@dataclass
class Picture:
    name: str                              # its part name, e.g. word/media/rId22.png
    uses: list[Use] = field(default_factory=list)
    other_refs: bool = False               # referenced other than from a <pic:pic>


def resolve(source_part: str, target: str) -> str:
    if target.startswith('/'):
        return target.lstrip('/')
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))


def relationships(parts: dict[str, bytes]) -> dict[str, dict[str, str]]:
    """{part: {rId: target part}} for every part that has relationships."""
    found = {}
    for name, blob in parts.items():
        m = RELS.match(name)
        if not m:
            continue
        source = (m.group(1) or '') + m.group(2)
        rels = {}
        for rel in RELATIONSHIP.findall(blob.decode('utf-8')):
            attrs = dict(ATTR.findall(rel))
            if attrs.get('TargetMode') != 'External' and 'Id' in attrs:
                rels[attrs['Id']] = resolve(source, attrs['Target'])
        found[source] = rels
    return found


def crop_of(pic: str) -> tuple[int, int, int, int]:
    rect = SRC_RECT.search(pic)
    sides = dict(SIDE.findall(rect.group(1))) if rect else {}
    return tuple(int(sides.get(s, 0)) for s in 'ltrb')


def find_pictures(parts: dict[str, bytes], rels: dict[str, dict[str, str]]) -> dict[str, Picture]:
    pictures: dict[str, Picture] = {}
    for part, part_rels in rels.items():
        if part not in parts or not part.endswith('.xml'):
            continue
        xml = parts[part].decode('utf-8')
        blip_count: dict[str, int] = {}
        for pic in PIC.findall(xml):
            blip, ext = BLIP.search(pic), EXT.search(pic)
            if not blip or not ext or blip.group(1) not in part_rels:
                continue
            rid = blip.group(1)
            name = part_rels[rid]
            pictures.setdefault(name, Picture(name)).uses.append(
                Use(part, int(ext.group(1)), int(ext.group(2)), crop_of(pic)))
            blip_count[rid] = blip_count.get(rid, 0) + 1
        # A picture also used from VML or anywhere else must keep its pixels where
        # they are, since that use is not adjusted when the picture is cropped.
        for rid, count in blip_count.items():
            if xml.count(f'"{rid}"') > count:
                pictures[part_rels[rid]].other_refs = True
    return pictures


def is_photo(image: Image.Image) -> bool:
    """Opaque and with many colours: a photo, which JPEG stores far smaller than PNG."""
    if 'transparency' in image.info:
        return False
    if 'A' in image.getbands() and image.getchannel('A').getextrema()[0] < 255:
        return False
    return image.getcolors(maxcolors=4096) is None


@dataclass
class Result:
    blob: bytes
    name: str
    cropped: bool
    note: str


def compress(picture: Picture, blob: bytes, ppi: int, quality: int, keep_png: bool) -> Result | None:
    """The picture's new bytes and name, or None to leave it as it is."""
    ext = posixpath.splitext(picture.name)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png'):
        return None
    image = Image.open(io.BytesIO(blob))
    image.load()
    # Word ignores a photo's EXIF rotation, so cropping by the stored pixels would be
    # right, but a picture carrying one is rare enough to leave alone than to get wrong.
    if image.getexif().get(0x0112, 1) != 1:
        return None
    icc = image.info.get('icc_profile')
    width, height = image.size

    crops = {u.crop for u in picture.uses}
    crop = next(iter(crops))
    cropped = (len(crops) == 1 and crop != (0, 0, 0, 0) and min(crop) >= 0
               and sum(crop[0::2]) < CROP_UNIT and sum(crop[1::2]) < CROP_UNIT
               and not picture.other_refs)
    if cropped:
        l, t, r, b = crop
        box = (round(width * l / CROP_UNIT), round(height * t / CROP_UNIT),
               round(width * (1 - r / CROP_UNIT)), round(height * (1 - b / CROP_UNIT)))
        image = image.crop(box)

    # The scale each use needs: its size on the page at `ppi`, over the pixels it shows.
    scale = 0.0
    for use in picture.uses:
        l, t, r, b = (0, 0, 0, 0) if cropped else use.crop
        shown_w = image.width * max(1 - (l + r) / CROP_UNIT, 0.01)
        shown_h = image.height * max(1 - (t + b) / CROP_UNIT, 0.01)
        scale = max(scale, ppi * use.cx / EMU_PER_INCH / shown_w,
                    ppi * use.cy / EMU_PER_INCH / shown_h)
    resized = scale < NOT_WORTH_IT
    if resized:
        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        image = image.resize(size, Image.Resampling.LANCZOS)

    to_jpeg = ext == '.png' and not keep_png and is_photo(image)
    if not (cropped or resized or to_jpeg):
        return None

    out = io.BytesIO()
    if ext != '.png' or to_jpeg:
        if image.mode not in ('RGB', 'L', 'CMYK'):
            image = image.convert('RGB')
        image.save(out, 'JPEG', quality=quality, optimize=True, icc_profile=icc,
                   dpi=(ppi, ppi))
        name = posixpath.splitext(picture.name)[0] + ('.jpg' if to_jpeg else ext)
    else:
        image.save(out, 'PNG', optimize=True, icc_profile=icc, dpi=(ppi, ppi))
        name = picture.name
    if len(out.getvalue()) >= len(blob) and not cropped:
        return None

    notes = []
    if cropped:
        notes.append('cropped')
    notes.append(f'{width}x{height} -> {image.width}x{image.height}' if (cropped or resized)
                 else f'{width}x{height}')
    if to_jpeg:
        notes.append('PNG -> JPEG')
    return Result(out.getvalue(), name, cropped, ', '.join(notes))


def drop_crop(xml: str, rids: set[str]) -> str:
    """Remove the crop from each <pic:pic> showing one of `rids`, now that its pixels are cropped."""
    def fix(m: re.Match) -> str:
        blip = BLIP.search(m.group(0))
        return SRC_RECT.sub('<a:srcRect/>', m.group(0)) if blip and blip.group(1) in rids else m.group(0)
    return PIC.sub(fix, xml)


def rename_in_rels(xml: str, source: str, old: str, new: str) -> str:
    def fix(m: re.Match) -> str:
        attrs = dict(ATTR.findall(m.group(0)))
        if attrs.get('TargetMode') == 'External' or resolve(source, attrs.get('Target', '')) != old:
            return m.group(0)
        target = attrs['Target']
        return m.group(0).replace(f'Target="{target}"',
                                  f'Target="{posixpath.join(posixpath.dirname(target), posixpath.basename(new))}"')
    return RELATIONSHIP.sub(fix, xml)


def ensure_jpeg_type(xml: str, renamed: dict[str, str]) -> str:
    """Declare the .jpg extension, and drop any per-part type the old PNG names had."""
    for old in renamed:
        xml = re.sub(rf'<Override PartName="/{re.escape(old)}"[^>]*/>', '', xml)
    if not re.search(r'<Default Extension="jpg"', xml, re.I):
        xml = xml.replace('</Types>', '<Default Extension="jpg" ContentType="image/jpeg"/></Types>')
    return xml


def kb(n: int) -> str:
    return f'{n / 1024:,.0f} KB'


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('docx', type=Path, help='the Word file to compress')
    parser.add_argument('-o', '--output', type=Path,
                        help='where to write the copy; default <name>.compressed.docx beside it')
    parser.add_argument('--ppi', type=int, default=150,
                        help='pixels per inch to keep, at the size each picture is shown (default 150; '
                             'Word offers 96 for email, 150 for web, 220 for print)')
    parser.add_argument('--quality', type=int, default=85, help='JPEG quality, 1-95 (default 85)')
    parser.add_argument('--keep-png', action='store_true', help='never turn a PNG into a JPEG')
    args = parser.parse_args()

    if not args.docx.is_file():
        sys.exit(f'no such file: {args.docx}')
    output = args.output or args.docx.with_name(args.docx.stem + '.compressed.docx')
    if output.resolve() == args.docx.resolve():
        sys.exit('the output would overwrite the original; pass a different -o')

    with zipfile.ZipFile(args.docx) as archive:
        parts = {info.filename: archive.read(info) for info in archive.infolist()}

    rels = relationships(parts)
    pictures = find_pictures(parts, rels)
    renamed: dict[str, str] = {}
    cropped: set[str] = set()
    for name in sorted(pictures):
        old = parts[name]
        result = compress(pictures[name], old, args.ppi, args.quality, args.keep_png)
        if not result:
            print(f'  {posixpath.basename(name)}: {kb(len(old))}, left as it is')
            continue
        new_name = result.name
        if new_name != name:
            stem, ext = posixpath.splitext(new_name)
            n = 1
            while new_name in parts:
                new_name, n = f'{stem}_{n}{ext}', n + 1
            del parts[name]
            renamed[name] = new_name
        parts[new_name] = result.blob
        if result.cropped:
            cropped.add(name)
        print(f'  {posixpath.basename(name)}: {kb(len(old))} -> {kb(len(result.blob))} ({result.note})')

    for source, part_rels in rels.items():
        rids = {rid for rid, target in part_rels.items() if target in cropped}
        if rids and source in parts:
            parts[source] = drop_crop(parts[source].decode('utf-8'), rids).encode('utf-8')
    for rels_name in [n for n in parts if RELS.match(n)]:
        m = RELS.match(rels_name)
        source = (m.group(1) or '') + m.group(2)
        xml = parts[rels_name].decode('utf-8')
        for old, new in renamed.items():
            xml = rename_in_rels(xml, source, old, new)
        parts[rels_name] = xml.encode('utf-8')
    if renamed:
        types = '[Content_Types].xml'
        parts[types] = ensure_jpeg_type(parts[types].decode('utf-8'), renamed).encode('utf-8')

    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, blob in parts.items():
            archive.writestr(name, blob)
    before, after = args.docx.stat().st_size, output.stat().st_size
    print(f'{output.name}: {before / 2**20:.1f} MB -> {after / 2**20:.1f} MB')


if __name__ == '__main__':
    main()
