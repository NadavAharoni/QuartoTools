#!/usr/bin/env python3
"""Rasterize SVG figures to PNG so Word output can embed them.

Pandoc cannot place an SVG into a .docx; it shells out to `rsvg-convert`, which
is not packaged for Windows. This script uses headless Edge instead — already the
project's way of rendering SVG (see CLAUDE.md) and present on every Windows box.

Pair it with `filters/svg-to-png.lua`, which points docx output at the PNG while
HTML keeps the vector original.

The raster of `figure.svg` is written beside it as `figure.svg.png`, never as
`figure.png`. The double extension marks it as generated, so one ignore rule
(`*.svg.png`) keeps every raster out of git while a hand-made PNG such as a
screenshot is tracked like any other file, and the raster can never overwrite
a hand-made `figure.png` that happens to share the figure's name.

Usage:
    python rasterize_svg.py media/media/image4.svg
    python rasterize_svg.py --all media          # every .svg under media/
"""

from __future__ import annotations

import argparse
import atexit
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path

EDGE_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)

# Pull width/height off the root <svg> so the PNG keeps the figure's aspect ratio.
LENGTH = re.compile(r'\b(width|height)\s*=\s*"([\d.]+)(px|pt|in|cm|mm)?"')
VIEWBOX = re.compile(r'viewBox\s*=\s*"[\d.\-\s]*?([\d.]+)[\s,]+([\d.]+)"')
# An absent unit means CSS pixels; re groups yield "" rather than None.
TO_PX = {"": 1.0, "px": 1.0, "pt": 96 / 72, "in": 96.0, "cm": 96 / 2.54, "mm": 96 / 25.4}


def find_edge() -> Path:
    for path in EDGE_CANDIDATES:
        if path.exists():
            return path
    sys.exit("Microsoft Edge not found; install it or add another rasterizer")


def svg_size(svg: Path) -> tuple[int, int]:
    """Best-effort intrinsic size of an SVG, in CSS pixels."""
    head = svg.read_text(encoding="utf-8", errors="replace")[:4000]
    root = head[head.find("<svg"):head.find(">", head.find("<svg")) + 1]

    dims: dict[str, float] = {}
    for name, value, unit in LENGTH.findall(root):
        dims[name] = float(value) * TO_PX[unit]
    if "width" in dims and "height" in dims:
        return round(dims["width"]), round(dims["height"])

    box = VIEWBOX.search(root)
    if box:
        return round(float(box.group(1))), round(float(box.group(2)))
    return 1000, 1000


def set_png_dpi(png: Path, dpi: float) -> None:
    """Record the raster's real resolution in the PNG itself.

    Rendering at 2x gives a print-quality image with twice as many pixels. A
    reader that assumes 96 dpi, pandoc among them, then places the figure at
    twice its intended width. A pHYs chunk states the true resolution, so the
    figure keeps its size on the page and gains only detail.
    """
    data = png.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        sys.exit(f'{png} is not a PNG')

    # Walk the chunks, dropping any pHYs already there; IHDR is always first.
    pos, out, ihdr_end = 8, [data[:8]], None
    while pos < len(data):
        length = struct.unpack('>I', data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        chunk = data[pos:pos + 12 + length]
        pos += 12 + length
        if kind == b'pHYs':
            continue
        out.append(chunk)
        if kind == b'IHDR':
            ihdr_end = len(out)

    per_metre = int(round(dpi / 0.0254))
    body = b'pHYs' + struct.pack('>IIB', per_metre, per_metre, 1)
    phys = struct.pack('>I', 9) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)
    out.insert(ihdr_end, phys)
    png.write_bytes(b''.join(out))


_profile: Path | None = None


def profile_dir() -> Path:
    """A private browser profile, made once and thrown away at exit.

    Without it, launching Edge while a browser is already open can hand the
    command to that running instance, which exits 0 and does nothing: no
    screenshot, no error, no output at all. A profile of its own forces a real
    browser to start.
    """
    global _profile
    if _profile is None:
        _profile = Path(tempfile.mkdtemp(prefix="rasterize-svg-"))
        atexit.register(shutil.rmtree, _profile, ignore_errors=True)
    return _profile


def screenshot(svg: Path, out: Path, edge: Path, scale: float,
               width: int, height: int) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [
            str(edge),
            "--headless",
            "--disable-gpu",
            f"--user-data-dir={profile_dir()}",
            "--no-first-run",
            "--no-default-browser-check",
            f"--screenshot={out.resolve()}",
            # The window is sized in CSS pixels; the scale factor multiplies the
            # captured raster. Scaling both would leave the figure in one corner.
            f"--window-size={width},{height}",
            f"--force-device-scale-factor={scale}",
            "--default-background-color=FFFFFFFF",
            "--hide-scrollbars",
            svg.resolve().as_uri(),
        ],
        capture_output=True, text=True, errors="replace",
    )
    # Edge can return before the file lands, so give it a moment rather than
    # calling a slow write a failure.
    for _ in range(20):
        if out.exists():
            break
        time.sleep(0.25)
    return result


def rasterize(svg: Path, edge: Path, scale: float, attempts: int = 2) -> Path:
    width, height = svg_size(svg)
    out = svg.with_name(svg.name + ".png")      # figure.svg -> figure.svg.png

    # Headless Edge fails now and then for reasons that have nothing to do with
    # the file -- a profile still locked by a previous run, a browser update in
    # progress. One retry clears those; anything that survives it is real, and
    # the message below says what Edge actually complained about, because a bare
    # "failed to rasterize" leaves you with nowhere to start.
    for attempt in range(1, attempts + 1):
        # Clear any earlier raster first. `out.exists()` is how a run is judged
        # to have worked, and a leftover PNG would answer for one that did not:
        # the stale file would be kept, and would keep whatever size it recorded.
        out.unlink(missing_ok=True)
        result = screenshot(svg, out, edge, scale, width, height)
        if out.exists():
            break
        if attempt < attempts:
            print(f"retrying {svg.name}; Edge wrote no PNG "
                  f"(exit {result.returncode})")
    else:
        noise = "Every renderer should have at least one task"   # harmless, always there
        complaint = [line for line in result.stderr.splitlines()
                     if line.strip() and noise not in line]
        detail = ("\n  ").join(complaint[-5:]) or "(Edge said nothing)"
        sys.exit(f"failed to rasterize {svg}\n"
                 f"  Edge exited {result.returncode} after {attempts} attempts\n"
                 f"  {detail}")

    dpi = 96.0 * scale
    set_png_dpi(out, dpi)
    print(f"{svg.name} ({width}x{height}) -> {out.name} @ {scale}x, {dpi:g} dpi")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help=".svg files, or a directory with --all")
    parser.add_argument("--all", action="store_true", help="treat paths as directories to search")
    parser.add_argument("--scale", type=float, default=2.0,
                        help="device scale factor; 2 gives print-quality raster (default: 2)")
    args = parser.parse_args()

    edge = find_edge()
    targets: list[Path] = []
    for path in args.paths:
        targets.extend(sorted(path.rglob("*.svg")) if args.all else [path])

    if not targets:
        print("no SVG files found")
        return
    for svg in targets:
        rasterize(svg, edge, args.scale)


if __name__ == "__main__":
    main()
