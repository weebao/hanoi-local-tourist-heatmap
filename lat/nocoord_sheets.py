"""Build contact sheets for Commons photographs of Hanoi that carry no
coordinate, so a vision pass can place them.

Disk hygiene is part of the design, not an afterthought: each thumbnail is
deleted as soon as it has been pasted into a sheet, so peak usage is one batch
of thumbnails rather than the whole corpus. The sheet keeps the pixels the
vision pass needs; the originals are on Commons and never needed again.

    PYTHONPATH=. .venv/bin/python lat/nocoord_sheets.py [--limit N] [--per 15]
"""
import argparse
import csv
import json
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from PIL import Image, ImageDraw

SRC = "data/multi/commons_nocoord.tsv"
OUT = "data/multi/nocoord"
UA = "hanoi-locals-tourists/1.0 (+https://github.com/weebao/hanoi-local-tourist-heatmap)"
THUMB = "https://commons.wikimedia.org/wiki/Special:FilePath/{}?width=460"


NOISE = re.compile(r"tower[s]? of hanoi|hanoiturm|torres? de hanoi|"
                   r"tours? de hano[i\u00ef]|\bmtoh\b|coat of arms|"
                   r"\.svg$|stamp of ", re.I)


def already_located():
    """pageids the cheaper routes already placed, so vision is not spent twice."""
    done = set()
    for path, col in (("data/multi/commons_located.tsv", "pageid"),
                      ("data/multi/commons_objloc.tsv", "id")):
        if not os.path.exists(path):
            continue
        with open(path, newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                if r.get(col):
                    done.add(str(r[col]))
    return done


def load(limit=None):
    done = already_located()
    rows, skipped_noise, skipped_done, undated = [], 0, 0, 0
    with open(SRC, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            t = r.get("title") or ""
            if not t.startswith("File:"):
                continue
            if NOISE.search(t):
                skipped_noise += 1
                continue
            if str(r.get("pageid")) in done:
                skipped_done += 1
                continue
            # No date means the row can be a point but never a colour, so it is
            # the last thing worth a vision pass.
            if not (r.get("date") or "").strip():
                undated += 1
                continue
            r["fname"] = t[5:]
            rows.append(r)
    print(f"  candidates {len(rows):,}  (skipped {skipped_noise} noise, "
          f"{skipped_done} already located, {undated} undated)")
    # A dated file is worth more: with a coordinate from sight plus a date and
    # an uploader it becomes a full row, whereas an undated one can only ever
    # be an uncoloured point.
    rows.sort(key=lambda r: (not r.get("date"), r.get("title", "")))
    return rows[:limit] if limit else rows


def fetch(session, row, tmp, pause=0.7):
    """One thumbnail, politely.

    Bulk-fetching these concurrently does not work and should not be done:
    750 requests across 8 workers got roughly 100 through before Wikimedia
    throttled the rest, which is the infrastructure telling us to slow down.
    One request at a time with a pause and a backoff is both effective and the
    behaviour their policy asks for.
    """
    path = os.path.join(tmp, f"{row['pageid']}.jpg")
    url = THUMB.format(row["fname"].replace(" ", "_"))
    for attempt in range(3):
        try:
            r = session.get(url, timeout=40)
            if r.status_code == 200 and len(r.content) > 2000:
                with open(path, "wb") as f:
                    f.write(r.content)
                time.sleep(pause)
                return path
            if r.status_code in (429, 503):
                time.sleep(5 * (attempt + 1))
                continue
            break
        except Exception:
            time.sleep(2 * (attempt + 1))
    time.sleep(pause)
    return None


def build(limit=None, per=15, cols=5, cell=300, workers=4):
    rows = load(limit)
    os.makedirs(OUT, exist_ok=True)
    tmp = os.path.join(OUT, "_tmp")
    session = requests.Session()
    session.headers["User-Agent"] = UA
    manifest, made, fetched = {}, 0, 0

    for start in range(0, len(rows), per):
        chunk = rows[start:start + per]
        os.makedirs(tmp, exist_ok=True)
        paths = [fetch(session, r, tmp) for r in chunk]
        ok = [(r, p) for r, p in zip(chunk, paths) if p]
        fetched += len(ok)
        if ok:
            n = (len(ok) + cols - 1) // cols
            sheet = Image.new("RGB", (cols * cell, n * (cell + 30)), "white")
            d = ImageDraw.Draw(sheet)
            for i, (r, p) in enumerate(ok):
                cx, cy = (i % cols) * cell, (i // cols) * (cell + 30)
                try:
                    im = Image.open(p).convert("RGB")
                except Exception:
                    continue
                im.thumbnail((cell - 8, cell - 8))
                sheet.paste(im, (cx + 4, cy + 26))
                d.text((cx + 5, cy + 4), f"{i+1}. id={r['pageid']}", fill="black")
                d.text((cx + 5, cy + 15),
                       (r.get("title", "")[5:])[:44], fill=(90, 90, 90))
            name = os.path.join(OUT, f"nocoord_{start//per:04d}.png")
            sheet.save(name)
            manifest[os.path.basename(name)] = [
                {"pageid": r["pageid"], "title": r["title"],
                 "artist": r.get("user", ""), "date": r.get("date", ""),
                 "date_kind": r.get("date_kind", "")} for r, _ in ok]
            made += 1
        # the point of the exercise: drop the thumbnails immediately
        shutil.rmtree(tmp, ignore_errors=True)
        time.sleep(0.4)   # Commons throttled an 8-worker burst of 750
        if made and made % 5 == 0:
            print(f"  {made} sheets, {fetched} images fetched and discarded",
                  flush=True)

    json.dump(manifest, open(os.path.join(OUT, "manifest.json"), "w"), indent=1)
    print(f"DONE {made} sheets from {fetched} images; thumbnails deleted")
    print(f"  {OUT}/manifest.json maps each sheet to its pageids")
    return made


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--per", type=int, default=15)
    a = ap.parse_args()
    build(a.limit, a.per)
