"""Render the same data with popularity made visible.

Fischer's marks are opaque 3x3 squares, so N photographs on one spot draw
exactly like one. That is faithful, and at his data volume it is also legible:
with hundreds of thousands of points a busy place spreads across contiguous
pixels, so frequency reads as area. At our volume it does not spread, it
stacks: 70.8% of the single-source photographs and 48.4% of the merged ones
sit under another point.

So this module is a deliberate departure from the spec, kept separate from it.
Under the ordinary points it lays one square per 16 px ground cell per class:

    side(n) = 3 * sqrt(n), capped at 41 px, n = DISTINCT PHOTOGRAPHERS

sqrt because perceived quantity tracks area. n counts photographers, not
photographs: the first version counted photographs on a pixel, and an audit
found that 44 of its 50 largest squares held one photographer (rank correlation
0.06 with the number of people). See popularity_marks(). A cell with a single
photographer gets no square, so a lone photographer is drawn exactly as Fischer
draws them and the two maps agree wherever nobody else went.

Squares go down largest first and every photograph is then drawn on top as a
3x3 point, so nothing small is buried. Colours, projection, bounds, basemap and
connecting lines are unchanged.
"""
import math
import random
from collections import Counter, defaultdict

from PIL import Image, ImageDraw

from lat.fischer import (COLORS, LINE_ALPHA, _ground_metres, BASEMAP, BG)

# 3 px at one photograph, matching the faithful map exactly, and area
# proportional to count from there.
BASE_SIDE = 3.0
# A 41 px side is ~160 m on the ground at 3.95 m/px, which is about the extent
# of a real landmark like the Temple of Literature grounds. Beyond that the
# mark stops describing a place and starts describing the pin.
MAX_SIDE = 41.0


def side_for(n, base=BASE_SIDE, cap=MAX_SIDE):
    return min(cap, base * math.sqrt(max(1, n)))


def pixel_counts(rows, frame, labels):
    """-> {(class, x, y): count} over rows that land on the canvas."""
    c = Counter()
    for r in rows:
        if not frame.contains(r["lon"], r["lat"]):
            continue
        x, y = frame.to_px(r["lon"], r["lat"])
        lab = labels[r["user"]] if isinstance(labels.get(r["user"]), str) \
            else labels[r["user"]][0]
        c[(lab, int(round(x)), int(round(y)))] += 1
    return c


CELL_PX = 16   # ~63 m at 3.95 m/px: about one street corner or one gate


def _label(labels, user):
    v = labels.get(user)
    return v if isinstance(v, str) else v[0]


