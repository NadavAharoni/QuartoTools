# docx writer: `lang` without a region subtag makes Word ignore the reference doc's complex-script font

*Draft issue report for https://github.com/jgm/pandoc/issues — see the bottom of this
file for how to file it.*

---

## Summary

When the document language is a bare bidi language tag (`lang: he`), the docx writer
emits `<w:lang w:bidi="he">` in `<w:docDefaults>`. Word does not accept a bare tag
there, and its response is to **silently ignore the complex-script font defined in
the reference document**, falling back to Times New Roman for all right-to-left
text.

Using a full locale (`lang: he-IL`) makes the same reference document work
correctly. The only difference between working and broken output is that one
attribute value.

This is easy to lose hours to, because:

- The generated `.docx` looks correct on inspection — `word/styles.xml` plainly
  contains `<w:rFonts ... w:cs="David"/>` on `Normal`.
- Word's own UI and `Font.Name` in the object model report the **Latin** slot, which
  is correct, so the styles appear to have applied. Only `Font.NameBi` (or the fonts
  the PDF ends up embedding) reveals the problem.
- Headings are usually unaffected, because they resolve their font through the theme
  (`majorBidi`) rather than through `docDefaults`. The result is the very confusing
  symptom "my headings changed font but my body text didn't".
- Nothing warns.

## Environment

- pandoc 3.9.0.1 (Windows binary)
- Microsoft Word 16.0 (Microsoft 365), Windows 11, English UI
- Reproduced with Hebrew; I would expect the same for Arabic, Farsi, Urdu, etc.,
  but I have only tested Hebrew

## Steps to reproduce

1. Build a reference document whose `Normal` style sets a complex-script font. This
   is what you get by opening pandoc's `reference.docx` in Word and setting
   **Modify Style → Format → Font → Complex scripts → David**; the script below does
   the same thing directly so the repro needs no manual step:

```python
import subprocess, zipfile, re, pathlib

raw = subprocess.run(["pandoc", "--print-default-data-file", "reference.docx"],
                     capture_output=True).stdout
pathlib.Path("seed.docx").write_bytes(raw)

with zipfile.ZipFile("seed.docx") as zin, \
     zipfile.ZipFile("ref-david.docx", "w", zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename == "word/styles.xml":
            xml = data.decode("utf-8")
            xml = re.sub(
                r'<w:style [^>]*w:styleId="Normal".*?</w:style>',
                lambda m: m.group(0).replace(
                    "</w:style>",
                    '<w:rPr><w:rFonts w:ascii="David" w:hAnsi="David" '
                    'w:cs="David"/></w:rPr></w:style>'),
                xml, count=1, flags=re.S)
            data = xml.encode("utf-8")
        zout.writestr(item, data)
```

2. Create `min.md` containing a line of Hebrew:

```
שלום עולם. זהו טקסט בעברית.
```

3. Render twice, differing **only** in the language tag:

```bash
pandoc min.md -o rtl-he.docx   --reference-doc=ref-david.docx -M lang=he    -M dir=rtl
pandoc min.md -o rtl-heIL.docx --reference-doc=ref-david.docx -M lang=he-IL -M dir=rtl
```

`dir=rtl` matters: it makes the writer mark runs `<w:rtl/>`, which is what causes
Word to consult the complex-script slot at all. Without it, Hebrew is drawn from the
Latin slot and the bug is hidden.

4. Open each in Word and compare the complex-script font.

## Expected

Both documents use David for the Hebrew text, as specified by the reference
document.

## Actual

| output | `lang` | `<w:lang w:bidi>` | Word's complex-script font |
|---|---|---|---|
| `rtl-he.docx` | `he` | `he` | **Times New Roman** |
| `rtl-heIL.docx` | `he-IL` | `he-IL` | David |

Both files contain the identical, correct style definition:

```xml
<w:rFonts w:ascii="David" w:cs="David" w:hAnsi="David" />
```

Confirmed independently by exporting each to PDF from Word and listing the embedded
fonts, which is ground truth for what was actually used to draw glyphs:

```
rtl-he.pdf    ['BCDEEE+TimesNewRomanPSMT', 'BCDFEE+David']
rtl-heIL.pdf  ['BCDEEE+David', 'BCDFEE+David']
```

