-- Float a figure beside the text, with its caption kept underneath it.
--
--   ::: {.wrap-left}
--   ![Caption](media/photo.jpg){width="40%"}
--   :::
--
-- `.wrap-left` puts the figure on the left and the text flows down its right
-- side; `.wrap-right` the other way round. Left and right are the page's, not
-- the reading direction's, so they mean the same in Hebrew and English.
--
-- HTML: the div itself floats, at the image's width, and the image fills it, so
-- the caption stays under the image inside the floated box.
--
-- Word: pandoc can only place an image in the line of text. The filter leaves
-- comments around the figure, and scripts/wrap_docx_figures.py moves the
-- image and caption paragraphs into a floating text box after the render.
-- render.py runs it.
--
-- `.full-page` covers a whole page with the picture instead, edge to edge, for a
-- cover. Word only: the picture is anchored to the page behind the text, sized
-- to the page, and cropped where its shape differs from the page's. `crop` says
-- where to take the difference from: "center" (the default), "top" or "bottom".
-- `crop="bottom"` keeps the top edge of the picture, for one with a head near it.
--
--   ::: {.full-page crop="bottom"}
--   ![](media/cover.svg)
--   :::
--
-- HTML shows the picture as usual.
--
-- List this filter before auto-direction.lua: in Word the div is replaced by
-- its contents, which auto-direction then handles like any other figure.

local SIDES = {['wrap-left'] = 'left', ['wrap-right'] = 'right', ['full-page'] = 'page'}
local GAP = '1.5em'

local function side_of(div)
  for _, class in ipairs(div.classes) do
    if SIDES[class] then return SIDES[class] end
  end
end

function Div(div)
  local side = side_of(div)
  if not side then return nil end

  if FORMAT:match('docx') then
    local marker = side
    if side == 'page' then marker = 'page ' .. (div.attributes.crop or 'center') end
    local blocks = pandoc.List({pandoc.RawBlock('openxml', '<!--WRAP-FIGURE ' .. marker .. '-->')})
    blocks:extend(div.content)
    blocks:insert(pandoc.RawBlock('openxml', '<!--/WRAP-FIGURE-->'))
    return blocks
  end

  if FORMAT:match('html') then
    if side == 'page' then return nil end
    -- The image's width becomes the box's, and the image fills the box.
    local width = '40%'
    div = div:walk({
      Image = function(image)
        width = image.attributes.width or width
        image.attributes.width = '100%'
        return image
      end,
    })
    -- A bare number is pixels to pandoc, but not to CSS.
    if width:match('^[%d.]+$') then width = width .. 'px' end
    local margin = side == 'left'
      and ('0.3em ' .. GAP .. ' 1em 0') or ('0.3em 0 1em ' .. GAP)
    div.attributes.style = string.format('float: %s; width: %s; margin: %s;',
                                         side, width, margin)
    return div
  end
end
