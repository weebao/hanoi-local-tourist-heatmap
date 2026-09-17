#!/usr/bin/env python3
"""OpenStreetView-5M (Mapillary-derived, CC-BY-SA) metadata CSV -> data/multi/osv5m_hanoi.tsv
+ osv5m_history.tsv.  Metadata only: the CSV is streamed over HTTP and filtered line by
line; it is never stored, and no image (the thumb_original_url column) is ever requested.

Mapillary's own API/tiles need a token; this open dump is the keyless route. It is a
SAMPLE (~5.1 M of Mapillary's ~2 G images), so absence of a user elsewhere proves nothing.

Columns used: id, latitude, longitude, sequence, captured_at (epoch ms, capture time),
creator_username, creator_id.  User id written as "<creator_id>|<creator_username>".

Default reads test.csv only (116 MB). train.csv is 2.9 GB: pass --train to stream it too
(constant memory; still 2.9 GB of transfer, so it is opt-in).

THINNING RULE (Hanoi rows): at most one row per user per 50 m lattice cell per calendar
day (UTC) of captured_at; earliest capture wins.
History: for every Hanoi contributor, photos outside the box reduced to temporal extremes -
earliest and latest capture per 0.5 degree cell. Memory stays bounded because extremes are
tracked for every creator during the single pass and non-Hanoi creators dropped at the end.

Resumable in the only sense that matters for a single streamed file: a finished split is
recorded in data/multi/osv5m/done.json and skipped on re-run; an interrupted split restarts.

Run:  .venv/bin/python lat/harvest_osv5m.py [--train]
"""
import csv, io, json, math, os, sys, time
from datetime import datetime, timezone
import requests

S, W, N, E = 20.926386, 105.728233, 21.144091, 105.961466
BASE = "https://huggingface.co/datasets/osv5m/osv5m/resolve/main/"
UA = "img-city-heatmap/osv5m-harvester (non-commercial research; metadata only)"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "multi")
ST = os.path.join(ROOT, "osv5m")
os.makedirs(ST, exist_ok=True)
COS = math.cos(math.radians((S + N) / 2))


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def stream(name):
    delay = 10
    for _ in range(6):
        r = requests.get(BASE + name, stream=True, timeout=120, headers={"User-Agent": UA})
        if r.status_code in (429, 503):
            log("backoff", r.status_code, delay)
            time.sleep(delay)
            delay *= 2
            continue
        r.raise_for_status()
        # no quoted field in this CSV spans lines, so line iteration is safe
        return csv.DictReader(l.decode("utf-8", "replace") for l in r.iter_lines(chunk_size=1 << 20))
    raise SystemExit("gave up on " + name)


def run_split(name):
    hanoi, ext, n = [], {}, 0
    for row in stream(name):
        n += 1
        if n % 500000 == 0:
            log(f"  {name}: {n:,} rows, {len(hanoi)} in box")
        try:
            la, lo = float(row["latitude"]), float(row["longitude"])
            ms = int(float(row["captured_at"]))
            cid = str(int(float(row["creator_id"])))
        except (KeyError, TypeError, ValueError):
            continue
        if S <= la <= N and W <= lo <= E:
            hanoi.append([row["id"], cid, row.get("creator_username", ""), ms, lo, la])
        else:
            cell = ext.setdefault(cid, {}).setdefault(
                f"{math.floor(la * 2)},{math.floor(lo * 2)}", [None, None])
            if cell[0] is None or ms < cell[0][0]:
                cell[0] = (ms, lo, la)
            if cell[1] is None or ms > cell[1][0]:
                cell[1] = (ms, lo, la)
    keep = {h[1] for h in hanoi}
    hist = {u: [list(p) for c in cells.values() for p in set(c)] for u, cells in ext.items() if u in keep}
    with open(os.path.join(ST, name + ".json"), "w") as f:
        json.dump({"rows": n, "hanoi": hanoi, "history": hist}, f)
    log(f"{name}: {n:,} rows, {len(hanoi)} in box, {len(keep)} creators")


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write():
    hanoi, hist = [], {}
    for fn in sorted(os.listdir(ST)):
        if fn.endswith(".csv.json"):
            d = json.load(open(os.path.join(ST, fn)))
            hanoi += d["hanoi"]
            for u, pts in d["history"].items():
                hist.setdefault(u, []).extend(pts)
    names = {h[1]: h[2] for h in hanoi}
    hanoi.sort(key=lambda h: (h[1], h[3]))
    seen, rows = set(), 0
    with open(os.path.join(ROOT, "osv5m_hanoi.tsv"), "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["id", "user", "date", "date_kind", "lon", "lat", "accuracy", "url"])
        for pid, cid, uname, ms, lo, la in hanoi:
            d = iso(ms)
            key = (cid, d[:10], int(la * 111320 / 50), int(lo * 111320 * COS / 50))
            if key in seen:
                continue
            seen.add(key)
            rows += 1
            w.writerow([pid, f"{cid}|{uname}", d, "taken", f"{lo:.6f}", f"{la:.6f}", "",
                        f"https://www.mapillary.com/app/?pKey={pid}"])
    hrows = 0
    with open(os.path.join(ROOT, "osv5m_history.tsv"), "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["user", "date", "date_kind", "lon", "lat"])
        for cid in sorted(hist):
            for ms, lo, la in sorted({tuple(p) for p in hist[cid]}):
                w.writerow([f"{cid}|{names[cid]}", iso(ms), "taken", f"{lo:.6f}", f"{la:.6f}"])
                hrows += 1
    log(f"wrote {rows} hanoi rows (from {len(hanoi)} in box), {len(names)} users, {hrows} history rows")


if __name__ == "__main__":
    for name in ["test.csv"] + (["train.csv"] if "--train" in sys.argv else []):
        if os.path.exists(os.path.join(ST, name + ".json")):
            log(name, "already done")
            continue
        run_split(name)
    write()
