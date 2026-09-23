-- Give each paragraph and table the direction of its first strong character.
--
-- A document that sets `dir: rtl` lays everything out right to left, so an
-- English paragraph comes out right-aligned with its full stop on the left, and
-- a table of English terms comes out with its first column on the right. The
-- Unicode bidi algorithm has a rule for this -- take the direction from the
-- first strong directional character -- which is what a browser does for
-- `dir="auto"`. Neither Word nor Quarto applies it, so this filter does.
--
-- How the direction is then expressed differs by output:
--
--   * a paragraph in Word: wrapped in a div stating the direction, which pandoc
--     turns into `w:bidi` on the paragraph
--   * a paragraph in HTML: nothing here -- `rtl-fixes.css` sets
--     `unicode-bidi: plaintext`, the same rule expressed natively
--   * a table in HTML: a `dir` attribute on the table element
--   * a table in Word: a comment before the table, which
--     `scripts/set_docx_rtl_tables.py` turns into `w:bidiVisual` afterwards.
--     Nothing in the pandoc AST can set a table property, hence the detour.
--     `render.py` runs that script.
--
-- The heuristic has one known failure, and it is common in Hebrew academic
-- prose: a Hebrew sentence that opens with a Latin term, such as
-- `MSM מוצא קטעים ארוכים יותר`, reads as left to right. Override it by hand:
--
--     ::: {dir="rtl"}
--     MSM מוצא קטעים ארוכים יותר מאשר האלגוריתם הקודם.
--     :::
--
-- A div that states a direction wins outright: nothing inside it is examined,
-- so a hand override is never second-guessed.

local stringify = pandoc.utils.stringify
local MARKER = '<!--RTL-TABLE-->'

-- Strong right-to-left ranges: Hebrew, Arabic, Syriac, Thaana, and the Hebrew
-- and Arabic presentation forms.
local RTL_RANGES = {
  {0x0590, 0x05FF}, {0x0600, 0x07BF}, {0x0860, 0x08FF},
  {0xFB1D, 0xFDFF}, {0xFE70, 0xFEFF},
  {0x10800, 0x10FFF}, {0x1E800, 0x1EFFF},
}

-- Strong left-to-right ranges: Latin, Greek, Cyrillic, and the other alphabets
-- up to the start of the Hebrew block.
local LTR_RANGES = {
  {0x0041, 0x005A}, {0x0061, 0x007A}, {0x00C0, 0x02B8},
  {0x0370, 0x058F}, {0x0900, 0x10FF}, {0x1E00, 0x1FFF},
  {0x2C00, 0x2DFF}, {0xA000, 0xD7FF},
}

local function within(code, ranges)
  for _, range in ipairs(ranges) do
    if code >= range[1] and code <= range[2] then return true end
  end
  return false
end

-- The direction of the first strong character, or nil when there is none
-- (a paragraph of digits, punctuation or symbols has no direction of its own).
local function detect(text)
  for _, code in utf8.codes(text) do
    if within(code, RTL_RANGES) then return 'rtl' end
    if within(code, LTR_RANGES) then return 'ltr' end
  end
  return nil
end

local WRAPPABLE = {Para = true, Plain = true, Header = true, LineBlock = true}
local CONTAINERS = {Div = true, BlockQuote = true, Figure = true}

local function process(blocks, inherited, stated)
  local out = {}
  for _, block in ipairs(blocks) do
    if block.t == 'Div' and block.attributes and block.attributes.dir then
      -- A stated direction is an instruction, not a starting point: inside it
      -- nothing is examined, only carried down to the tables that need it.
      block.content = process(block.content, block.attributes.dir, true)
      table.insert(out, block)
    elseif CONTAINERS[block.t] then
      block.content = process(block.content, inherited, stated)
      table.insert(out, block)
    elseif block.t == 'BulletList' or block.t == 'OrderedList' then
      for i, item in ipairs(block.content) do
        block.content[i] = process(item, inherited, stated)
      end
      table.insert(out, block)
    elseif block.t == 'Table' then
      local dir = stated and inherited or (detect(stringify(block)) or inherited)
      if FORMAT == 'docx' then
        if dir == 'rtl' then
          table.insert(out, pandoc.RawBlock('openxml', MARKER))
        end
      else
        block.attr.attributes.dir = dir
      end
      table.insert(out, block)
    elseif WRAPPABLE[block.t] and FORMAT == 'docx' and not stated then
      local dir = detect(stringify(block))
      if dir and dir ~= inherited then
        table.insert(out, pandoc.Div({block}, pandoc.Attr('', {}, {dir = dir})))
      else
        table.insert(out, block)
      end
    else
      table.insert(out, block)
    end
  end
  return out
end

function Pandoc(doc)
  local inherited = 'ltr'
  if doc.meta.dir then inherited = stringify(doc.meta.dir) end
  doc.blocks = process(doc.blocks, inherited, false)
  return doc
end
