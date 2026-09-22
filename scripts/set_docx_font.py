#!/usr/bin/env python3
"""Force a font onto a rendered .docx, including the Hebrew (complex-script) slot.

Why this is a post-processing step rather than a reference document
------------------------------------------------------------------
Quarto's `mainfont:` does not reach .docx at all. The documented alternative,
`reference-doc:`, does not work either: pandoc re-serializes the reference
document's styles (dropping attributes it does not recognise) and keeps **its own**
`word/theme/theme1.xml` and `<w:docDefaults>` regardless of what the reference
document says. Patching a template therefore cannot win.

What actually decides how Hebrew looks in Word
----------------------------------------------
Two things, and both must be handled:

1. `<w:docDefaults>` uses *theme references* (`w:cstheme="minorBidi"`), not font
   names, so fonts resolve through the theme.
2. The theme's font scheme carries **per-script fallbacks** — including
   `<a:font script="Hebr" typeface="Times New Roman"/>`. That entry beats the
   generic `<a:latin>`/`<a:cs>` for Hebrew text specifically. It is why setting
   only the Latin font changes headings and leaves body text in Times New Roman.

Word draws right-to-left text with the complex-script slot (`w:cs` / `NameBi`), so
that is the slot that matters; the Latin slot governs embedded English terms.

Usage:
    python set_docx_font.py update.docx
    python set_docx_font.py update.docx --font FrankRuehl --latin-font Calibri
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

# Theme font attributes resolve through the theme and beat explicit names.
THEME_ATTRS = ("asciiTheme", "hAnsiTheme", "cstheme", "eastAsiaTheme")

# Scripts that should follow the Hebrew font choice.
RTL_SCRIPTS = ("Hebr",)


def strip_theme_attrs(xml: str) -> str:
    for attr in THEME_ATTRS:
        xml = re.sub(rf'\s+w:{attr}="[^"]*"', "", xml)
    return xml


def set_rfonts(xml: str, hebrew: str, latin: str) -> str:
    """Rewrite every existing <w:rFonts> to the chosen fonts."""
    replacement = (f'<w:rFonts w:ascii="{latin}" w:hAnsi="{latin}" '
                   f'w:cs="{hebrew}" w:eastAsia="{latin}"/>')
    xml = re.sub(r"<w:rFonts\b[^>]*/>", replacement, xml)
    xml = re.sub(r"<w:rFonts\b[^>]*>.*?</w:rFonts>", replacement, xml, flags=re.S)
    return xml


def pin_styles(xml: str, hebrew: str, latin: str) -> str:
    """Give every style an explicit <w:rFonts>, creating <w:rPr> where needed.

    A style that inherits its font silently can still resolve against Word's own
    template instead of this document, so inheritance is not good enough.
    """
    rfonts = (f'<w:rFonts w:ascii="{latin}" w:hAnsi="{latin}" '
              f'w:cs="{hebrew}" w:eastAsia="{latin}"/>')

    def fix(match: re.Match) -> str:
        style = match.group(0)
        if "<w:rFonts" in style:
            return style
        if "<w:rPr>" in style:
            return style.replace("<w:rPr>", f"<w:rPr>{rfonts}", 1)
        # w:rPr follows w:pPr in the schema.
        if "</w:pPr>" in style:
            return style.replace("</w:pPr>", f"</w:pPr><w:rPr>{rfonts}</w:rPr>", 1)
        return style.replace("</w:style>", f"<w:rPr>{rfonts}</w:rPr></w:style>", 1)

    return re.sub(r"<w:style\b.*?</w:style>", fix, xml, flags=re.S)


def pin_runs(xml: str, hebrew: str, latin: str) -> str:
    """Put an explicit <w:rFonts> on every run in the body.

    This is the pass that actually settles it. Direct run formatting outranks
    styles, `<w:docDefaults>`, and the theme, so nothing downstream can reintroduce
    Times New Roman. It is needed because pandoc writes Hebrew runs as
    `<w:r><w:rPr><w:rtl/></w:rPr>` — marked right-to-left but naming no font, which
    leaves the complex-script slot to be resolved by everything above.
    """
    rfonts = (f'<w:rFonts w:ascii="{latin}" w:hAnsi="{latin}" '
              f'w:cs="{hebrew}" w:eastAsia="{latin}"/>')

    # A run that already has run properties but no font.
    def add_to_rpr(match: re.Match) -> str:
        block = match.group(0)
        if "<w:rFonts" in block:
            return block
        return block.replace("<w:rPr>", f"<w:rPr>{rfonts}", 1)

    xml = re.sub(r"<w:rPr>.*?</w:rPr>", add_to_rpr, xml, flags=re.S)
    # Self-closing run properties carry nothing at all.
    xml = xml.replace("<w:rPr/>", f"<w:rPr>{rfonts}</w:rPr>")
    # A run with no run properties at all: w:rPr must come first inside w:r.
    xml = re.sub(r"<w:r>(?!\s*<w:rPr)", f"<w:r><w:rPr>{rfonts}</w:rPr>", xml)

    # Empty paragraphs and empty table cells hold no run at all, so they keep
    # inheriting. Nothing is visible there today, but text typed into them later
    # would come out in the inherited font. Pin the paragraph mark too — w:rPr is
    # the last child of w:pPr.
    def add_to_ppr(match: re.Match) -> str:
        block = match.group(0)
        if "<w:rPr>" in block:
            return block
        return block.replace("</w:pPr>", f"<w:rPr>{rfonts}</w:rPr></w:pPr>", 1)

    xml = re.sub(r"<w:pPr>.*?</w:pPr>", add_to_ppr, xml, flags=re.S)
    return xml


def ensure_doc_defaults(xml: str, hebrew: str, latin: str) -> str:
    """Make sure the document-wide default names fonts instead of the theme."""
    if "<w:rPrDefault>" not in xml:
        return xml
    head = xml.split("</w:rPrDefault>")[0]
    if "<w:rFonts" in head:
        return xml  # set_rfonts already rewrote it
    rfonts = (f'<w:rFonts w:ascii="{latin}" w:hAnsi="{latin}" '
              f'w:cs="{hebrew}" w:eastAsia="{latin}"/>')
    if "<w:rPrDefault><w:rPr>" in xml:
        return xml.replace("<w:rPrDefault><w:rPr>", f"<w:rPrDefault><w:rPr>{rfonts}", 1)
    return xml.replace("<w:rPrDefault>", f"<w:rPrDefault><w:rPr>{rfonts}</w:rPr>", 1)


def patch_theme(xml: str, hebrew: str, latin: str) -> str:
    """Retarget the theme, including the per-script Hebrew fallback."""
    xml = re.sub(r'<a:latin typeface="[^"]*"', f'<a:latin typeface="{latin}"', xml)
    xml = re.sub(r'<a:cs typeface="[^"]*"', f'<a:cs typeface="{hebrew}"', xml)
    for script in RTL_SCRIPTS:
        xml = re.sub(
            rf'<a:font script="{script}" typeface="[^"]*"\s*/>',
            f'<a:font script="{script}" typeface="{hebrew}"/>',
            xml,
        )
    return xml


def patch_docx(path: Path, hebrew: str, latin: str) -> dict[str, int]:
    stats = {"styles": 0, "runs": 0, "theme_script_entries": 0}
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / path.name
        shutil.copy2(path, staged)
        with zipfile.ZipFile(staged) as zin, \
             zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                name = item.filename
                body_parts = ("word/document.xml", "word/footnotes.xml", "word/endnotes.xml")
                # numbering.xml names the font for list markers; leaving it out
                # leaves Arial embedded for the numerals of ordered lists.
                if name in ("word/styles.xml", "word/settings.xml",
                            "word/numbering.xml") + body_parts:
                    xml = strip_theme_attrs(data.decode("utf-8"))
                    xml = set_rfonts(xml, hebrew, latin)
                    if name == "word/styles.xml":
                        xml = ensure_doc_defaults(xml, hebrew, latin)
                        xml = pin_styles(xml, hebrew, latin)
                        stats["styles"] = len(re.findall(r"<w:style\b[^>]*>", xml))
                    if name in body_parts:
                        xml = pin_runs(xml, hebrew, latin)
                        if name == "word/document.xml":
                            stats["runs"] = xml.count("<w:rFonts")
                    data = xml.encode("utf-8")
                elif name.startswith("word/theme/"):
                    xml = patch_theme(data.decode("utf-8"), hebrew, latin)
                    stats["theme_script_entries"] = len(
                        re.findall(rf'script="(?:{"|".join(RTL_SCRIPTS)})" '
                                   rf'typeface="{re.escape(hebrew)}"', xml)
                    )
                    data = xml.encode("utf-8")
                zout.writestr(item, data)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx", nargs="+", type=Path, help=".docx file(s) to patch in place")
    parser.add_argument("--font", default="David",
                        help="font for Hebrew / complex-script text (default: David)")
    parser.add_argument("--latin-font", default=None,
                        help="font for Latin text (default: same as --font)")
    parser.add_argument("--if-exists", action="store_true",
                        help="skip missing files instead of failing (for render wrappers)")
    args = parser.parse_args()
    latin = args.latin_font or args.font

    missing = [p for p in args.docx if not p.is_file()]
    if missing and not args.if_exists:
        sys.exit(f"not found: {', '.join(str(p) for p in missing)}")
    args.docx = [p for p in args.docx if p.is_file()]

    for path in args.docx:
        stats = patch_docx(path, args.font, latin)
        print(f"{path.name}: {args.font} (Hebrew) / {latin} (Latin) — "
              f"{stats['styles']} styles, {stats['runs']} run font tags, "
              f"{stats['theme_script_entries']} theme script entries")


if __name__ == "__main__":
    main()
