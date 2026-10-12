# Hebrew documents, figures, and slides in Quarto

Everything learned while testing Quarto as a replacement for writing updates in Word.
The test ran on a real document in the `TextReuse` repository: `2026-08-12 עדכון.docx`
(12 pages, 13 figures, 2 tables, Hebrew with embedded English terms). That document
stays there; what the trial produced is the toolchain in this repository.

Read `README.md` first for how to use the tools. This file is the reasoning behind
them, and the record of what was measured.

**Verdict: adopt it for documents. Do not use it for PowerPoint.**

| Output | Hebrew / RTL | Verdict |
|---|---|---|
| `html` | correct | excellent — best authoring feedback loop |
| `docx` → Word → PDF | correct | very good; the recommended path for advisor-facing PDFs |
| `revealjs` slides | correct | excellent for teaching material |
| `pptx` | **broken** | unusable for Hebrew — see below |
| `pdf` (LaTeX) | not tested | unnecessary; Word exports PDF and handles bidi better |

Quarto 1.10.18, installed machine-wide via `winget install Posit.Quarto`. Pandoc 3.9 and
Python 3.14 were already present.

## What's here

| Path | What it is |
|---|---|
| `render.py` | render plus SVG rasterization; use this instead of bare `quarto render` |
| `templates/hebrew.docx` | Word reference document — all `.docx` typography lives here |
| `rtl-fixes.css` | the handful of RTL touch-ups Quarto's stylesheets miss |
| `filters/svg-to-png.lua` | points Word output at rasterized copies of SVG figures |
| `scripts/docx_to_qmd.py` | Word to Quarto converter, with the cleanups described below |
| `scripts/set_docx_font.py` | fallback: forces one font onto a rendered `.docx` (see caveat below) |
| `scripts/set_docx_rtl_tables.py` | makes Word lay tables out right to left |
| `scripts/rasterize_svg.py` | SVG to PNG through headless Edge (no `rsvg-convert` needed on Windows) |
| `scripts/generate_repetition_schematic.py` | redraws the one figure Word conversion loses |
| `example/smoke-test.qmd` | one page for checking the toolchain still works |
| `example/slides_demo.qmd` | a short Hebrew lecture deck, to test `revealjs` and `pptx` |
| `visual-editor-rtl/` | right-to-left text in the VS Code visual editor |
| `upstream/` | the bug reports and patch these findings produced |

## Converting a Word document, then rendering it

```bash
# 1. Convert the Word document (one-time per document)
python scripts/docx_to_qmd.py "<path>/<document>.docx" \
    -o <document>.qmd --reflow-figures

# 2. Render. This rasterizes SVG figures first, which plain `quarto render` cannot do.
#    Word typography comes from templates/hebrew.docx; no post-processing runs.
python render.py <document>.qmd

# Slides have no docx step, so plain quarto is fine
quarto render example/slides_demo.qmd --to revealjs
```

Word → PDF, which is the recommended PDF path:

```powershell
$w = New-Object -ComObject Word.Application; $w.Visible = $false
$d = $w.Documents.Open("<abs>\<document>.docx", $false, $true)
$d.SaveAs([ref]"<abs>\<document>.pdf", [ref]17); $d.Close($false); $w.Quit()
```

## Setting the font (David)

The document font is **David**. How it is set differs per output, and the Word case
has a trap worth knowing.

**HTML and revealjs** — `rtl-fixes.css` sets the family, with fallbacks so the page
still reads correctly off this machine:

```css
David, "David CLM", "David Libre", FrankRuehl, "Frank Ruehl CLM", serif
```

Monospace is deliberately left alone: David has no monospace design, and code needs
fixed advance widths.

**Word** — all typography comes from the reference document,
`templates/hebrew.docx`, named in the `.qmd` via `reference-doc:`. It is pandoc's
own default reference file, hand-edited in Word. Note that `mainfont:` does **not**
reach `.docx` at all, so it is not an option there.

Edit it through **Styles pane → right-click → Modify → Format → Font**, not by
selecting text and restyling it — only style definitions propagate to rendered
documents, direct formatting does not. Hebrew reads from the **"Complex scripts"**
font box, not the Latin one (`w:cs` in the file, `Font.NameBi` in Word's object
model), so set both.

### `lang` must include the region subtag — this is the whole bug

**`lang: he` silently breaks Hebrew fonts in Word. Use `lang: he-IL`.**

This is what made the font "impossible" to set for most of this trial, and it is
worth understanding because no amount of template editing works around it.

Pandoc writes the document's `lang` straight into the docx as
`<w:lang w:bidi="...">` in `<w:docDefaults>`. Word only honours a full locale
there. Given a bare `he`, it **discards the reference document's complex-script
font entirely** and falls back to Times New Roman — even though the file plainly
contains `<w:rFonts ... w:cs="David"/>` on the `Normal` style.

