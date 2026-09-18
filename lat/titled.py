"""Presentation sheet: the map with a title and a legend, like Fischer's
uploads on Flickr carried. Everything is scaled from the map's own width, so
it renders identically from the 1600 px and the 6137 px maps.

    .venv/bin/python lat/titled.py                       # 6137 px map
    .venv/bin/python lat/titled.py --map out/hanoi_locals_tourists_1600.png

The numbers in the legend are the DRAWN ones from out/stats.json (points and
photographers on the canvas), not the rows loaded.
"""
import argparse
import json

from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None
FONTS = ("/usr/share/fonts/truetype/dejavu/DejaVuSans{b}.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans{b}.ttf")
LEGEND = [((0, 0, 255), "locals", "local",
           "photographed in Hanoi over a span of a month or more"),
          ((255, 0, 0), "tourists", "tourist",
           "a local of some other city, and in Hanoi under a month"),
          ((255, 215, 0), "unknown", "unknown",
           "nowhere photographed over a month")]


def font(px, bold=False):
    for p in FONTS:
        try:
            return ImageFont.truetype(p.format(b="-Bold" if bold else ""), px)
        except OSError:
            pass
    return ImageFont.load_default()


def build(map_path, stats_path, out_path):
    m = Image.open(map_path).convert("RGB")
    W = m.size[0]
    s = W / 1600.0                      # the layout was designed at 1600 px
    pad, top, bot = round(48 * s), round(132 * s), round(112 * s)
    c = Image.new("RGB", (W + pad * 2, top + m.size[1] + bot), "white")
    c.paste(m, (pad, top))
    d = ImageDraw.Draw(c)

    st = json.load(open(stats_path))
    n_pts = sum(st["points"].values())
    n_ph = sum(st["photographers_on_map"].values())
    d.text((pad, round(34 * s)), "Locals and Tourists: Hanoi",
           fill=(20, 20, 20), font=font(round(46 * s), True))
    d.text((pad, round(92 * s)),
           f"after Erica Fischer  ·  {n_pts:,} geotagged photographs, "
           f"{n_ph:,} photographers  ·  24.2 km square",
           fill=(110, 110, 110), font=font(round(21 * s)))

    y, x = top + m.size[1] + round(24 * s), pad
    for col, name, key, desc in LEGEND:
        sq = round(16 * s)
        d.rectangle([x, y + round(6 * s), x + sq, y + round(6 * s) + sq], fill=col)
        tx = x + round(26 * s)
        d.text((tx, y + round(2 * s)), name, fill=(20, 20, 20),
               font=font(round(23 * s), True))
        d.text((tx, y + round(30 * s)),
               f"{st['points'][key]:,} photos · "
               f"{st['photographers_on_map'][key]:,} photographers",
               fill=(90, 90, 90), font=font(round(18 * s)))
        d.text((tx, y + round(52 * s)), desc, fill=(140, 140, 140),
               font=font(round(15 * s)))
        x += round(520 * s)
    c.save(out_path, optimize=True)
    print(f"wrote {out_path} {c.size}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="out/hanoi_locals_tourists_6137.png")
    ap.add_argument("--stats", default="out/stats.json")
    ap.add_argument("--out", default="out/hanoi_locals_tourists_titled.png")
    a = ap.parse_args()
    build(a.map, a.stats, a.out)