def popularity_marks(rows, frame, labels, cell=CELL_PX):
    """-> [(side, class, cx, cy, n_photographers, n_photos)], one per (cell,
    class) that at least two photographers of that class photographed.

    The first version sized a square by the PHOTOGRAPHS on one pixel. An audit
    measured what that shows: of the 50 largest squares 44 had one
    photographer, and the rank correlation between photographs and distinct
    photographers was 0.06. It drew "somebody uploaded 200 frames from one
    spot", not "people come here". Exact-pixel coincidence between different
    people is also mostly artefact - a place-picker pin or a geocoded centroid.
    So popularity is counted over a small ground cell, in distinct
    photographers, and a lone photographer never earns more than the ordinary
    3x3 point however many frames they shot.
    """
    users, photos, sx, sy = defaultdict(set), Counter(), Counter(), Counter()
    for r in rows:
        if not frame.contains(r["lon"], r["lat"]):
            continue
        x, y = frame.to_px(r["lon"], r["lat"])
        k = (_label(labels, r["user"]), int(x // cell), int(y // cell))
        users[k].add(r["user"]); photos[k] += 1; sx[k] += x; sy[k] += y
    out = []
    for k, u in users.items():
        if len(u) < 2:
            continue
        n = photos[k]
        out.append((side_for(len(u)), k[0], sx[k] / n, sy[k] / n, len(u), n))
    return out


def popularity_report(marks, rows_on_canvas):
    import numpy as np
    n = np.array([m[4] for m in marks]) if marks else np.array([0])
    top = sorted(marks, key=lambda m: -m[4])[:50]
    return {
        "cell_px": CELL_PX,
        "squares": len(marks),
        "photographs_on_canvas": rows_on_canvas,
        "photographers_in_largest_square": int(n.max()),
        "median_photographers_top50": int(np.median([m[4] for m in top])) if top else 0,
        "min_photographers_top50": int(min(m[4] for m in top)) if top else 0,
        "max_side_px": round(float(max((m[0] for m in marks), default=0)), 1),
    }


def draw_density(img, counts, lines=(), marks=(), seed=20100615,
                 line_alpha=LINE_ALPHA):
    """Lines as in the faithful renderer, then popularity squares, then points.

    `marks` come from popularity_marks(); `counts` from pixel_counts() and are
    used only for WHERE the photographs are.
    """
    import numpy as np

    rng = random.Random(seed)
    base_arr = np.asarray(img).astype(np.float32)

    by_class = defaultdict(list)
    for x0, y0, x1, y1, col in lines:
        by_class[col].append((x0, y0, x1, y1))
    S = img.size[0]
    for col in sorted(by_class):
        acc = np.zeros((S, S), dtype=np.int32)
        for x0, y0, x1, y1 in sorted(by_class[col]):
            n = max(abs(int(round(x1)) - int(round(x0))),
                    abs(int(round(y1)) - int(round(y0))))
            if n == 0:
                xs = np.array([int(round(x0))]); ys = np.array([int(round(y0))])
            else:
                t = np.arange(n + 1, dtype=float) / n
                xs = np.round(x0 + (x1 - x0) * t).astype(np.int64)
                ys = np.round(y0 + (y1 - y0) * t).astype(np.int64)
            ok = (xs >= 0) & (xs < S) & (ys >= 0) & (ys < S)
            if ok.any():
                np.add.at(acc, (ys[ok], xs[ok]), 1)
        hit = acc > 0
        if hit.any():
            a = 1.0 - np.power(1.0 - line_alpha, acc[hit].astype(np.float32))
            c = np.array(col, dtype=np.float32)
            base_arr[hit] = (base_arr[hit] * (1.0 - a)[:, None]
                             + c[None, :] * a[:, None])

    out = Image.fromarray(np.clip(np.round(base_arr), 0, 255).astype(np.uint8),
                          "RGB")
    d = ImageDraw.Draw(out)
    # Largest first, so a small square is painted over a big one and not the
    # reverse. (The first version sorted ascending while its docstring claimed
    # the opposite; 1,720 marks ended up under a different colour.)
    for side, lab, x, y, _u, _n in sorted(marks, key=lambda m: (-m[0], m[2], m[3])):
        h = side / 2.0
        d.rectangle([int(round(x - h)), int(round(y - h)),
                     int(round(x + h)), int(round(y + h))], fill=COLORS[lab])
    # then every photograph as the faithful renderer's 3x3 point, on top, in a
    # seeded shuffle so no class systematically covers another
    pts = [(lab, x, y) for (lab, x, y) in counts]
    pts.sort(); rng.shuffle(pts)
    for lab, x, y in pts:
        d.rectangle([x - 1, y - 1, x + 1, y + 1], fill=COLORS[lab])
    return out


def stacking_report(counts):
    """What the frequency encoding is actually showing."""
    import numpy as np
    v = np.array(sorted(counts.values()))
    tot = int(v.sum())
    return {
        "photos": tot,
        "distinct_pixels": len(v),
        "hidden_by_opaque_render": tot - len(v),
        "hidden_share": (tot - len(v)) / tot if tot else 0.0,
        "median": int(np.median(v)), "p99": int(np.percentile(v, 99)),
        "max": int(v.max()) if len(v) else 0,
        "pixels_ge_10": int((v >= 10).sum()),
        "photos_in_pixels_ge_10": int(v[v >= 10].sum()) if len(v) else 0,
        "max_side_px": round(side_for(int(v.max()) if len(v) else 1), 1),
    }