Measured by flipping that single attribute in an otherwise identical file:

| `<w:lang w:bidi="…">` | Word's complex-script font for `Normal` |
|---|---|
| `he` | **Times New Roman** — explicit `w:cs="David"` ignored |
| `he-IL` | David |
| `ar-SA` | David |

The mechanism is in pandoc's `Docx.hs`: `mkLangTransformer` routes bidi languages
into the `w:bidi` attribute via `renderLang`, performing no validation and adding
no region subtag. Nothing warns you.

This also explains the earlier red herring. Heading styles name their font through
the theme (`majorBidi`), which resolved fine; body styles were subject to the
broken `w:bidi`. Hence "the heading changed to David but body text stayed
Times New Roman" — the symptom that sent us chasing themes and run properties.
The theme's per-script fallback
(`<a:font script="Hebr" typeface="Times New Roman"/>`) is real and worth knowing
about, but it was not what was breaking this document.

The styles pandoc actually applies — names as they appear in Word:

`Normal`, `Body Text`, `First Paragraph`, `Title`, `Subtitle`, `Author`,
`heading 1`–`heading 4`, `Image Caption`, `Table Caption`, `Block Text`
(blockquotes), `Compact` (lists), `Verbatim Char`, `Footnote Text`.

Headings are lowercase (`heading 1`). There is no `Quote` or `SourceCode` style in
the default file: blockquotes use `Block Text`, and a code style is created on
demand. Starting from pandoc's default rather than a blank document matters —
pandoc only applies styles that already exist by name.

### Fallback: forcing a font after rendering

With `lang: he-IL` and a styled template, **no post-processing is needed** — this
document renders correctly through plain `render.py`.

`scripts/set_docx_font.py` is kept only as an escape hatch. It pins `<w:rFonts>`
onto every run, which outranks styles, `docDefaults`, and the theme, so it works
even against the `lang` bug — but it **flattens every style to a single face**,
making per-style typography impossible. Reach for it only if a template genuinely
cannot be made to work:

```bash
python render.py <document>.qmd --font David
```

Verify by asking the PDF which fonts it actually embedded — that is ground truth,
unlike the XML or `Font.Name` (which reports the Latin slot and so looks fine even
when Hebrew is wrong):

```bash
python -c "import re; d=open('<document>.pdf','rb').read(); print(sorted(set(m.decode() for m in re.findall(rb'/BaseFont\s*/([A-Za-z0-9+#,-]+)',d))))"
# ['BCDEEE+David', 'BCDFEE+David', 'BCDGEE+David', 'BCDHEE+David-Bold', 'BCDIEE+ArialMT']
```

`ArialMT` is the theme's fallback for scripts the document never uses (Armenian and
similar); no Hebrew or Latin text resolves to it. What matters is that no
Times New Roman is embedded.

Note that Word's `Font.Name` reports the **Latin** slot, so it reads "David" even
when Hebrew is still wrong — which is exactly how a bad render passed an earlier
check here. Use `Font.NameBi`, or the PDF's embedded fonts. Headings legitimately
report `+Headings CS`, a theme reference that resolves to David, not a literal
font name.

Minor cosmetic note: David renders a slightly wide gap before a colon, so
`השאלה: איך` looks like `השאלה : איך`. It's the font's side bearing, not a markup
problem, and it appears in Word too.

## What Quarto fixes

**Figure numbering.** This was the original complaint, and it is fully solved. Figures
carry labels (`{#fig-3}`) and are cited by label (`@fig-3`); Quarto assigns numbers from
document order. Inserting a figure renumbers everything, including the references.

More importantly, **a broken reference is a loud warning, not a stale number**:

```
WARNING (main.lua:14840) Unable to resolve crossref @fig-9
```

The trial document exercised this for real. Figure 9 was drawn with native Word shapes,
which carry no image and are lost on conversion, so the reference had nothing to point
at. Quarto refused to resolve it and renumbered the remaining figures consistently —
where Word would have kept displaying a number that no longer meant anything.

**Claude Code reads it exactly.** `.qmd` is plain text, so no more misread `.docx`.
Diffs are reviewable and figures are script-generated.

## Gotchas found, and how they're handled

### 1. Hebrew prefixes break cross-references — the important one

Hebrew prefixes attach directly to the following word, and Quarto will not resolve a
reference when a letter precedes the `@`. Measured on all six plausible forms:

| Source | Renders as | |
|---|---|---|
| `ב@fig-2` | `ב@fig-2` | **silently unresolved** |
| `ב @fig-2` | `ב איור 2` | resolves, wrong Hebrew (stray space) |
| `ב[-@fig-2]` | `ב2` | resolves, loses the word "איור" |
| `ב-@fig-2` | `ב-איור 2` | **correct** |
| `@fig-2` | `איור 2` | correct |

