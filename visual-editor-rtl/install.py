#!/usr/bin/env python3
"""Add the right-to-left rules to the Quarto visual editor's stylesheet.

The visual editor is a ProseMirror surface in a VS Code webview. It lays text
out left to right whatever the document's `dir` says, so Hebrew paragraphs come
out left-aligned with the punctuation on the wrong side. The rendered preview is
correct; only the editing surface is wrong. There is no setting for this, so the
fix is to append `spike.css` to the stylesheet the extension ships:

    <extensions>/quarto.quarto-<version>/assets/www/editor/style.css

Each extension update installs into a folder of its own and therefore starts
clean, so this has to be run again after every update. Run it with no arguments
to install, then run "Developer: Reload Window" in VS Code.

    python visual-editor-rtl/install.py            # install, or report no-op
    python visual-editor-rtl/install.py --check    # report, change nothing
    python visual-editor-rtl/install.py --remove   # restore the original

A copy of the untouched stylesheet is kept beside it as `style.css.orig`, which
is what --remove restores.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPIKE = HERE / 'spike.css'
MARKER = 'RTL SPIKE'          # appears in spike.css; how an applied copy is recognised


def read(path: Path) -> str:
    """Read without newline translation, so a rewrite is byte for byte."""
    with open(path, encoding='utf-8', newline='') as handle:
        return handle.read()


def write(path: Path, text: str) -> None:
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        handle.write(text)

# Where the various VS Code builds keep their extensions.
EXTENSION_ROOTS = [
    Path.home() / '.vscode' / 'extensions',
    Path.home() / '.vscode-insiders' / 'extensions',
    Path.home() / '.vscode-server' / 'extensions',
    Path.home() / '.cursor' / 'extensions',
    Path.home() / '.windsurf' / 'extensions',
]


def version_key(folder: Path) -> tuple[int, ...]:
    """Sort key from the version in a folder name like quarto.quarto-1.138.0."""
    digits = re.findall(r'\d+', folder.name.split('-', 1)[-1])
    return tuple(int(d) for d in digits)


def stylesheets() -> list[Path]:
    """The style.css of the newest Quarto extension in each extensions folder."""
    found = []
    for root in EXTENSION_ROOTS:
        if not root.is_dir():
            continue
        installs = sorted((p for p in root.glob('quarto.quarto-*') if p.is_dir()),
                          key=version_key)
        if not installs:
            continue
        css = installs[-1] / 'assets' / 'www' / 'editor' / 'style.css'
        if css.is_file():
            found.append(css)
        else:
            print(f'{installs[-1].name}: no editor stylesheet at {css}, skipping')
    return found


def install(css: Path) -> bool:
    """Append the rules. Returns True if the file changed."""
    text = read(css)
    if MARKER in text:
        print(f'{css.parent.parent.parent.parent.name}: already applied, nothing to do')
        return False
    # No marker means this is the stylesheet as shipped, so it is safe to
    # (re)write the backup from it.
    write(css.with_suffix('.css.orig'), text)
    write(css, text + '\n' + read(SPIKE))
    print(f'{css.parent.parent.parent.parent.name}: applied '
          f'(original kept as {css.name}.orig)')
    return True


def remove(css: Path) -> bool:
    """Restore the shipped stylesheet. Returns True if the file changed."""
    backup = css.with_suffix('.css.orig')
    if MARKER not in read(css):
        print(f'{css.parent.parent.parent.parent.name}: not applied, nothing to remove')
        return False
    if not backup.is_file():
        sys.exit(f'{backup} is missing; reinstall the extension to restore it')
    write(css, read(backup))
    backup.unlink()
    print(f'{css.parent.parent.parent.parent.name}: removed')
    return True


def check(css: Path) -> bool:
    applied = MARKER in read(css)
    version = css.parent.parent.parent.parent.name
    print(f'{version}: {"applied" if applied else "NOT applied"}')
    return applied


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--check', action='store_true',
                        help='report whether the rules are in place, change nothing')
    action.add_argument('--remove', action='store_true',
                        help='restore the stylesheet the extension shipped')
    args = parser.parse_args()

    if not SPIKE.is_file():
        sys.exit(f'no such file: {SPIKE}')

    targets = stylesheets()
    if not targets:
        sys.exit('no Quarto extension found; is it installed?')

    changed = False
    for css in targets:
        if args.check:
            check(css)
        elif args.remove:
            changed |= remove(css)
        else:
            changed |= install(css)

    if changed:
        print('\nNow run "Developer: Reload Window" in VS Code.')


if __name__ == '__main__':
    main()
