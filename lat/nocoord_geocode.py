"""Place uncoordinated Commons photographs of Hanoi from their TITLES.

Commons filenames are often written by the photographer and name the subject
outright: "Cổng chùa Hoàng Mai.jpg", "TranQuangKhai street, Hanoi 2025.jpg",
"Công viên hồ Đền Lừ vào buổi tối.jpg". Where that happens a geocoder beats a
vision pass on both cost and precision, so titles are tried first and the
vision pass is reserved for the photographs whose titles say nothing.

Everything resolves through Nominatim bounded to the Hanoi viewbox, so a title
naming somewhere else cannot land a point in Hanoi. Nothing is asserted from
memory.

    PYTHONPATH=. .venv/bin/python lat/nocoord_geocode.py [--limit N]
"""
import argparse
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lat.geocode import geocode_specific, plausible, _load
from lat.fischer import HANOI_BOUNDS

SRC = "data/multi/commons_nocoord.tsv"
OUT = "data/multi/commons_located.tsv"
REJ = "data/multi/commons_located_rejected.tsv"

# The category walk reaches Category:Tower of Hanoi, the mathematical puzzle,
# whose diagrams are not photographs of anywhere. Keep this tight: an earlier,
# looser pattern also threw out legitimate photographs whose titles merely
# mentioned a map or a logo.
NOISE = re.compile(r"tower[s]? of hanoi|hanoiturm|torres? de hanoi|"
                   r"tours? de hano[iï]|\bmtoh\b|coat of arms|"
                   r"\.svg$|stamp of ", re.I)
# A title has to name a place *type* to be worth geocoding; otherwise we are
# feeding a geocoder someone's holiday caption and trusting whatever it says.
PLACE = re.compile(r"(ph[oố]\b|đường|duong\b|ng[oõ]\b|ph[uư][oờ]ng|qu[aậ]n\b|"
                   r"c[aầ]u\b|h[oồ]\b|ch[uù]a\b|đ[eề]n\b|mi[eế]u\b|"
                   r"nh[aà] th[oờ]|tr[uư][oờ]ng\b|b[eệ]nh vi[eệ]n|"
                   r"c[oổ]ng l[aà]ng|vi[eệ]n\b|b[aả]o t[aà]ng|ch[oợ]\b|"
                   r"c[oô]ng vi[eê]n|l[aà]ng\b|"
                   r"\bstreet\b|\broad\b|\blake\b|\bpagoda\b|\btemple\b|"
                   r"\bbridge\b|\bmarket\b|\bmuseum\b|\bstation\b|"
                   r"\buniversity\b|\bhospital\b|\bdistrict\b|\bward\b|"
                   r"\bcathedral\b|\bchurch\b|\bpark\b|\btheatre\b|\btheater\b)",
                  re.I)

STRIP = [
    (re.compile(r"\.(jpe?g|png|tiff?|webp)$", re.I), ""),
    (re.compile(r"\b(19|20)\d{2}\b"), " "),          # years
    (re.compile(r"\(\d[^)]*\)"), " "),               # (3026842639) ids
    (re.compile(r"[_]+"), " "),
    (re.compile(r"\b(img|dsc|dscn|p\d{3,}|\d{4,})\b", re.I), " "),
    (re.compile(r"\s{2,}"), " "),
]


def title_to_query(title):
    q = title[5:] if title.startswith("File:") else title
    for pat, rep in STRIP:
        q = pat.sub(rep, q)
    q = q.strip(" ,-–—.")
    if not q:
        return None
    low = q.lower()
    if "hanoi" not in low and "hà nội" not in low and "ha noi" not in low:
        q = q + ", Hanoi, Vietnam"
    return q


def main(limit=None):
    s_, w_, n_, e_ = HANOI_BOUNDS
    rows = list(csv.DictReader(open(SRC, newline=""), delimiter="\t"))
    cand = [r for r in rows
            if not NOISE.search(r["title"]) and PLACE.search(r["title"])]
    if limit:
        cand = cand[:limit]
    print(f"  {len(rows):,} uncoordinated files; {len(cand):,} titles name a "
          f"place and are worth geocoding")

    cache = _load()
    kept, rej = [], []
    for i, r in enumerate(cand, 1):
        q = title_to_query(r["title"])
        if not q:
            rej.append((r["title"], "", "no query"))
            continue
        g = geocode_specific(q, cache)
        ok, why = plausible(q, g) if g else (False, "")
        if not g:
            rej.append((r["title"], q, "no specific feature found"))
        elif not ok:
            rej.append((r["title"], q, why))
        elif not (w_ <= g[0] <= e_ and s_ <= g[1] <= n_):
            # Outside Fischer's drawn box. Could be greater Hanoi or could be a
            # namesake elsewhere; either way it cannot be drawn, so record it
            # rather than forcing it in.
            rej.append((r["title"], q, f"outside drawn box {g[0]:.4f},{g[1]:.4f}"))
        else:
            kept.append({"pageid": r["pageid"], "title": r["title"],
                         "user": r.get("user", ""), "date": r.get("date", ""),
                         "date_kind": r.get("date_kind", "taken"),
                         "lon": g[0], "lat": g[1], "method": "title",
                         "resolved": g[2][:90], "kind": f"{g[3]}/{g[4]}"})
        if i % 50 == 0:
            print(f"  [{i}/{len(cand)}] located {len(kept):,}", flush=True)

    with open(OUT, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["pageid", "title", "user", "date", "date_kind",
                    "lon", "lat", "method", "resolved", "osm_kind"])
        for k in kept:
            w.writerow([k["pageid"], k["title"].replace("\t", " "),
                        k["user"].replace("\t", " "), k["date"],
                        k["date_kind"], f"{k['lon']:.6f}", f"{k['lat']:.6f}",
                        k["method"], k["resolved"].replace("\t", " "),
                        k["kind"]])
    with open(REJ, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["title", "query", "reason"])
        for t, q, why in rej:
            w.writerow([t.replace("\t", " "), q, why])
    print(f"\nDONE located {len(kept):,} of {len(cand):,} by title -> {OUT}")
    print(f"  {len(rej):,} rejected -> {REJ}")
    return kept


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    main(a.limit)
