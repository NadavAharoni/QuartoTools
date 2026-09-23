-- Mark tables that sit inside a right-to-left div, for Word output.
--
-- Word lays a table out left to right unless the table itself carries
-- `w:bidiVisual`. Pandoc never writes that element, and `dir="rtl"` on a div
-- reaches the paragraphs inside the table but not the table's own properties,
-- so the columns come out in the wrong order.
--
-- Nothing in the pandoc AST can set a table property, so this filter leaves a
-- marker in the output instead: a raw OOXML comment immediately before each
-- table that needs it. `scripts/set_docx_rtl_tables.py` then turns each marker
-- into a real `w:bidiVisual` on the table that follows, and deletes the marker.
-- `render.py` runs that script for you.
--
-- Only tables inside a div marked `dir="rtl"` are touched, so a document can
-- hold both right-to-left and left-to-right tables:
--
--     ::: {dir="rtl"}
--     | עמודה  |    ערך |
--     |--------|-------:|
--     | התאמות |    233 |
--     :::

local MARKER = '<!--RTL-TABLE-->'

-- Insert the marker before every table in this list of blocks, at any depth.
local function mark(blocks)
  local out = {}
  for _, block in ipairs(blocks) do
    if block.t == 'Table' then
      table.insert(out, pandoc.RawBlock('openxml', MARKER))
    elseif block.content and (block.t == 'Div' or block.t == 'BlockQuote') then
      block.content = mark(block.content)
    end
    table.insert(out, block)
  end
  return out
end

function Div(div)
  if FORMAT ~= 'docx' then return nil end
  if div.attributes and div.attributes.dir == 'rtl' then
    div.content = mark(div.content)
    return div
  end
end
