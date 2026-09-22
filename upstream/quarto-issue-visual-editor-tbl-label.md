# Visual editor silently drops table cross-reference labels (`{#tbl-…}`)

*Draft issue report for https://github.com/quarto-dev/quarto/issues — see the bottom
of this file for how to file it.*

---

## Summary

Opening a document in the visual editor and saving it **removes the label from a
labelled table**, rewriting the source file:

```diff
-: A table caption {#tbl-nums}
+: A table caption
```

The table then stops being a cross-referenceable float: it loses its number, any
`@tbl-nums` reference renders literally, and `quarto render` reports

```
WARNING (main.lua:14840) Unable to resolve crossref @tbl-nums
```

Figure labels (`{#fig-…}`) are unaffected.

This is source data loss rather than a rendering problem. Nothing warns at edit time,
and if the document has no reference to the table yet, nothing warns later either —
the label is simply gone, and a reference added afterwards fails for no visible
reason.

## Environment

- Quarto VS Code extension **1.135.0**
- VS Code 1.133.0, Windows 11
- Quarto CLI 1.10.18

## Steps to reproduce

`repro.qmd`:

```markdown
---
title: "Minimal repro"
---

See @tbl-nums and @fig-pic.

| a | b |
|---|---|
| 1 | 2 |

: A table caption {#tbl-nums}

![A figure caption](any-image.png){#fig-pic width=40%}
```

1. `quarto render repro.qmd` — renders cleanly; both references resolve to
   "Table 1" and "Figure 1".
2. Open `repro.qmd` in VS Code and switch to visual mode (`Ctrl+Shift+F4`).
3. Type a character in the paragraph and delete it, so the document is written back.
4. Save, return to source mode, and diff.

## Expected

The document round-trips unchanged apart from the edit.

## Actual

`{#tbl-nums}` is gone from the table caption. `{#fig-pic}` survives.

Rendering before and after the round-trip:

| | before | after |
|---|---|---|
| captions | `Table 1: A table caption`, `Figure 1: A figure caption` | only `Figure 1: A figure caption` |
| `@tbl-nums` | resolves to "Table 1" | rendered literally as `@tbl-nums` |
| render | clean | `Unable to resolve crossref @tbl-nums` |

## Diagnosis

**Pandoc is not at fault.** Its reader puts the label on the `Table` element itself:

```
, Table
    ( "tbl-nums" , [] , [] )
           [ Str "A" , Space , Str "table" , Space , Str "caption" ]
```

and its markdown writer re-emits it. Verified losslessly with both standalone pandoc
3.9.0.1 and the pandoc 3.10 bundled with Quarto:

```bash
pandoc repro.qmd -f markdown -t markdown --wrap=none   # keeps {#tbl-nums}
quarto pandoc repro.qmd -f markdown -t markdown --wrap=none   # keeps it too
```

**The loss is in the editor's ProseMirror model.** In the shipped bundle
(`assets/www/editor/index.js`) the table node spec is:

```js
{ name: "table", spec: { ...yb.table,
    attrs: { ...yb.table.attrs, width: {default:null}, colpercents: {default:null} },
    ...
```

Width and column percentages are modelled; there is no field for the pandoc
identifier. So the id read from the AST has nowhere to live and is dropped when the
document is written back. This is consistent with figures surviving, since `Image`
attributes *are* modelled.

## Additional churn that hides the loss

A visual-mode round-trip also rewrites unrelated markup, which makes the real damage
easy to miss in review. On a 220-line document here it produced a 42-line diff:

