--- Point Word output at a rasterized copy of each SVG figure.
---
--- Pandoc cannot embed an SVG in a .docx: it shells out to `rsvg-convert`, which
--- has no Windows package. HTML should still get the vector original, so instead
--- of rasterizing the source we swap the extension for docx only, and let
--- `scripts/rasterize_svg.py` produce the .png beside it.
---
--- Enable per-format in the .qmd:
---     format:
---       docx:
---         filters: [filters/svg-to-png.lua]

local function exists(path)
  local handle = io.open(path, "r")
  if handle then
    handle:close()
    return true
  end
  return false
end

function Image(img)
  if not img.src:lower():match("%.svg$") then
    return nil
  end

  local png = img.src:gsub("%.[Ss][Vv][Gg]$", ".png")
  if exists(png) then
    img.src = png
    return img
  end

  io.stderr:write(
    "svg-to-png: no raster found for " .. img.src ..
    " — run: python scripts/rasterize_svg.py --all media\n"
  )
  return nil
end
