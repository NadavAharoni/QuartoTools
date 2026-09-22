#!/usr/bin/env python3
"""Draw the schematic of a repeated short passage inside a parallel segment.

This figure existed in the Word update as native Word shapes, which carry no
image part and so are lost on conversion. Redrawing it as a script-generated SVG
follows the project convention (see CLAUDE.md) and makes it reproducible.

What it shows: a long passage is genuinely parallel between the two works, and a
short passage repeats inside it. Shmidman and MSM can both latch onto the wrong
copy of the short passage, producing a short spurious match instead of extending
the long true one.

Usage:
    python generate_repetition_schematic.py -o ../media/figures/repetition.svg
"""

from __future__ import annotations

import argparse
from pathlib import Path

# Canvas
W, H = 900, 460
FONT = "Segoe UI, Arial, Helvetica, sans-serif"

# Two text bars
BAR_H = 54
BAR_X, BAR_W = 90, 720
TOP_Y = 110
BOT_Y = 300

# Positions along each bar, as fractions of its width
TOP_LONG = (0.10, 0.72)      # the genuinely parallel passage in HP
BOT_LONG = (0.16, 0.80)      # ... and its counterpart in HG
TOP_SHORT = (0.30, 0.40)     # the short repeated passage, one copy
BOT_SHORT_A = (0.36, 0.46)   # its true counterpart
BOT_SHORT_B = (0.62, 0.72)   # a second, coincidental copy

INK = "#1a1a1a"
LONG_FILL = "#dbe7f5"
LONG_EDGE = "#5b7fa6"
SHORT_FILL = "#f5d9a8"
SHORT_EDGE = "#b8802a"
TRUE_LINE = "#2f6b3f"
FALSE_LINE = "#c0392b"


def px(bar_x: int, bar_w: int, frac: float) -> float:
    return bar_x + bar_w * frac


def bar(y: int, label: str) -> list[str]:
    """One text as a horizontal bar, labelled at its right edge (RTL reading).

    Note: no `direction="rtl"` on the text. Hebrew glyphs are already ordered
    right-to-left by the Unicode bidi algorithm, and setting `direction` flips
    what `text-anchor="end"` means — which pushes the label off the canvas.
    """
    return [
        f'<rect x="{BAR_X}" y="{y}" width="{BAR_W}" height="{BAR_H}" '
        f'fill="#ffffff" stroke="{INK}" stroke-width="1.6" rx="3"/>',
        # Hebrew label sits above the bar's right edge, where RTL reading starts.
        f'<text x="{BAR_X + BAR_W}" y="{y - 12}" font-family="{FONT}" font-size="19" '
        f'font-weight="600" fill="{INK}" text-anchor="end">{label}</text>',
    ]


def span(y: int, frac: tuple[float, float], fill: str, edge: str,
         label: str, dash: bool = False, label_at: str = "middle") -> list[str]:
    """A highlighted passage inside a bar, labelled inside it.

    `label_at="right"` tucks the label against the span's right edge, so a long
    span's label does not collide with a shorter span drawn on top of it.
    """
    x0, x1 = px(BAR_X, BAR_W, frac[0]), px(BAR_X, BAR_W, frac[1])
    stroke_dash = ' stroke-dasharray="5 3"' if dash else ""
    if label_at == "right":
        text_x, anchor = x1 - 10, "end"
    elif label_at == "left":
        text_x, anchor = x0 + 10, "start"
    else:
        text_x, anchor = (x0 + x1) / 2, "middle"
    return [
        f'<rect x="{x0:.1f}" y="{y + 6}" width="{x1 - x0:.1f}" height="{BAR_H - 12}" '
        f'fill="{fill}" stroke="{edge}" stroke-width="1.6" rx="2"{stroke_dash}/>',
        f'<text x="{text_x:.1f}" y="{y + BAR_H / 2 + 6:.0f}" font-family="{FONT}" '
        f'font-size="15" fill="{INK}" text-anchor="{anchor}">{label}</text>',
    ]


