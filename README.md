# QuartoTools

Tools for writing Hebrew, right-to-left documents in [Quarto](https://quarto.org),
collected from the trial that moved a set of research updates off Word. They are kept
here rather than inside one document repository because none of them are specific to a
document.

Three separate things live here:

| Folder | What it does |
|---|---|
| the root, `scripts/`, `filters/`, `templates/` | rendering a `.qmd` to Word and HTML with Hebrew set correctly |
| `visual-editor-rtl/` | making the VS Code visual editor lay text out right to left |
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
| `filters/rtl-tables.lua` | marks the tables inside a `dir="rtl"` div, during the render |
| `scripts/set_docx_rtl_tables.py` | lays those marked tables out right to left, after the render |
| `scripts/set_docx_font.py` | escape hatch: forces one font onto a rendered `.docx`, flattening every style |
| `scripts/docx_to_qmd.py` | Word to Quarto converter, with the Hebrew cleanups a plain pandoc run leaves behind |
| `example/smoke-test.qmd` | one page for checking that all of this still works after a change |
| `example/slides_demo.qmd` | a Hebrew lecture deck, for `revealjs` |
| `scripts/generate_repetition_schematic.py` | draws a figure as SVG, as an example of the script-generated figure convention |

### Two settings that are the reason the template exists

**`lang` must carry the region: `he-IL`, never `he`.** Pandoc writes the document's `lang`
into the `.docx` as `<w:lang w:bidi="...">`, and Word only honours a full locale there.
Given a bare `he` it throws away the reference document's Hebrew font and falls back to
Times New Roman, even though the file plainly says David. Nothing warns you. The full
measurement is in `upstream/pandoc-issue-lang-bidi.md`.

**Tables are a separate problem from text.** `dir: rtl` reaches a table's cell paragraphs
but not the table itself, and Word lays a table out left to right unless the table carries
`w:bidiVisual`. Pandoc never writes that element and no filter can add it, so wrap the
table in a right-to-left div:

```markdown
::: {dir="rtl"}
| עמודה  |    ערך |
|--------|-------:|
| התאמות |    233 |
:::
```

`filters/rtl-tables.lua` marks those tables during the render and
`scripts/set_docx_rtl_tables.py` sets the layout direction on each marked table afterwards.
`render.py` runs both, so a document only has to use the div. Tables outside such a div are
left alone, which is what a table of English terms wants.

Two findings behind this, both measured against Word itself:

* `w:bidiVisual` on the **`Table` style** does nothing at all -- Word ignores it there.
  Worse, it then cancels the same setting on the table itself, so a template carrying it
  stops the working fix from working. Keep it out of `templates/hebrew.docx`.
* `w:bidiVisual` must sit immediately after `w:tblStyle` inside `w:tblPr`. Put it anywhere
  else and Word silently drops it when the file is opened.

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
