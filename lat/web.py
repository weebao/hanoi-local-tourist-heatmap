"""Extract the map as geometry for the static web viewer in docs/.

The 6137 px PNGs are the deliverable; this is the same map as data. Nothing
here re-decides anything: the marks come out of `lat.fischer.build_marks`
itself (the same time/distance/speed/accuracy/pin gates), so the point and
line counts must match out/stats.json and out/multi/stats.json exactly, and
the build asserts it.

Only the projection is left to the viewer. build_marks returns canvas pixels,
so the pixels are inverted back through the same EquirectFrame to lon/lat -
an exact linear inverse - and MapLibre projects them itself.

Encoding. GeoJSON of the basemap at 5 decimals is ~3x larger than it needs to
be, and the page has a byte budget, so every file here is flat arrays of
integers in units of 1e-5 degrees, delta-coded, which docs/app.js expands into
GeoJSON in the browser. Fields:

    scale   integer units per degree (100000)
    off     [x, y] added back to every decoded coordinate
    d       flat integers; see enc_* below for the three layouts

Run one stage per process: the Overpass extract alone costs ~1.2 GB resident.

    .venv/bin/python lat/web.py basemap
    .venv/bin/python lat/web.py faithful
    .venv/bin/python lat/web.py merged
"""
import json
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lat.fischer import (EquirectFrame, HANOI_BOUNDS, SIZE, COLORS,
                         build_marks, find_pins, _pin_key)

SCALE = 100000                  # 1e-5 deg: 1.11 m in latitude, 1.04 m here
OUT_DIR = "docs/data"
# The basemap is carried a little past the drawn box so that panning to the
# edge of the viewer's max bounds does not show bare white.
DATA_PAD = 0.03                 # degrees, ~3.3 km
SIMPLIFY_M = 1.0                # Douglas-Peucker tolerance, a quarter pixel
BASEMAP_SKIP = {"footway", "path", "steps", "cycleway", "bridleway",
                "corridor"}     # exactly draw_basemap's default in the builds
BASEMAP_TAGS = {"highway", "waterway", "natural", "landuse"}
# The sources that produced the 42,394-point merged map (out/multi/stats.json).
# Named explicitly rather than taken from multi.enabled_sources() so that a
# harvest landing a new *_hanoi.tsv mid-run cannot silently change the page.
MERGED_SOURCES = ["flickr", "commons", "commonsplaced", "inat"]

S, W, N, E = HANOI_BOUNDS
OFF = (round(W * SCALE), round(S * SCALE))
CLASS_OF_COLOR = {v: k for k, v in COLORS.items()}


def q(lon, lat):
    """lon/lat -> integer grid coordinate (5 decimals), origin at the box SW."""
    return round(lon * SCALE) - OFF[0], round(lat * SCALE) - OFF[1]


# ------------------------------------------------------------------ encoding
def enc_points(pts):
    """[(x, y)] -> flat deltas, sorted. Order is irrelevant: the points are
    opaque and same-coloured within a group, and app.js reshuffles the three
    classes together to keep the original's interleaving."""
    out = []
    px = py = 0
    for x, y in sorted(pts):
        out += [x - px, y - py]
        px, py = x, y
    return out


def enc_segs(segs):
    """[(x0, y0, x1, y1)] -> flat: start delta-coded, end relative to start."""
    out = []
    px = py = 0
    for x0, y0, x1, y1 in sorted(segs):
        out += [x0 - px, y0 - py, x1 - x0, y1 - y0]
        px, py = x0, y0
    return out


def enc_polylines(pls):
    """[[(x, y), ...]] -> flat: count, first point absolute, then deltas."""
    out = []
    for pl in pls:
        out.append(len(pl))
        px = py = 0
        for i, (x, y) in enumerate(pl):
            out += [x, y] if i == 0 else [x - px, y - py]
            px, py = x, y
    return out


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    n = os.path.getsize(path)
    print(f"wrote {path}  {n:,} bytes")
    return n


