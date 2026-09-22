# Right-to-left text in the Quarto visual editor

The Quarto VS Code extension's visual editor uses an **LTR base direction regardless
of the document's `dir: rtl`**. Hebrew paragraphs come out left-aligned with sentence
punctuation on the wrong side. The rendered preview is correct; only the editing
surface is wrong.

This is not a configuration problem. Checked against the installed extension
(`quarto.quarto-1.135.0`):

- 41 contributed settings, **none** relating to text direction
- bundled `assets/www/editor/style.css` contains **zero** `rtl` rules — every
  `direction:` in it is flexbox (`column`/`row`)
- the only `dir` handling in `index.js` is third-party library code (a positioning
  helper reading `documentElement`)

The editor is ProseMirror in a webview (`assets/www/editor/{index.js,style.css}`),
so the fix is CSS-level. Source lives in
[quarto-dev/quarto](https://github.com/quarto-dev/quarto) at `packages/editor/`
(Yarn + Turbo monorepo, `yarn && yarn dev-vscode`; `packages/editor` is AGPL-3.0).

## What was measured

`bidi-harness.html` renders six candidate treatments over the same mixed
Hebrew/English content. Open it in a browser, or see `bidi-candidates.png`.

| | Treatment | Result |
|---|---|---|
| A | baseline | broken — Hebrew left-aligned, punctuation misplaced |
| B | `.ProseMirror { direction: rtl }` | Hebrew correct throughout; English-only paragraphs become right-aligned, which is correct bidi inside an RTL document **and matches the rendered HTML** |
| C | blocks `{ unicode-bidi: plaintext }` | per-paragraph automatic direction, alignment resolves correctly |
| D | C + `text-align: start` | **identical to C** — the extra rule is redundant |
| E | container `rtl` + blocks `plaintext` | same as C |
| F | `dir="auto"` on each block | **pixel-identical to C** |

Two conclusions that matter:

1. **`unicode-bidi: plaintext` in CSS is exactly equivalent to `dir="auto"` per
   block** (C ≡ F). A JavaScript plugin that sets `dir="auto"` — the approach
   [tiptap-text-direction](https://github.com/amirhhashemi/tiptap-text-direction)
   takes — buys nothing over a stylesheet rule here. That makes the patch far
   smaller than it first appears.
2. **First-character detection is the wrong default for this project's prose.**
   Paragraphs opening with a Latin word resolve LTR, and `MSM מוצא קטעים...` /
   `passim לא נתקל...` are routine here. The flaw is inherent to the heuristic, so
   `dir="auto"` shares it.

So **B is the better fix**: derive the base direction from the document's `dir` and
let the Unicode bidi algorithm order embedded Latin runs. It also makes the editor
agree with the output, which is the point of a WYSIWYM editor.

Note that `direction: auto` does **not** exist — the CSS `direction` property takes
only `ltr`/`rtl`. Automatic detection is the HTML `dir="auto"` attribute, or
`unicode-bidi: plaintext` in CSS.

## WARNING: visual mode destroys table cross-reference labels

Found while testing the spike on `update_2026-08-12.qmd`. Editing in visual mode and
saving rewrote the source, and **both table labels were silently stripped**:

```diff
-: Size of the filtered match sets (span >= 20) {#tbl-filtered}
+: Size of the filtered match sets (span \>= 20)
```

`{#tbl-filtered}` and `{#tbl-coverage}` were both lost. The 11 figure labels
(`{#fig-N}`) survived, so this is specific to the `: caption {#tbl-x}` table syntax.
`>` also got escaped to `\>`.

This is worse than the Word problem that motivated the move to Quarto: there, a stale
number was visible in the output. Here the label vanishes from the *source*, and if
nothing references it yet, nothing warns. A later `@tbl-filtered` simply fails to
resolve, with no clue that a label used to exist.

Round-tripping also renormalises unrelated markup — `{width=100%}` became
`{width="100%"}` on all 11 figures — so the diff after a visual-mode session is
large, which makes the real loss easy to miss in review.

**Until this is understood: after any visual-mode session, run `git diff` and check
that `{#tbl-...}` labels are intact.** Keeping the document in git is what made this
detectable at all.

Worth reporting upstream separately from the RTL request; it is a data-loss bug, not
a display preference, and it has nothing to do with Hebrew. The report is written up
in `upstream/quarto-issue-visual-editor-tbl-label.md`.

## Installing it

`install.py` appends `spike.css` to the stylesheet the extension ships:

    <extensions>/quarto.quarto-<version>/assets/www/editor/style.css

It finds the newest installed Quarto extension by itself, keeps the untouched
stylesheet beside it as `style.css.orig`, and does nothing if the rules are
already there.

```bash
python visual-editor-rtl/install.py            # install
python visual-editor-rtl/install.py --check    # report, change nothing
python visual-editor-rtl/install.py --remove   # restore the original
```

Then in VS Code run **Developer: Reload Window**, open a `.qmd`, and switch to
visual mode (`Ctrl+Shift+F4`).

**Every extension update discards this.** Each version installs into a folder of
its own, which starts as a clean copy, so run `install.py` again after each
update. Nothing warns you; the editor simply goes back to left-to-right.

Option 1 in `spike.css` is the active one. To compare with Option 2, swap which
one is commented out, run `install.py --remove` and then `install.py` again, and
reload the window.

Verified against `quarto.quarto-1.138.0` (September 2026); first measured on
1.135.0.

## If this becomes a feature request

The ask is small and concrete: *apply the document's `dir` to the ProseMirror
container.* Worth proposing a setting
(`quarto.visualEditor.textDirection: auto | ltr | rtl`) rather than only
auto-detection, since deriving `dir` from YAML means parsing frontmatter out of the
Pandoc AST and reacting to edits — much more work than the CSS itself, and the part a
maintainer would have opinions about.

One design trap to avoid: implement per-block direction as ProseMirror
**decorations**, never as a schema attribute. An attribute risks serializing `dir`
into the `.qmd`, silently rewriting source files.