def connector(top_at: float, bot_at: float, color: str, dashed: bool,
              label: str = "", label_dx: float = 0) -> list[str]:
    """A curve linking a point on the upper bar to a point on the lower bar.

    Takes explicit fractions rather than span midpoints, so the line can leave
    from a clear stretch of a span instead of from under a nested span — where it
    would look like it originates from the nested one.
    """
    tx = px(BAR_X, BAR_W, top_at)
    bx = px(BAR_X, BAR_W, bot_at)
    y0, y1 = TOP_Y + BAR_H, BOT_Y
    dash = ' stroke-dasharray="7 5"' if dashed else ""
    mid = (y0 + y1) / 2
    out = [
        f'<path d="M {tx:.1f} {y0} C {tx:.1f} {mid:.0f}, {bx:.1f} {mid:.0f}, {bx:.1f} {y1}" '
        f'fill="none" stroke="{color}" stroke-width="2.4"{dash}/>',
    ]
    if label:
        lx = (tx + bx) / 2 + label_dx
        out.append(
            f'<text x="{lx:.1f}" y="{mid + 5:.0f}" font-family="{FONT}" font-size="15" '
            f'font-weight="600" fill="{color}" text-anchor="middle" '
            f'paint-order="stroke" stroke="#ffffff" stroke-width="4">{label}</text>'
        )
    return out


def legend(y: int) -> list[str]:
    rows = [
        (TRUE_LINE, False, "ההתאמה האמיתית — הקטע הארוך"),
        (FALSE_LINE, True, "התאמה שגויה — העותק השני של הקטע הקצר"),
    ]
    out = []
    swatch_right = BAR_X + BAR_W
    swatch_left = swatch_right - 46
    for i, (color, dashed, text) in enumerate(rows):
        ly = y + i * 26
        dash = ' stroke-dasharray="7 5"' if dashed else ""
        # RTL legend: swatch on the right, text ending just left of the swatch so
        # the label grows leftward instead of running back through the line.
        out.append(
            f'<line x1="{swatch_right}" y1="{ly}" x2="{swatch_left}" y2="{ly}" '
            f'stroke="{color}" stroke-width="2.4"{dash}/>'
        )
        out.append(
            f'<text x="{swatch_left - 14}" y="{ly + 5}" font-family="{FONT}" '
            f'font-size="15" fill="{INK}" text-anchor="end">{text}</text>'
        )
    return out


def build() -> str:
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="{FONT}">',
        f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
    ]

    parts += bar(TOP_Y, "הלכות פסוקות")
    parts += span(TOP_Y, TOP_LONG, LONG_FILL, LONG_EDGE, "קטע ארוך מקביל", label_at="right")
    parts += span(TOP_Y, TOP_SHORT, SHORT_FILL, SHORT_EDGE, "קטע קצר")

    parts += bar(BOT_Y, "הלכות גדולות")
    # Labelled at its left edge: the repeat span occupies the right stretch.
    parts += span(BOT_Y, BOT_LONG, LONG_FILL, LONG_EDGE, "קטע ארוך מקביל", label_at="left")
    parts += span(BOT_Y, BOT_SHORT_A, SHORT_FILL, SHORT_EDGE, "קטע קצר")
    parts += span(BOT_Y, BOT_SHORT_B, SHORT_FILL, SHORT_EDGE, "קטע קצר (חזרה)", dash=True)

    # The true correspondence, drawn from clear stretches of the long spans.
    parts += connector(0.56, 0.52, TRUE_LINE, False)
    # ... and the spurious one the repetition invites: the short passage in HP
    # latched onto the second copy in HG.
    mid_short_top = (TOP_SHORT[0] + TOP_SHORT[1]) / 2
    mid_repeat = (BOT_SHORT_B[0] + BOT_SHORT_B[1]) / 2
    parts += connector(mid_short_top, mid_repeat, FALSE_LINE, True)

    parts += legend(H - 62)
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, required=True, help="output .svg path")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build(), encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