Substituting `ar-SA` for the `w:bidi` value in the broken file, changing nothing
else, also yields David — so the trigger is specifically the absence of a region
subtag rather than anything about Hebrew.

## Where it comes from

`src/Text/Pandoc/Writers/Docx.hs`, in `mkLangTransformer`:

```haskell
updateLangAttrs e
  | isEastAsianLang lang = e{ elAttribs = map (setattr "eastAsia") ... }
  | isBidiLang lang      = e{ elAttribs = map (setattr "bidi") ... }
  | otherwise            = e{ elAttribs = map (setattr "val") ... }
```

The value comes from `renderLang lang`, which round-trips whatever the user wrote.
There is no validation and no region subtag added, so a bare `he` reaches
`w:bidi` unchanged.

Note that `w:val` (the Latin slot) is not affected in the same way in practice,
because fonts for Latin text do not depend on it — which is part of why this is so
asymmetric and hard to spot.

## `he` is a valid BCP 47 tag, which is why this is easy to walk into

Worth stressing: the input is not malformed. `he` is a correct IETF language tag,
and the manual's own wording invites it:

> `lang` — identifies the main language of the document using IETF language tags
> (following the BCP 47 standard), such as `en` or `en-GB`

A bare tag is given as the first example, and the manual links the Language Subtag
Lookup tool rather than enumerating tags, so there is nothing to suggest a region
subtag matters anywhere. Quarto, which many users reach pandoc through, lists its
translations by bare code as well (`he`, `fr`, `de`), so following its documentation
produces `lang: he` as the natural choice.

So pandoc is not mishandling BCP 47. It is passing a standards-valid tag into a Word
attribute that only accepts a full locale, and Word's failure mode for that is silent
and drastic.

I suspect this is why the problem does not seem to be reported despite being easy to
hit. Word's own language list is region-qualified ("Hebrew (Israel)"), so guidance
written from the Word side tends to use `he-IL` and those users never encounter the
bug. The people who do hit it come from the pandoc side, where a bare tag is the
documented example.

Note also that recipes recommending `he-IL` for Hebrew docx output do circulate, but
as a step in a list rather than as a fix — none I found state that a bare tag breaks
the complex-script font. So someone following a recipe end to end succeeds, while
someone who already wrote `lang: he` and is now debugging has no route from the
symptom back to the cause. That asymmetry is the argument for at least a warning or a
line in the manual.

## Possible fixes

Roughly in increasing order of effort, any one of which would have saved this:

1. **Document it.** State in the manual that docx output requires a region subtag
   for right-to-left languages, e.g. `he-IL` rather than `he`.
2. **Warn.** Emit a warning from the docx writer when a bidi language tag has no
   region subtag, since the failure is otherwise silent.
3. **Normalize.** Map a bare bidi language to its conventional Word locale when
   writing `w:bidi` (`he` → `he-IL`, `ar` → `ar-SA`, `fa` → `fa-IR`, `ur` → `ur-PK`).
   This keeps `lang: he` meaningful for every other output format while emitting
   something Word accepts. A small table would cover the RTL languages Word knows.
   Worth noting that this only affects the `w:bidi` attribute — the document's `lang`
   metadata, and every other writer, would be untouched.

I am happy to prepare a PR for (2) or (3) if a maintainer indicates which is
preferred — (3) changes behaviour, so it seems worth agreeing on first.

## Possibly related

- #7022 — `lang: zh-CN` makes western fonts in the output docx unchangeable. Same
  general shape (the `lang` metadata defeating reference-doc fonts), different
  language and slot.
- #6911 — RTL docx output not using `w:bCs`/`w:iCs` for bold/italic.
- #4947 — complex-script run properties ignored by the docx reader.
- #7047 — a correct BCP 47 tag in `lang` failing where an incorrect one works, for
  PDF via LaTeX. Different writer, but the same theme of a standards-valid tag not
  surviving contact with the backend.

## Not tested

- Whether other Word versions, or Word with a non-English UI language, behave the
  same way.
- Whether Quarto should also be asked to recommend full locales. For what it is
  worth, Quarto's own Hebrew UI strings resolve correctly from `he-IL` as well as
  `he`, so recommending the fuller tag would cost users nothing there.
