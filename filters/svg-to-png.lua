--- Point Word output at a rasterized copy of each SVG figure.
---
--- Pandoc cannot embed an SVG in a .docx: it shells out to `rsvg-convert`, which
--- has no Windows package. HTML should still get the vector original, so instead
--- of rasterizing the source we point docx output at a raster copy, and let
--- `scripts/rasterize_svg.py` produce it beside the SVG.
---
--- The raster of `figure.svg` is `figure.svg.png`, not `figure.png`: the double
--- extension marks it as generated, so `*.svg.png` in .gitignore keeps rasters
--- out of git while hand-made PNGs, screenshots among them, stay tracked.
---
--- Enabled for docx output in _quarto.yml at the repository root.

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

  local png = img.src .. ".png"            -- figure.svg -> figure.svg.png
  if exists(png) then
    img.src = png
    return img
  end

  io.stderr:write(
    "svg-to-png: no raster found for " .. img.src ..
    " — render with: python render.py <document>.qmd\n"
  )
  return nil
end
