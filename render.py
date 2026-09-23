#!/usr/bin/env python3
"""Render a .qmd, doing the two things `quarto render` alone cannot.

1. Rasterizes the SVG figures beside the document, because pandoc cannot embed
   SVG in .docx. Figures live in a `media` folder next to the .qmd.
2. Optionally forces a font onto the rendered .docx.

Word typography comes from a reference document, normally `templates/hebrew.docx`
here, which the document's own `_quarto.yml` names. `--font` overrides the
template and flattens every style to one face; use it only if the template alone
falls short.

Quarto runs from the document's project root -- the nearest folder at or above
the document that holds a `_quarto.yml` -- so the project's settings apply. With
no `_quarto.yml` anywhere above it, the document's own folder is used.

Usage, from anywhere:

    python <path to QuartoTools>/render.py path/to/document.qmd
    python <path to QuartoTools>/render.py path/to/document.qmd --to docx
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent      # the QuartoTools checkout


def project_root(qmd: Path) -> Path:
    """The nearest folder at or above `qmd` holding a `_quarto.yml`."""
    for folder in [qmd.parent, *qmd.parent.parents]:
        if (folder / '_quarto.yml').is_file() or (folder / '_quarto.yaml').is_file():
            return folder
    return qmd.parent


def run(cmd: list[str], cwd: Path) -> None:
    """Run a command, failing loudly."""
    printable = ' '.join(cmd)
    print(f'$ {printable}')
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        sys.exit(f'failed ({result.returncode}): {printable}')


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('qmd', help='document to render')
    parser.add_argument('--to', default=None, help='a single output format (default: all)')
    parser.add_argument('--font', default=None,
                        help='force this font onto the .docx after rendering; '
                             'overrides the reference document')
    args = parser.parse_args()

    qmd = Path(args.qmd).resolve()
    if not qmd.is_file():
        sys.exit(f'no such document: {qmd}')

    # Quarto is installed machine-wide but may not be on PATH in every shell.
    quarto = shutil.which('quarto') or r'C:\Program Files\Quarto\bin\quarto.exe'
    if not shutil.which('quarto') and not Path(quarto).exists():
        sys.exit('quarto not found on PATH')

    # Figures belong to the document, not to this script.
    media = qmd.parent / 'media'
    if media.is_dir():
        run([sys.executable, str(HERE / 'scripts' / 'rasterize_svg.py'),
             '--all', str(media)], cwd=qmd.parent)
    else:
        print(f'no media directory at {media}, skipping rasterization')

    root = project_root(qmd)
    print(f'project root: {root}')
    render = [quarto, 'render', str(qmd.relative_to(root))]
    if args.to:
        render += ['--to', args.to]
    run(render, cwd=root)

    # Tables marked by filters/auto-direction.lua still need their layout direction
    # set, which only the rendered file can carry.
    run([sys.executable, str(HERE / 'scripts' / 'set_docx_rtl_tables.py'),
         str(qmd.with_suffix('.docx')), '--if-exists'], cwd=root)

    if args.font:
        run([sys.executable, str(HERE / 'scripts' / 'set_docx_font.py'),
             str(qmd.with_suffix('.docx')), '--font', args.font, '--if-exists'],
            cwd=root)


if __name__ == '__main__':
    main()