- LibreOffice's handling of the same files (not installed here). It may well render
  both correctly, which would make this specifically a Word-compatibility issue.

---

## How to file this

1. **Get a GitHub account** if you do not have one, and sign in.
2. Go to <https://github.com/jgm/pandoc/issues> and search first — `w:bidi`, `lang
   docx font`, `complex script font` — to confirm nothing newer covers it.
3. Click **New issue**. Pandoc's tracker asks for pandoc version, the exact command,
   and expected vs actual behaviour; everything above is already in that shape.
4. Paste the content of this file from the title down to "Not tested". Drop the
   "How to file this" section.
5. Attach `ref-david.docx`, `rtl-he.docx`, and `rtl-heIL.docx` by dragging them onto
   the comment box. Maintainers can then check it without running anything, and
   GitHub accepts `.docx` attachments.
6. Submit, and expect a fast response — jgm is unusually responsive to reports that
   come with a minimal reproducer.

If you would rather discuss before filing, the pandoc-discuss list
(<https://groups.google.com/g/pandoc-discuss>) is the conventional venue, but a
report this concrete belongs straight on the tracker.

### If you want to go further and submit the fix

Pandoc is Haskell. For options (2) or (3) above the change is small and local:

1. Fork `jgm/pandoc`, then `git clone` your fork.
2. Build once: `cabal build` (or `stack build`). The first build is slow — expect a
   long wait while dependencies compile.
3. The code is `src/Text/Pandoc/Writers/Docx.hs`, function `mkLangTransformer`.
4. Add a test. Pandoc keeps docx writer tests under `test/`, with golden files in
   `test/docx/`; `cabal test` runs the suite.
5. Push the branch and open a pull request that links back to the issue.

Wait for a maintainer to say which option they want before writing code — otherwise
there is a real chance of implementing the wrong one.

---

## Answering other people who hit this

File the issue first. A forum answer is far more useful when it can link to a
canonical bug report, and it is the normal order of things.

### Where to look

Searches worth running (Stack Overflow is the most likely venue):

```
pandoc docx hebrew font not applied reference doc
pandoc docx arabic font times new roman reference-doc
pandoc reference.docx complex script font ignored
quarto docx hebrew font reference-doc
[pandoc] rtl font docx
```

Also: `groups.google.com/g/pandoc-discuss`, the Quarto discussions at
`github.com/orgs/quarto-dev/discussions`, and `forum.posit.co`.

### Check before answering

Most "reference-doc fonts are ignored" questions are **a different problem** — the
person formatted text directly instead of modifying the style definition. Only
answer if the symptoms match this bug:

- the language is right-to-left, and `lang:` is set to a bare tag
- the reference document really does set the **Complex scripts** font
- Latin text picks up the new font but the RTL text does not, **or** headings change
  and body text does not

If they only ever set the Latin font box, that is the ordinary mistake, not this.

### Reusable reply

> If your document sets a bare language tag — `lang: he` rather than `lang: he-IL` —
> that is likely the cause, and it is not your template.
>
> Pandoc writes the document language into the `.docx` as
> `<w:lang w:bidi="…">` in `<w:docDefaults>`. Word only accepts a full locale there.
> Given a bare tag it silently ignores the complex-script font from your reference
> document and falls back to Times New Roman — even though the file plainly contains
> `<w:rFonts … w:cs="YourFont"/>` on the `Normal` style.
>
> Fix: use the full locale.
>
> ```yaml
> lang: he-IL   # ar-SA, fa-IR, ur-PK for Arabic, Persian, Urdu
> ```
>
> Two things that make this hard to spot. It only shows up when runs are marked
> right-to-left (`dir: rtl`); without that, Word draws the text from the Latin slot
> and the font looks fine. And Word's own `Font.Name` reports the *Latin* slot, so it
> reads correctly while the Hebrew is still wrong — check `Font.NameBi`, or export to
> PDF and list the embedded fonts, which is the only real ground truth.
>
> Headings often look correct while body text does not, because heading styles
> resolve their font through the theme rather than through `docDefaults`.
>
> Reported upstream as <link to the issue>.

Adapt the language and locale to whatever the asker is using. Keep it short — the
one-line fix is the part they need; the mechanism is for whoever arrives later via
search.
