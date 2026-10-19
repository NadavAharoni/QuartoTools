-- Keep the quotes in the YAML header as typed, as `from: markdown-smart` already
-- does for the body.
--
--   subtitle: לע"נ אמא ע"ה
--
-- Quarto reads `title`, `subtitle`, `author` and the rest of the metadata with
-- smart quotes on, whatever `from` says, so the line above would render as
-- לע”נ אמא ע”ה. This filter turns every curly quote in the metadata back into
-- the straight one, including a pair the reader matched, such as "שלום". The
-- body is not touched, so a curly quote typed there on purpose stays curly.
--
-- Write such a value without YAML quotes, as above: inside "..." a `"` ends
-- the value early and the render stops with `bad indentation of a mapping
-- entry`. Use '...' only when the value needs it, for a ": " or a leading
-- symbol, and double any geresh inside it: 'גב'' כהן'.

local STRAIGHT = {
  ['\u{201C}'] = '"', ['\u{201D}'] = '"',
  ['\u{2018}'] = "'", ['\u{2019}'] = "'",
}

local straighten = {
  Str = function(el)
    local text = el.text
    for curly, plain in pairs(STRAIGHT) do text = text:gsub(curly, plain) end
    el.text = text
    return el
  end,
  Quoted = function(el)
    local q = el.quotetype == 'DoubleQuote' and '"' or "'"
    local out = pandoc.Inlines{pandoc.Str(q)}
    out:extend(el.content)
    out:insert(pandoc.Str(q))
    return out
  end,
}

local function fix(value)
  local t = pandoc.utils.type(value)
  if t == 'Inlines' or t == 'Blocks' then return value:walk(straighten) end
  if t == 'List' then return value:map(fix) end
  if t == 'table' then
    for k, v in pairs(value) do value[k] = fix(v) end
  end
  return value
end

function Meta(meta)
  for k, v in pairs(meta) do meta[k] = fix(v) end
  return meta
end
