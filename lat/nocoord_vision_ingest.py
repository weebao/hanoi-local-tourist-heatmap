"""Turn the vision pass's place names into coordinates.

The vision agents name a place per contact-sheet cell and never guess a
coordinate. This geocodes those names with the same specificity guard the
title route uses, keeps only points inside the drawn box, and joins the
uploader so the row can be coloured by the Commons history we already hold.

Run only when no other geocoding job is alive: the Nominatim cache is a single
JSON file rewritten whole on every save.
"""
import csv
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lat.fischer import HANOI_BOUNDS
from lat.geocode import geocode_specific, plausible, _load

VERDICTS = "data/multi/nocoord_verdicts/*.json"
MANIFEST = "data/multi/nocoord/manifest.json"
UPLOADERS = "data/multi/commons_nocoord_uploaders.tsv"
NOCOORD = "data/multi/commons_nocoord.tsv"
OUT = "data/multi/commons_vision_located.tsv"
REJ = "data/multi/commons_vision_rejected.tsv"
MIN_CONFIDENCE = 0.7


def _meta():
    """pageid -> title/date, from the manifest if it survives, else the crawl."""
    meta = {}
    for r in csv.DictReader(open(NOCOORD, newline=""), delimiter="\t"):
        meta[r["pageid"]] = {"title": r["title"], "date": r.get("date", ""),
                             "date_kind": r.get("date_kind", "taken")}
    return meta


def _uploaders():
    if not os.path.exists(UPLOADERS):
        return {}
    return {r["pageid"]: r for r in
            csv.DictReader(open(UPLOADERS, newline=""), delimiter="\t")}


def main():
    s_, w_, n_, e_ = HANOI_BOUNDS
    meta, ups, cache = _meta(), _uploaders(), _load()
    kept, rej, seen = [], [], set()
    n_cells = n_located = 0
    for path in sorted(glob.glob(VERDICTS)):
        for v in json.load(open(path)):
            n_cells += 1
            pid = str(v.get("pageid", ""))
            if pid in seen or pid not in meta:
                rej.append((pid, "", "unknown or duplicate pageid"))
                continue
            seen.add(pid)
            if v.get("verdict") != "located":
                continue
            n_located += 1
            place = (v.get("place") or "").strip()
            conf = float(v.get("confidence") or 0)
            if conf < MIN_CONFIDENCE:
                rej.append((pid, place, f"confidence {conf:.2f} < {MIN_CONFIDENCE}"))
                continue
            g = geocode_specific(place, cache)
            if not g:
                rej.append((pid, place, "no specific feature found"))
                continue
            ok, why = plausible(place, g)
            if not ok:
                rej.append((pid, place, why))
                continue
            if not (w_ <= g[0] <= e_ and s_ <= g[1] <= n_):
                rej.append((pid, place, f"outside drawn box {g[0]:.4f},{g[1]:.4f}"))
                continue
            u, m = ups.get(pid, {}), meta[pid]
            date = u.get("datetimeoriginal") or m["date"]
            kept.append([pid, m["title"].replace("\t", " "),
                         u.get("user", ""), u.get("userid", ""), date,
                         m["date_kind"] if date == m["date"] else "taken",
                         f"{g[0]:.6f}", f"{g[1]:.6f}", "vision", f"{conf:.2f}",
                         place, g[2][:90].replace("\t", " "), f"{g[3]}/{g[4]}",
                         (v.get("evidence") or "").replace("\t", " ")[:160]])

    with open(OUT, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["pageid", "title", "user", "userid", "date", "date_kind",
                    "lon", "lat", "method", "confidence", "place", "resolved",
                    "osm_kind", "evidence"])
        w.writerows(kept)
    with open(REJ, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["pageid", "place", "reason"])
        w.writerows(rej)
    no_user = sum(1 for k in kept if not k[2])
    print(f"{n_cells:,} cells, {n_located:,} located by vision, "
          f"{len(kept):,} geocoded inside the box -> {OUT}")
    print(f"  {len(rej):,} rejected -> {REJ}; {no_user:,} kept rows lack an uploader")


if __name__ == "__main__":
    main()
