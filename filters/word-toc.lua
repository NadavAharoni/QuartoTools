-- A right-to-left table of contents for Word, wherever the document puts it.
--
--   ::: {.word-toc title="תוכן העניינים" depth="2"}
--   :::
--
-- Word: the div becomes the title (style TOC Heading) and one line per heading
-- down to `depth` (default 2), in the styles TOC 1, TOC 2, ...: the heading's
-- text, linked to it, a dot leader, and its page number.
-- HTML and other formats: the div is dropped; use Quarto's `toc` option there.
--
-- Why not Word's own TOC field (Quarto's `toc` option, or the field written as
-- raw XML): Word builds its lines when it updates the field, and builds them
-- left to right, whatever the document, the TOC styles or the headings say.
-- Here the lines are written already, right to left, and only the page numbers
-- are fields (PAGEREF, to the bookmark pandoc puts on each heading), marked for
-- Word to fill in when it opens the file. Updating them leaves the lines alone.
-- The dot leader is a tab to the far margin, so it fits any page width.
--
-- The template should define TOC 1, TOC 2, ... (right to left, with an indent
-- for the lower levels); Word's built-in ones are left to right.

local function xml(s)
  return (s:gsub('&', '&amp;'):gsub('<', '&lt;'):gsub('>', '&gt;'):gsub('"', '&quot;'))
end

local function line(level, id, text)
  return table.concat {
    '<w:p><w:pPr><w:pStyle w:val="TOC', level, '"/><w:bidi/></w:pPr>',
    '<w:hyperlink w:anchor="', xml(id), '" w:history="1">',
    '<w:r><w:rPr><w:rtl/></w:rPr><w:t xml:space="preserve">', xml(text), '</w:t></w:r>',
    '</w:hyperlink>',
    -- "right" is the end of the line in a right-to-left paragraph: Word mirrors
    -- it. "left" would be the line's start, behind the text, and wraps.
    '<w:r><w:ptab w:relativeTo="margin" w:alignment="right" w:leader="dot"/></w:r>',
    '<w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>',
    '<w:r><w:instrText xml:space="preserve"> PAGEREF ', xml(id), ' \\h </w:instrText></w:r>',
    '<w:r><w:fldChar w:fldCharType="separate"/></w:r>',
    '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>',
  }
end

function Pandoc(doc)
  local is_toc = function(div) return div.classes:includes('word-toc') end
  if not FORMAT:match('docx') then
    return doc:walk { Div = function(div) if is_toc(div) then return {} end end }
  end

  local headers = {}
  doc:walk { Header = function(h) headers[#headers + 1] = h end }

  return doc:walk { Div = function(div)
    if not is_toc(div) then return nil end
    local depth = tonumber(div.attributes.depth) or 2
    local title = div.attributes.title or 'תוכן העניינים'
    local out = { '<w:p><w:pPr><w:pStyle w:val="TOCHeading"/><w:bidi/></w:pPr>',
                  '<w:r><w:rPr><w:rtl/></w:rPr><w:t xml:space="preserve">', xml(title),
                  '</w:t></w:r></w:p>' }
    for _, h in ipairs(headers) do
      if h.level <= depth and h.identifier ~= '' then
        out[#out + 1] = line(h.level, h.identifier, pandoc.utils.stringify(h.content))
      end
    end
    return pandoc.RawBlock('openxml', table.concat(out))
  end }
end