- `{width=100%}` → `{width="100%"}` on every image
- `>` escaped to `\>` inside table captions
- HTML comments wrapped in ```` ```{=html} ```` blocks
- hard-wrapped lines unwrapped
- table cells padded

None of that is harmful on its own, but a one-line label deletion inside it is very
easy to overlook — especially for anyone not keeping documents in version control.

## A patch

Written and committed on branch `fix/visual-editor-table-crossref-attr` in a clone at
`~/Documents/dev/quarto`, and exported to
`quarto_test/quarto-patch-table-attr.patch`. 32 lines across two files.

The pandoc `Table` token's attribute maps naturally onto `table_container`, which is
the node whose reader/writer handle that token. So:

**`packages/editor/src/nodes/table/table-pandoc.ts`**

- uncomment `kTableAttr = 0` (it was already there, unused)
- reader: `writer.openNode(schema.nodes.table_container, pandocAttrReadAST(tok, kTableAttr))`
  instead of `{}`
- writer: `output.writeAttr(node.attrs.id, node.attrs.classes, node.attrs.keyvalue)`
  instead of the bare `output.writeAttr()` marked *"write empty attributes"*

**`packages/editor/src/nodes/table/table-nodes.ts`**

- add `...pandocAttrSpec` to `tableContainerNode.spec.attrs`
- `parseDOM` gains `getAttrs` via `pandocAttrParseDom`, and `toDOM` emits them via
  `pandocAttrToDomAttr`, merging the existing container classes — so attributes also
  survive DOM round-trips (copy/paste), not just file round-trips

Every call matches the idiom already used by `div.ts`, `heading.ts`, `image.ts` and
`marks/code.ts`; no new helpers were needed, which suggests the omission was an
oversight rather than a deliberate limitation.

**Verified behaviourally, headlessly.** `quarto-verify-table-attr.ts` drives the two
patched functions directly with fake writer/output objects — no DOM, no pandoc
process, no editor instance — and runs under the repo's own `tsx`:

```
WITH PATCH
  read  : table_container attrs.id = "tbl-nums"   PASS
  write : writeAttr("tbl-nums", [], [])           PASS
  RESULT: identifier survives the round-trip

WITHOUT PATCH (same script, patch reverted)
  read  : table_container attrs.id = null         FAIL
  write : writeAttr()                             FAIL
  RESULT: identifier is LOST
```

The control matters as much as the result: the script fails on unpatched code, so it
is genuinely detecting this bug rather than passing vacuously.

`packages/editor` has test files but no test script or runner wired up, so this is a
standalone script rather than a test in the suite. Happy to turn it into a proper test
if you point at the right harness.

**Builds clean.** `yarn build-vscode` succeeds (4 tasks, ~3 min) with the patch applied.

**Typechecks clean.** `tsc --noEmit -p packages/editor/tsconfig.json` reports exactly
one error with the patch applied, in `src/nodes/rmd_chunk/rmd_chunk-image.ts` — and
reverting the patch produces the identical single error, so it is pre-existing and
unrelated. The patch adds no new type errors.

### Follow-up worth mentioning but not included

Nodes that carry pandoc attributes usually also register an `attr_edit` entry so the
attributes can be edited in visual mode — `div.ts` is the closest analogue. Adding one
for `table_container` would let a user *set* a table label from the visual editor,
rather than only preserving one written in source. That is a feature on top of the
bug fix, so it is left out deliberately.

## Suggested handling

Whatever the fix, the failure mode seems worth separating from the feature work: if
the identifier cannot yet be preserved, refusing to write back a construct the model
cannot represent — or warning — would be much safer than silently discarding it.

I am happy to test a fix; I have a reproducible setup on Windows.

## Possibly related

- Reports of `reference-doc` styles or attributes not surviving conversion are a
  different area, but the general theme of round-trips dropping what the intermediate
  model cannot represent is the same.

---

## How to file this

1. Go to <https://github.com/quarto-dev/quarto/issues> (the extension and visual
   editor repo — **not** quarto-cli, which is the CLI).
2. Search first for `tbl` / `table label` / `visual editor` to check it is not known.
3. **New issue**, paste everything from the title down to "Possibly related".
4. Attach the before/after `repro.qmd` if convenient — a screenshot of the diff is
   just as good.

### Submitting the patch as a PR

File the issue first and link the PR to it; maintainers may prefer a different home
for the attributes than `table_container`.

1. Fork `quarto-dev/quarto` on GitHub.
2. In the clone at `~/Documents/dev/quarto`, point it at your fork and push the
   existing branch:

       git remote add fork https://github.com/<you>/quarto.git
       git push fork fix/visual-editor-table-crossref-attr

   (The branch already has the commit. Note the clone was made with `--depth 1`; if
   GitHub objects, `git fetch --unshallow origin` first.)
3. Open the PR against `main`, describing the bug and linking the issue.

`packages/editor` is **AGPL-3.0**, so the contribution is under that licence.

Before pushing, ideally build and confirm in a dev instance:

    yarn && yarn dev-vscode

then open the repro in visual mode and check the label survives. Note that
`corepack enable` needs administrator rights on this machine; `npx yarn@1.22.22
install` works without it.

Local copies for the repro: `quarto_test/tbl-label-repro.qmd` (with the steps in a
comment) and `quarto_test/rtl-spike/README.md` for the wider notes.
