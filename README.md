# QuartoTools

Tools for writing Hebrew, right-to-left documents in [Quarto](https://quarto.org),
collected from the trial that moved a set of research updates off Word. They are kept
here rather than inside one document repository because none of them are specific to a
document.

Four separate things live here:

| Folder | What it does |
|---|---|
| the root, `scripts/`, `filters/`, `templates/` | rendering a `.qmd` to Word and HTML with Hebrew set correctly |
| `visual-editor-rtl/` | making the VS Code visual editor lay text out right to left |
| `redline/` | word-level change reports for Markdown, readable by someone who never sees `git diff` |
| `upstream/` | bug reports and a patch aimed at the Quarto and pandoc maintainers |

Everything was tested on Windows with Quarto 1.10, pandoc 3.9 and Python 3.14.

`hebrew-in-quarto.md` is the long form: what was measured, which Quarto and pandoc
behaviours bite in Hebrew, and why each tool here exists. Read this file for how to use
the tools and that one for why they work the way they do.

## Rendering

```bash
python <path to this repo>/render.py path/to/document.qmd
python <path to this repo>/render.py path/to/document.qmd --to docx
```

`render.py` does two things `quarto render` alone cannot. It rasterizes the SVG figures
in the `media` folder next to the document, because pandoc cannot embed SVG in a `.docx`,
and it runs Quarto from the document's project root -- the nearest folder at or above the
document holding a `_quarto.yml` -- so the project's settings apply.

| Path | What it is |
|---|---|
| `render.py` | render plus SVG rasterization; use this instead of bare `quarto render` |
| `_quarto.yml` | the project defaults to copy into a document repository, and what makes `example/` renderable |
| `templates/hebrew.docx` | the Word reference document; all `.docx` typography lives here |
| `rtl-fixes.css` | the right-to-left touch-ups Quarto's own stylesheets miss, plus the David font stack |
| `filters/svg-to-png.lua` | sends Word output to the rasterized copy of each SVG, while HTML keeps the vector |
| `scripts/rasterize_svg.py` | SVG to PNG through headless Edge, so no `rsvg-convert` is needed |
| | it renders at 2x and records 192 dpi in the PNG, so the figure keeps its size and gains detail |
| | the raster of `figure.svg` is `figure.svg.png`, so `*.svg.png` is the only ignore rule rasters need |
| `filters/auto-direction.lua` | gives each paragraph and table its own direction, during the render |
| `filters/straight-header-quotes.lua` | keeps `"` and `'` in the title, subtitle and author straight, as `from: markdown-smart` does for the body |
| `scripts/set_docx_direction.py` | sets the direction of the tables and captions the filter cannot reach, after the render |
| `filters/wrap-figure.lua` | floats a figure in a `.wrap-left` / `.wrap-right` div beside the text, caption kept under it; `.full-page` spreads a picture over a whole page instead, for a cover |
| `scripts/wrap_docx_figures.py` | in Word, moves each such figure and its caption into a floating text box, after the render |
| `scripts/compress_docx_images.py` | writes `<name>.compressed.docx`, its pictures shrunk as Word's Compress Pictures does |
| | scales each to 150 ppi at its shown size, deletes cropped-away parts, turns photo PNGs into JPEG |
| `scripts/set_docx_font.py` | escape hatch: forces one font onto a rendered `.docx`, flattening every style |
| `scripts/docx_to_qmd.py` | Word to Quarto converter, with the Hebrew cleanups a plain pandoc run leaves behind |
| `example/smoke-test.qmd` | one page for checking that all of this still works after a change |
| `example/slides_demo.qmd` | a Hebrew lecture deck, for `revealjs` |
| `scripts/generate_repetition_schematic.py` | draws a figure as SVG, as an example of the script-generated figure convention |

### Editing the template: styles, never the sample text

The template's body is a page of sample paragraphs, one per style. Formatting applied to
that sample text does nothing: pandoc copies **style definitions** out of a reference
document and ignores its body entirely. A page break applied to the words "Heading 1" on
that page is invisible in every rendered document, with no warning.

Always go through **Styles pane -> right-click the style -> Modify -> Format -> ...**. Two
settings that live there now: `Heading 1` starts a new page (Format -> Paragraph -> Line and
Page Breaks -> Page break before), and `Image Caption` leaves 12 pt after it.

### Spacing around a figure caption

The gap below a figure caption is the `Image Caption` style's space-after, in
`templates/hebrew.docx`. It is 12 pt; the `Caption` style it inherits from gives only 6 pt,
which leaves a figure and the paragraph after it looking joined. To change it, open the
template in Word and use **Styles pane -> Image Caption -> Modify -> Format -> Paragraph ->
Spacing After**.

Do not try to do this from the document instead. A blank line in the `.qmd` does nothing --
markdown collapses it -- and the space *above* the caption is direct formatting that pandoc
writes on the paragraph itself, which no style can override. The `Table Caption` style is
deliberately left alone, since a table caption sits above its table and space-after would
push it away from what it describes.

### Two settings that are the reason the template exists

**`lang` must carry the region: `he-IL`, never `he`.** Pandoc writes the document's `lang`
into the `.docx` as `<w:lang w:bidi="...">`, and Word only honours a full locale there.
Given a bare `he` it throws away the reference document's Hebrew font and falls back to
Times New Roman, even though the file plainly says David. Nothing warns you. The full
measurement is in `upstream/pandoc-issue-lang-bidi.md`.

**Direction is decided per paragraph and per table, automatically.** A document that sets
`dir: rtl` would otherwise lay everything out right to left, so an English sentence comes
out right-aligned with its full stop on the left and a table of English terms comes out
with its first column on the right. `filters/auto-direction.lua` applies the Unicode rule
instead: each paragraph and each table takes its direction from its own first strong
character, the same rule a browser applies for `dir="auto"`. Nothing has to be marked up.

The rule has one known failure, and it is common in Hebrew academic prose: a Hebrew
sentence that opens with a Latin term reads as left to right.

```markdown
MSM מוצא קטעים ארוכים יותר מאשר האלגוריתם הקודם.     <- comes out left to right

::: {dir="rtl"}
MSM מוצא קטעים ארוכים יותר מאשר האלגוריתם הקודם.     <- correct
:::
```

A div that states a direction wins outright, and nothing inside it is examined, so a hand
override is never second-guessed. It works the other way too: `::: {dir="ltr"}` forces a
passage left to right.

One thing the filter deliberately does not touch: anything Quarto has wrapped in a float,
which is what it does to a figure or a table that carries a label. Those carry
`__quarto_custom` attributes and are taken apart again later, and anything inserted inside
one is lost with it -- wrapping a caption cost the caption itself, which vanished from Word
while still showing in HTML. A labelled table still gets its direction, from a marker placed
before the float rather than inside it. A caption gets its direction afterwards, from
`scripts/set_docx_direction.py`, which applies the same first-strong-character rule to the
rendered file -- so `figure 1: The matches between HP and HG.` reads left to right inside a
Hebrew document, while `תרשים 1: ...` stays right to left.

How that direction reaches each output differs, and the table case is the awkward one.
A paragraph in Word becomes `w:bidi`, and in HTML `rtl-fixes.css` sets
`unicode-bidi: plaintext`, which is the same rule expressed natively. A table in HTML gets
a `dir` attribute. A table in Word needs `w:bidiVisual` on the table itself, which nothing
in the pandoc AST can set -- so the filter leaves a comment before the table and
`scripts/set_docx_direction.py` turns it into the real element afterwards. `render.py`
runs that script, so this is invisible in normal use.

Two findings behind this, both measured against Word itself:

* `w:bidiVisual` on the **`Table` style** does nothing at all -- Word ignores it there.
  Worse, it then cancels the same setting on the table itself, so a template carrying it
  stops the working fix from working. Keep it out of `templates/hebrew.docx`.
* `w:bidiVisual` must sit immediately after `w:tblStyle` inside `w:tblPr`. Put it anywhere
  else and Word silently drops it when the file is opened.

### A smaller copy to send around

A rendered `.docx` carries every photo at the resolution it was taken at, so a document
with a few photos easily passes 10 MB. To send it to people for comments, make a copy with
the pictures shrunk, and keep the original for print:

```bash
python scripts/compress_docx_images.py path/to/document.docx              # 150 ppi
python scripts/compress_docx_images.py path/to/document.docx --ppi 220    # sharper
```

It writes `document.compressed.docx` beside the original, and does what Word's **Picture
Format -> Compress Pictures** does to every picture at once: each is scaled down to the
given resolution at the size it is shown on the page, and a picture cropped in Word has its
hidden parts deleted. It also stores a photo that came as PNG as JPEG instead, which is most
of the saving for an AI-made or screenshot photo; `--keep-png` turns that off. A booklet of
ten pictures went from 11.2 MB to 0.9 MB, with no difference visible on the page. It needs
Pillow (`pip install pillow`).

### Checking the toolchain

```bash
python render.py example/smoke-test.qmd --to docx
```

`example/smoke-test.qmd` deliberately carries no `lang` or `dir` of its own, so it also
checks that the project file supplies them. Open the Word file and confirm three things:
the Hebrew body text is David, the Latin terms inside the Hebrew paragraph do not break
the line, and the figure appears.

### Slides

Use `revealjs`, not `pptx`. Pandoc does not carry `dir: rtl` into PowerPoint, so bullets
sit on the left and clause order visibly scrambles. The same deck is correct in every
respect as `revealjs`. `example/slides_demo.qmd` is the deck this was measured on.

```bash
quarto render example/slides_demo.qmd --to revealjs
```

### Using it from a document repository

Copy `_quarto.yml` to the repository root and point its paths at this checkout -- as
`../QuartoTools/templates/hebrew.docx` if the two sit side by side. Put documents in a
folder of their own with their figures in a `media` subfolder beside them.

## Right-to-left in the visual editor

The visual editor lays text out left to right whatever the document's `dir` says, and
there is no setting for it. `visual-editor-rtl/install.py` appends the missing CSS rules
to the stylesheet the extension ships:

```bash
python visual-editor-rtl/install.py            # install
python visual-editor-rtl/install.py --check    # report, change nothing
python visual-editor-rtl/install.py --remove   # restore the original
```

Then run **Developer: Reload Window** in VS Code.

**Every extension update discards this**, because each version installs into a folder of
its own that starts as a clean copy. Run `install.py` again after each update.

`visual-editor-rtl/README.md` explains which rules were chosen and why, and shows the six
treatments that were measured against each other.

### Warning: visual mode strips table cross-reference labels

Editing a document in visual mode and saving rewrites the source, and `{#tbl-...}` labels
are silently lost -- the label vanishes from the `.qmd` itself, so a later `@tbl-...`
simply fails to resolve with no clue that a label ever existed. Figure labels survive.
**After any visual-mode session, run `git diff` and check the table labels are intact.**
Written up in `upstream/quarto-issue-visual-editor-tbl-label.md`.

## Change reports

`git diff` is line-based, which suits code and the people who write it, but not a reader
of prose: a one-word edit shows as a whole paragraph removed and re-added, in a terminal.
Someone reviewing a document wants what Word's track changes shows them.
`redline/md_redline.py` produces that as a single HTML page -- deleted words red and struck
through, inserted words green and underlined, inside the running paragraph. Each paragraph
also takes its own direction (`dir="auto"`), so Hebrew reads right to left and English left
to right, which `git diff` gets wrong as well. It needs only the Python standard library, plus `git` for the history mode.

```bash
python redline/md_redline.py compare old.md new.md
python redline/md_redline.py history path/to/repo
python redline/md_redline.py history path/to/repo --since "2 weeks ago" --paths life-story.md
```

Every report is named `*.changes.html`, so one line in a document repository's
`.gitignore` keeps them all out of git without touching any other HTML:

```gitignore
*.changes.html
```

`compare` writes `new.changes.html` beside `new.md`. `history` writes into the repository:
`life-story.changes.html` when `--paths` names a single file, including the same file under
an old and a new name (`--paths life-story.md life-story.qmd`, to follow a rename), and
`<repository name>.changes.html` otherwise. `-o` names the file yourself.

`compare` diffs two files. `history` walks a repository's log and writes one report for
every commit that touched the selected files: a summary table at the top (date, commit
message, author, words deleted and inserted), then one collapsible section per commit with
the changes in each file. Only changed paragraphs are shown, with a little grey context
around them. A paragraph written over several lines -- one sentence per line, say, as the
visual editor writes with `editor: markdown: wrap: sentence` -- is shown as the one
paragraph it renders as, and a commit that only rewraps lines reports no change.

| Option (`history`) | What it does |
|---|---|
| `--paths` | which files to report on, as git pathspecs; default `*.md` |
| `--since` | only commits after a date, e.g. `2026-09-01` or `"2 weeks ago"` |
| `--range` | only a commit range, e.g. `v1..HEAD` or `HEAD~10..HEAD` |
| `--context N` | unchanged paragraphs shown around each change; default 1 (also for `compare`) |
| `--oldest-first` | list commits in chronological order; default is newest first |
| `--expand` | open every commit's section, instead of starting them collapsed |

Word counts are approximate -- a word is a run of letters or digits -- and a commit with
several parents is compared against its first parent only.

## Upstream

| File | What it is |
|---|---|
| `upstream/pandoc-issue-lang-bidi.md` | the `lang: he` font bug, measured |
| `upstream/quarto-issue-visual-editor-tbl-label.md` | the table label data loss above |
| `upstream/quarto-patch-table-attr.patch` | a proposed fix for it |
| `upstream/quarto-verify-table-attr.ts` | what the patch was checked with |
| `upstream/tbl-label-repro.qmd` | the smallest document that reproduces the table label loss |

## Where these came from

The `TextReuse` repository, which is where the trial ran. It keeps its own working copy
under `quarto/`; the two can drift apart, so treat this repository as the one to develop
in. The trial document itself and its figures stay in `TextReuse`, on the
`worktree-quarto-test` branch.
