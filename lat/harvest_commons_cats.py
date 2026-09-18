"""Find Commons photographs OF Hanoi that carry no coordinate.

The geosearch harvest can only return files someone already geotagged. The
Hanoi category tree holds far more: 163 of 355 files in "Buildings in Hanoi"
and 94 of 124 in "People of Hanoi" have no coordinate at all. Those are real
photographs of the city that the map cannot place, which is exactly the job the
visual-geolocation pass already does for bad Flickr geotags.

This walks the category tree and records the uncoordinated files, with their
uploader and date, so a vision pass can place them and they can then enter the
map like any other row.

Category trees on Commons leak: Hanoi reaches Vietnam reaches Asia within a
couple of hops. So the walk is depth-limited, refuses categories whose title
does not look Hanoi-related once past depth 1, and caps total work.

    PYTHONPATH=. .venv/bin/python lat/harvest_commons_cats.py [--depth 3]
"""
import argparse
import csv
import os
import re
import time
from collections import deque

import requests

API = "https://commons.wikimedia.org/w/api.php"
UA = "hanoi-locals-tourists/1.0 (+https://github.com/weebao/hanoi-local-tourist-heatmap)"
OUT = "data/multi/commons_nocoord.tsv"

ROOTS = [
    "Category:Hanoi",
    "Category:Buildings in Hanoi",
    "Category:Streets in Hanoi",
    "Category:People of Hanoi",
    "Category:Culture of Hanoi",
    "Category:Transport in Hanoi",
    "Category:Parks in Hanoi",
    "Category:Markets in Hanoi",
    "Category:Religious buildings in Hanoi",
    "Category:Hoan Kiem District",
]
# Past the roots, a category has to still be about Hanoi or we are walking out
# into Vietnam and then Asia.
KEEP = re.compile(r"hanoi|ha noi|hà nội|hoan kiem|hoàn kiếm|ba dinh|ba đình|"
                  r"dong da|đống đa|tay ho|tây hồ|long bien|long biên|"
                  r"hai ba trung|hai bà trưng|cau giay|cầu giấy|thanh xuan|"
                  r"hoang mai|hoàng mai|van mieu|văn miếu|thang long|thăng long",
                  re.I)
PHOTO = re.compile(r"\.(jpe?g|png|tiff?|webp)$", re.I)


def api(session, **params):
    p = {"action": "query", "format": "json", "formatversion": "2",
         "maxlag": "5"}
    p.update(params)
    for _ in range(4):
        try:
            r = session.get(API, params=p, timeout=60)
            if r.status_code == 200:
                d = r.json()
                if "error" not in d:
                    return d
            time.sleep(4)
        except Exception:
            time.sleep(4)
    return {}


def walk(session, depth=3, max_cats=400, pause=0.25):
    """-> (files_without_coords, stats). Each file: dict with title/user/date."""
    seen_cat, seen_file = set(), set()
    out = []
    n_with, n_cats = 0, 0
    q = deque((c, 0) for c in ROOTS)
    while q and n_cats < max_cats:
        cat, d = q.popleft()
        if cat in seen_cat:
            continue
        seen_cat.add(cat)
        n_cats += 1
        cont = None
        while True:
            kw = dict(generator="categorymembers", gcmtitle=cat,
                      gcmtype="file|subcat", gcmlimit="500",
                      prop="coordinates|imageinfo", colimit="max",
                      iiprop="timestamp|extmetadata",
                      iiextmetadatafilter="DateTimeOriginal|Artist")
            if cont:
                kw.update(cont)
            doc = api(session, **kw)
            pages = doc.get("query", {}).get("pages", []) or []
            for pg in pages:
                title = pg.get("title", "")
                if title.startswith("Category:"):
                    if d + 1 <= depth and (d == 0 or KEEP.search(title)):
                        q.append((title, d + 1))
                    continue
                if not PHOTO.search(title) or title in seen_file:
                    continue
                seen_file.add(title)
                if pg.get("coordinates"):
                    n_with += 1
                    continue
                ii = (pg.get("imageinfo") or [{}])[0]
                em = ii.get("extmetadata") or {}
                taken = (em.get("DateTimeOriginal") or {}).get("value")
                artist = (em.get("Artist") or {}).get("value") or ""
                artist = re.sub(r"<[^>]+>", "", artist).strip()
                # Flickr-transferred credits sometimes carry the author's
                # email address. It identifies nobody we need to identify.
                artist = re.sub(r"[\w.%+-]+@[\w-]+(\.[\w-]+)+",
                                "[email removed]", artist)
                out.append({
                    "pageid": pg.get("pageid"), "title": title,
                    "user": artist or "", "date": taken or ii.get("timestamp") or "",
                    "date_kind": "taken" if taken else "uploaded",
                    "category": cat,
                })
            cont = doc.get("continue")
            if not cont:
                break
            time.sleep(pause)
        time.sleep(pause)
        if n_cats % 25 == 0:
            print(f"  {n_cats} categories, {len(out):,} uncoordinated files, "
                  f"{n_with:,} already geotagged, queue {len(q)}", flush=True)
    return out, {"categories": n_cats, "with_coords": n_with,
                 "files_seen": len(seen_file)}


def main(depth=3, max_cats=400):
    s = requests.Session()
    s.headers["User-Agent"] = UA
    files, st = walk(s, depth=depth, max_cats=max_cats)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["pageid", "title", "user", "date", "date_kind", "category"])
        for r in files:
            w.writerow([r["pageid"], r["title"].replace("\t", " "),
                        r["user"].replace("\t", " ")[:120],
                        str(r["date"]).replace("\t", " ")[:40],
                        r["date_kind"], r["category"].replace("\t", " ")])
    named = sum(1 for r in files if r["user"])
    dated = sum(1 for r in files if r["date"])
    print(f"\nDONE {st['categories']} categories, {st['files_seen']:,} files seen")
    print(f"  {st['with_coords']:,} already geotagged (the geosearch harvest has these)")
    print(f"  {len(files):,} with NO coordinate -> {OUT}")
    print(f"  of those: {named:,} name an author, {dated:,} carry a date")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--max-cats", type=int, default=400)
    a = ap.parse_args()
    main(a.depth, a.max_cats)