# ---------------------------------------------------------------- simplifying
def _dp(pts, tol_x, tol_y, tol):
    """Douglas-Peucker on grid coordinates, tolerance in metres.

    tol_x / tol_y convert a grid unit to metres, so the test is on the ground
    and not in degrees (a degree of longitude here is 0.93 of a degree of
    latitude)."""
    n = len(pts)
    if n < 3:
        return pts
    keep = [False] * n
    keep[0] = keep[n - 1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        x1, y1 = pts[i][0] * tol_x, pts[i][1] * tol_y
        x2, y2 = pts[j][0] * tol_x, pts[j][1] * tol_y
        dx, dy = x2 - x1, y2 - y1
        dd = dx * dx + dy * dy
        best, bi = -1.0, -1
        for k in range(i + 1, j):
            px, py = pts[k][0] * tol_x, pts[k][1] * tol_y
            if dd == 0.0:
                d = math.hypot(px - x1, py - y1)
            else:
                t = ((px - x1) * dx + (py - y1) * dy) / dd
                t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
                d = math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
            if d > best:
                best, bi = d, k
        if best > tol:
            keep[bi] = True
            stack.append((i, bi))
            stack.append((bi, j))
    return [p for p, k in zip(pts, keep) if k]


def _dedupe(pts):
    out = [pts[0]]
    for p in pts[1:]:
        if p != out[-1]:
            out.append(p)
    return out


# ------------------------------------------------------------------- basemap
def basemap(out_dir=OUT_DIR, osm="data/hanoi_osm.json.gz", pad=DATA_PAD):
    """Every way draw_basemap would stroke, as simplified polylines."""
    from lat.basemap import load_overpass

    print(f"loading {osm}")
    nodes, ways = load_overpass(osm)
    print(f"  {len(nodes):,} nodes  {len(ways):,} ways")

    s, w, n, e = S - pad, W - pad, N + pad, E + pad
    # metres per grid unit, at the box centre
    mlat = 111320.0 / SCALE
    mlon = mlat * math.cos(math.radians((S + N) / 2))

    pls, n_ways, v_in, v_out = [], 0, 0, 0
    for way in ways:
        tags = way.get("tags") or {}
        if tags.get("highway") in BASEMAP_SKIP:
            continue
        if not (BASEMAP_TAGS & tags.keys()):
            continue
        pts = []
        for r in (way.get("nodes") or []):
            nd = nodes.get(r)
            if nd is not None:
                pts.append(nd)
        if len(pts) < 2:
            continue
        n_ways += 1
        v_in += len(pts)
        # Keep any segment whose bounding box meets the padded box, and break
        # the way wherever a run of kept segments stops. Segments are kept
        # whole rather than cut at the boundary: a few hundred metres of
        # overdraw off-screen is cheaper than an intersection routine.
        run = []
        for a, b in zip(pts, pts[1:]):
            if (max(a[0], b[0]) >= w and min(a[0], b[0]) <= e
                    and max(a[1], b[1]) >= s and min(a[1], b[1]) <= n):
                if not run:
                    run.append(q(*a))
                run.append(q(*b))
            elif run:
                pls.append(run)
                run = []
        if run:
            pls.append(run)

    simp = []
    for pl in pls:
        pl = _dedupe(pl)
        if len(pl) < 2:
            continue
        pl = _dp(pl, mlon, mlat, SIMPLIFY_M)
        simp.append(pl)
        v_out += len(pl)
    print(f"  {n_ways:,} ways stroked by the renderer, {v_in:,} vertices")
    print(f"  clipped to the box + {pad} deg and simplified at {SIMPLIFY_M} m: "
          f"{len(simp):,} polylines, {v_out:,} vertices "
          f"({v_out / max(v_in, 1) * 100:.0f}% of the input)")

    return write_json(os.path.join(out_dir, "basemap.json"), {
        "kind": "basemap", "scale": SCALE, "off": list(OFF),
        "bounds": list(HANOI_BOUNDS), "pad": pad,
        "lines": len(simp), "vertices": v_out,
        "simplify_m": SIMPLIFY_M,
        "note": ("OSM ways with a highway/waterway/natural/landuse tag, minus "
                 + "/".join(sorted(BASEMAP_SKIP))
                 + "; polyline layout: count, first point, then deltas"),
        "d": enc_polylines(simp),
    })


# ---------------------------------------------------------------- mark export
def _marks(rows, labels, frame, pins):
    """-> (points, segments, photographers_on_map) in lon/lat.

    Points are read off the rows rather than the ops so that each one can
    carry its source; the assertion below is that this is the same set.
    """
    ops = build_marks(rows, labels, frame, pins=pins)
    n_pt = sum(1 for o in ops if o[0] == "pt")
    segs = []
    for o in ops:
        if o[0] != "ln":
            continue
        _t, x0, y0, x1, y1, col = o
        segs.append((_unproject(frame, x0, y0), _unproject(frame, x1, y1),
                     CLASS_OF_COLOR[col]))
    pts = [(r["lon"], r["lat"], labels[r["user"]], r.get("src", "flickr"))
           for r in rows if frame.contains(r["lon"], r["lat"])]
    assert len(pts) == n_pt, f"{len(pts)} rows on canvas vs {n_pt} point ops"
    # Photographers WITH A MARK, which is the column the README publishes.
    # Counting everyone classified (960) or everyone with a loaded row (3,051)
    # describes a population the page does not draw.
    on_map = defaultdict(set)
    for r in rows:
        if frame.contains(r["lon"], r["lat"]):
            on_map[labels[r["user"]]].add(r["user"])
    return pts, segs, {k: len(v) for k, v in sorted(on_map.items())}


def _unproject(frame, x, y):
    return (frame.w + x / frame.size * frame.dlon,
            frame.n - y / frame.size * frame.dlat)


def write_marks(path, pts, segs, meta):
    groups = {}
    for lon, lat, cls, src in pts:
        groups.setdefault((cls, src), []).append(q(lon, lat))
    lines = {}
    for (lon0, lat0), (lon1, lat1), cls in segs:
        x0, y0 = q(lon0, lat0)
        x1, y1 = q(lon1, lat1)
        lines.setdefault(cls, []).append((x0, y0, x1, y1))

    doc = dict(meta)
    doc.update({
        "scale": SCALE, "off": list(OFF), "bounds": list(HANOI_BOUNDS),
        "points": [{"class": c, "source": s, "n": len(v), "d": enc_points(v)}
                   for (c, s), v in sorted(groups.items())],
        "lines": [{"class": c, "n": len(v), "d": enc_segs(v)}
                  for c, v in sorted(lines.items())],
        "counts": {"points": len(pts), "lines": len(segs)},
    })
    for c, s in sorted(groups):
        print(f"  {c:8s} {s:14s} {len(groups[(c, s)]):>7,}")
    for c in sorted(lines):
        print(f"  lines {c:8s} {len(lines[c]):>7,}")
    return write_json(path, doc)


# ------------------------------------------------------------------ faithful
def faithful(out_dir=OUT_DIR, size=SIZE):
    """The Flickr-only map: the data path of lat/build_fischer.py, unchanged."""
    from collections import defaultdict
    from lat.build import load_hanoi, load_user_history
    from lat.classify import classify_users

    overrides, exclude = {}, []
    if os.path.exists("data/reloc/overrides.json"):
        overrides = {k: tuple(v) for k, v in
                     json.load(open("data/reloc/overrides.json")).items()}
    if os.path.exists("data/reloc/exclude.json"):
        exclude = json.load(open("data/reloc/exclude.json"))
    print(f"loaded {len(overrides)} relocations, {len(exclude)} exclusions")

    hanoi = load_hanoi(overrides=overrides, exclude=exclude)
    hist = load_user_history({r["user"] for r in hanoi})

    s_, w_, n_, e_ = HANOI_BOUNDS

    def in_city(lon, lat):
        return w_ <= lon <= e_ and s_ <= lat <= n_

    stale = {(r["user"], r["date"].date(), round(r["orig_lon"], 3),
              round(r["orig_lat"], 3)) for r in hanoi}
    hist_kept = [h for h in hist
                 if (h["user"], h["date"].date(), round(h["lon"], 3),
                     round(h["lat"], 3)) not in stale]
    recs = hist_kept + [{"user": r["user"], "date": r["date"], "lon": r["lon"],
                         "lat": r["lat"]} for r in hanoi]
    print(f"classifying {len({r['user'] for r in hanoi})} photographers over "
          f"{len(recs):,} records")
    labels = {u: v[0] for u, v in
              classify_users(recs, in_city, city_bounds=HANOI_BOUNDS).items()}
    cu = defaultdict(int)
    for lab in labels.values():
        cu[lab] += 1
    print("  " + "  ".join(f"{k} {v}" for k, v in sorted(cu.items())))

    masked = set()
    if os.path.exists("data/reloc/masked_ids.json"):
        masked = set(json.load(open("data/reloc/masked_ids.json")))
    draw = [r for r in hanoi if not (r["id"] in masked and r["id"] not in overrides)]
    print(f"  {len(hanoi) - len(draw)} photos masked on discredited pins")

    frame = EquirectFrame(HANOI_BOUNDS, size)
    pins = find_pins(draw, exclude_ids=overrides)
    print(f"  {len(pins)} shared place-pin coordinates")
    pts, segs, on_map = _marks(draw, labels, frame, pins)
    print(f"  {len(pts):,} points + {len(segs):,} connecting lines")
    _check("out/stats.json", len(pts), len(segs))
    return write_marks(os.path.join(out_dir, "faithful.json"), pts, segs, {
        "kind": "faithful",
        "label": "Flickr only (YFCC100M)",
        "photographers": on_map,
        "photographers_classified": {k: cu[k] for k in sorted(cu)},
    })


# -------------------------------------------------------------------- merged
def merged(out_dir=OUT_DIR, size=SIZE, sources=MERGED_SOURCES):
    """The multi-source map: lat.multi.merge, as lat/build_multi.py calls it."""
    from collections import Counter
    from lat import multi

    print(f"merging {sources}")
    m = multi.merge(multi.MULTI_DIR, cap=None, sources=sources, verbose=True)
    rows, labels = m["rows"], m["labels"]
    frame = EquirectFrame(HANOI_BOUNDS, size)
    pins = find_pins(multi.pin_voters(rows))
    print(f"  {len(pins)} shared place-pin coordinates "
          f"({sum(1 for r in rows if _pin_key(r) in pins)} photos)")
    # merge() leaves a row's label off only when no residency test was
    # possible; build_multi reads that as UNKNOWN and so does this.
    labels = {u: labels.get(u, "unknown") for u in {r["user"] for r in rows}}
    pts, segs, on_map = _marks(rows, labels, frame, pins)
    print(f"  {len(pts):,} points + {len(segs):,} connecting lines")
    _check("out/multi/stats.json", len(pts), len(segs))
    return write_marks(os.path.join(out_dir, "merged.json"), pts, segs, {
        "kind": "merged",
        "label": "Flickr + Commons + iNaturalist",
        "sources": list(sources),
        "photographers": on_map,
    })


def _check(stats_path, n_pts, n_lines):
    """The rendered PNG is the reference; disagreeing with it is a bug here."""
    if not os.path.exists(stats_path):
        print(f"  ! {stats_path} absent: counts not cross-checked")
        return
    st = json.load(open(stats_path))
    want_p = st.get("points_total")
    if want_p is None and isinstance(st.get("points"), dict):
        want_p = sum(st["points"].values())
    want_l = st.get("connecting_lines")
    print(f"  {stats_path}: {want_p:,} points / {want_l:,} lines -> "
          f"{'match' if (want_p, want_l) == (n_pts, n_lines) else 'MISMATCH'}")
    if (want_p, want_l) != (n_pts, n_lines):
        raise SystemExit(
            f"refusing to write: {stats_path} says {want_p} points and "
            f"{want_l} lines, this extraction has {n_pts} and {n_lines}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stage", choices=["basemap", "faithful", "merged"])
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--size", type=int, default=SIZE,
                    help="canvas the marks are gated on; only the pixel "
                         "rounding inside build_marks depends on it")
    a = ap.parse_args()
    if a.stage == "basemap":
        basemap(a.out)
    elif a.stage == "faithful":
        faithful(a.out, a.size)
    else:
        merged(a.out, a.size)