**Use `ב-@fig-2`.** The maqaf is how these updates already write Latin-script tokens
(`ב-MSM`, `ל-passim`), so it costs nothing stylistically. The converter inserts it
automatically when a Hebrew prefix was glued to a Word bookmark reference.

Note the failure mode of the naive form is silent in the *reference*, but Quarto still
warns that the crossref is unresolved — so this cannot ship unnoticed.

### 2. Word output cannot embed SVG

Pandoc shells out to `rsvg-convert` for SVG-in-docx, and there is no Windows package for
it (not on winget). Handled without adding a dependency: `scripts/rasterize_svg.py`
rasterizes via headless Edge — already this project's SVG renderer — and
`filters/svg-to-png.lua` swaps the extension for docx only, so HTML keeps the vector.

### 3. Native Word drawings are lost entirely

Shapes, SmartArt, and drawing canvases have no image part to extract. One figure in the
trial document was affected. There is no automated fix; it must be redrawn.
`scripts/generate_repetition_schematic.py` does that for this document, and the converter
warns which figure numbers are affected instead of emitting a dead reference.

Since these have to be redrawn anyway, redraw them as scripts producing SVG — matching
the existing convention in `two_letter_algorithm/scripts/`.

### 4. Pandoc's default tables are whitespace-fragile

Pandoc emits grid/multiline tables by default, whose columns are defined by exact
character alignment — an editor that trims trailing whitespace destroys them silently
(this happened during the trial). The converter forces pipe tables instead:

```
--to=markdown-grid_tables-multiline_tables-simple_tables+pipe_tables
```

### 5. Word conversion leaves per-run direction spans

Word marks direction on every run, so pandoc emits `[טקסט]{dir="rtl"}` around nearly
every fragment. Unreadable and unmaintainable. The converter strips them and sets
`dir: rtl` once in the frontmatter.

### 6. Word floats figures; conversion does not

Figures 3–8 all landed in one clump after the paragraph citing figure 8. Numbering stays
correct either way (Quarto numbers by document order), but reading order does not.
`--reflow-figures` moves each figure to just after the paragraph that first cites it, and
leaves alone any figure that already follows its citation or that nothing cites.

### 7. A few RTL alignment gaps in Quarto's CSS

Figure/table captions and table headers keep a hard-coded left alignment. `rtl-fixes.css`
corrects them.

### 8. Word pagination is loose

Figures are inline paragraphs with no float, so Word leaves whitespace where a figure
won't fit. Same behaviour as the original hand-written document; tighten with a
`reference-doc` if it becomes annoying.

### 9. Smart quotes curl Hebrew gershayim and geresh

Pandoc's `smart` extension, on by default, turns `"` and `'` into curly quotes. In Hebrew
they are abbreviation marks, not quotes: `ז"ל` renders as `ז”ל`, `גב'` as `גב’`, and an
acronym like `ה"פער` has no closing quote to pair with. `_quarto.yml` sets
`from: markdown-smart`, which keeps every quote exactly as typed. The cost is that `--`
and `...` also stay as typed instead of becoming a dash and an ellipsis; type `–` and `…`
directly where you want them.

## Why `pptx` fails for Hebrew

Pandoc does not propagate `dir: rtl` into PowerPoint — the generated slides contain zero
`rtl="1"` paragraph attributes. Verified by rendering and opening in PowerPoint 16:

- bullets and list numbers sit on the **left**
- clause order visibly scrambles, because the base direction stays LTR: *"שני חיבורים —
  הלכות פסוקות והלכות גדולות — חולקים קטעי טקסט"* rendered as *"חולקים קטעי —הלכות
  פסוקות והלכות גדולות —שני חיבורים"*
- captioned figures with cross-references degrade (`FloatRefTargets require a single
  image as content`)

The same deck rendered to `revealjs` is correct in every respect. **For teaching
material, use `revealjs`** — it also gives incremental reveals, speaker notes, and PDF
export. Reach for `pptx` only if a colleague must edit the file in PowerPoint, and expect
to fix direction by hand.

## Recommended workflow

Quarto is the single source; Word is an export stop, not a second copy.

```
.qmd  ──quarto──>  .html   (write and review here)
      ──quarto──>  .docx   ──Word──>  .pdf   (share with advisor)
      ──quarto──>  revealjs        (teach from this)
```

One caveat if you resume editing in Word: Quarto's cross-references land in `.docx` as
static text, not live Word fields. Numbering is correct as rendered, but Word will not
renumber if you then insert a figure there. Treat the `.docx` as output.
