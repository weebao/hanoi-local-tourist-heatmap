"""Render the frequency-aware variant, for either dataset.

    PYTHONPATH=. .venv/bin/python lat/build_density.py single [--size 6137]
    PYTHONPATH=. .venv/bin/python lat/build_density.py merged [--size 6137]

Writes to out/density/ and never touches out/ or out/multi/. See lat/density.py
for why this exists and why it is a departure from Fischer's spec.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lat.basemap import load_overpass
from lat.classify import classify_users
from lat.density import (draw_density, pixel_counts, stacking_report,
                         popularity_marks, popularity_report)
from lat.fischer import (EquirectFrame, HANOI_BOUNDS, SIZE, build_marks,
                         draw_basemap, find_pins)

OUT = "out/density"


def load_single():
    """The faithful dataset: YFCC, with the vision relocations and mask."""
    from lat.build import load_hanoi, load_user_history
    ov = {k: tuple(v) for k, v in
          json.load(open("data/reloc/overrides.json")).items()}
    ex = json.load(open("data/reloc/exclude.json"))
    mi = set(json.load(open("data/reloc/masked_ids.json")))
    rows = load_hanoi(overrides=ov, exclude=ex)
    hist = load_user_history({r["user"] for r in rows})
    stale = {(r["user"], r["date"].date(), round(r["orig_lon"], 3),
              round(r["orig_lat"], 3)) for r in rows}
    hist = [h for h in hist
            if (h["user"], h["date"].date(), round(h["lon"], 3),
                round(h["lat"], 3)) not in stale]
    s_, w_, n_, e_ = HANOI_BOUNDS

    def in_city(lon, lat):
        return w_ <= lon <= e_ and s_ <= lat <= n_

    recs = hist + [{k: r[k] for k in ("user", "date", "lon", "lat")}
                   for r in rows]
    labels = {u: v[0] for u, v in
              classify_users(recs, in_city, city_bounds=HANOI_BOUNDS).items()}
    drawn = [r for r in rows if not (r["id"] in mi and r["id"] not in ov)]
    return drawn, labels, ov


def load_merged():
    from lat import multi
    m = multi.merge(cap=None, verbose=False)
    return m["rows"], m["labels"], {}


def main(which, size=SIZE, include_paths=False):
    rows, labels, ov = (load_single() if which == "single" else load_merged())
    frame = EquirectFrame(HANOI_BOUNDS, size)
    print(f"  {which}: {len(rows):,} rows loaded")

    counts = pixel_counts(rows, frame, labels)
    marks = popularity_marks(rows, frame, labels)
    prep = popularity_report(marks, sum(counts.values()))
    print(f"  {prep['squares']:,} popularity squares; largest holds "
          f"{prep['photographers_in_largest_square']} photographers "
          f"({prep['max_side_px']} px); top-50 median "
          f"{prep['median_photographers_top50']}, min {prep['min_photographers_top50']}")
    rep = stacking_report(counts)
    print(f"  {rep['photos']:,} photographs on {rep['distinct_pixels']:,} "
          f"distinct pixels")
    print(f"  the opaque render hides {rep['hidden_by_opaque_render']:,} of "
          f"them ({100*rep['hidden_share']:.1f}%)")
    print(f"  busiest pixel {rep['max']} photographs -> {rep['max_side_px']} px "
          f"side; {rep['pixels_ge_10']:,} pixels hold "
          f"{rep['photos_in_pixels_ge_10']:,} photographs")

    nodes, ways = load_overpass("data/hanoi_osm.json.gz")
    include = None
    if not include_paths:
        skip = {"footway", "path", "steps", "cycleway", "bridleway", "corridor"}
        include = lambda t: t.get("highway") not in skip
    img, nw = draw_basemap(frame, nodes, ways, include=include)
    print(f"  {nw:,} basemap ways stroked")

    from lat.multi import pin_voters
    pins = find_pins(pin_voters(rows), exclude_ids=ov)
    ops = build_marks(rows, labels, frame, pins=pins)
    lines = [(o[1], o[2], o[3], o[4], o[5]) for o in ops if o[0] == "ln"]
    img = draw_density(img, counts, lines, marks=marks)

    os.makedirs(OUT, exist_ok=True)
    path = f"{OUT}/hanoi_density_{which}_{size}.png"
    img.save(path)
    print(f"  {len(lines):,} connecting lines")
    print(f"wrote {path}")
    json.dump({"dataset": which, "frame": repr(frame),
               "marks": len(counts), "lines": len(lines),
               "sizing": "side = 3*sqrt(distinct photographers of that class "
                         "in a 16 px cell), capped at 41 px; cells with one "
                         "photographer get no square",
               "popularity": prep, "stacking": rep},
              open(f"{OUT}/stats_{which}.json", "w"), indent=1)
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["single", "merged"])
    ap.add_argument("--size", type=int, default=SIZE)
    ap.add_argument("--include-paths", action="store_true")
    a = ap.parse_args()
    main(a.which, a.size, a.include_paths)
