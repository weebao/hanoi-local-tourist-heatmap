#!/usr/bin/env python3
"""KartaView (ex OpenStreetCam) -> data/multi/kartaview_hanoi.tsv + kartaview_history.tsv

Keyless public API, metadata only: no image file is ever requested.

Stages (each resumable; state lives in data/multi/kartaview/):
  1 discover  POST /1.0/list/nearby-photos/ over a grid of 1000 m circles on the
              Hanoi box (1300 m spacing, so circles overlap) -> sequence ids.
              The 2.0 radius search only returns a 20-photo sample, and the 2.0
              bbox sequence search is "Restricted access", so this is the only
              keyless spatial index.
  2 details   POST /details id=<sequence> -> every photo of the sequence with
              shot_date, lat/lng, gps_accuracy, plus the sequence's user/user_id.
  3 write     keep photos inside the box; THINNING RULE: at most one row per
              user per 50 m grid cell (lat/lon snapped to a 50 m lattice) per
              calendar day of shot_date (first photo in time wins).
  4 history   GET /2.0/sequence/?userId= (100/page, capped at MAX_SEQ_PAGES) for
              each Hanoi contributor. That listing only carries the *upload*
              date, so for sequences starting outside the box we pick temporal
              extremes (earliest + latest upload per 0.5 deg cell, at most
              MAX_LOOKUPS per user) and ask /2.0/photo/?sequenceId=&itemsPerPage=1
              for the first photo's shotDate. Only those capture-dated rows are
              written, date_kind=taken.

Only coordinates are used as history. The profile's self-declared country that
/2.0/user/ exposes is deliberately never requested or stored.

Run:  .venv/bin/python lat/harvest_kartaview.py
"""
import csv, json, math, os, sys, time
import requests

S, W, N, E = 20.926386, 105.728233, 21.144091, 105.961466
API = "https://api.openstreetcam.org"
UA = "img-city-heatmap/kartaview-harvester (non-commercial research; metadata only)"
SLEEP = 1.2
RADIUS, STEP_M, IPP = 1000, 1300, 500
MAX_SEQ_PAGES, MAX_LOOKUPS = 80, 60

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "multi")
ST = os.path.join(ROOT, "kartaview")
os.makedirs(ST, exist_ok=True)
sess = requests.Session()
sess.headers["User-Agent"] = UA


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def call(method, path, **kw):
    """-> parsed JSON or None. Backoff on 429/5xx/network; API-level errors return None."""
    delay = 5
    for attempt in range(6):
        try:
            r = sess.request(method, API + path, timeout=90, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                raise IOError(f"http {r.status_code}")
            time.sleep(SLEEP)
            try:
                return r.json()
            except ValueError:
                return None
        except (requests.RequestException, IOError) as e:
            log("  retry", path, e, f"sleep {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, 300)
    return None


def load_json(name, default):
    p = os.path.join(ST, name)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return default


def save_json(name, obj):
    p = os.path.join(ST, name)
    with open(p + ".tmp", "w") as f:
        json.dump(obj, f)
    os.replace(p + ".tmp", p)


def inside(lat, lon):
    return S <= lat <= N and W <= lon <= E


# ------------------------------------------------------------------ 1 discover
def nearby(lat, lon, radius):
    """-> set of sequence ids, or None when the server errors on this circle."""
    seqs, page = set(), 1
    while True:
        d = call("POST", "/1.0/list/nearby-photos/",
                 data={"lat": f"{lat:.6f}", "lng": f"{lon:.6f}", "radius": radius,
                       "page": page, "ipp": IPP})
        if not d or "currentPageItems" not in d:
            return None
        items = d["currentPageItems"]
        seqs.update(str(i["sequence_id"]) for i in items)
        total = int((d.get("totalFilteredItems") or ["0"])[0])
        if len(items) < IPP or page * IPP >= total:
            return seqs
        page += 1


def discover():
    state = load_json("cells.json", {"done": {}, "failed": []})
    dlat = STEP_M / 111320.0
    dlon = STEP_M / (111320.0 * math.cos(math.radians((S + N) / 2)))
    cells = []
    la = S
    while la <= N + dlat:
        lo = W
        while lo <= E + dlon:
            cells.append((round(la, 6), round(lo, 6)))
            lo += dlon
        la += dlat
    log(f"discover: {len(cells)} circles, {len(state['done'])} already done")
    for n, (la, lo) in enumerate(cells):
        key = f"{la},{lo}"
        if key in state["done"]:
            continue
        got = nearby(la, lo, RADIUS)
        if got is None:  # server error on a dense circle: split into 4 smaller, overlapping
            got, bad = set(), False
            o = RADIUS / 2 / 111320.0
            for sa in (-o, o):
                for so in (-o, o):
                    g = nearby(la + sa, lo + so / math.cos(math.radians(la)), int(RADIUS * 0.75))
                    if g is None:
                        bad = True
                    else:
                        got |= g
            if bad:
                state["failed"].append(key)
        state["done"][key] = sorted(got)
        save_json("cells.json", state)
        if n % 20 == 0:
            log(f"  cell {n}/{len(cells)} seqs so far "
                f"{len({s for v in state['done'].values() for s in v})}")
    return sorted({s for v in state["done"].values() for s in v}, key=int), state["failed"]


# ------------------------------------------------------------------ 2 details
def details(seq_ids):
    path = os.path.join(ST, "sequences.jsonl")
    have = set()
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                try:
                    have.add(json.loads(line)["seq"])
                except ValueError:
                    pass
    todo = [s for s in seq_ids if s not in have]
    log(f"details: {len(todo)} to fetch, {len(have)} cached")
    with open(path, "a") as out:
        for n, sid in enumerate(todo):
            d = call("POST", "/details", data={"id": sid})
            osv = (d or {}).get("osv") or {}
            rec = {"seq": sid, "user": osv.get("user"), "user_id": osv.get("user_id"),
                   "photos": [[p.get("id"), p.get("shot_date"), p.get("lat"), p.get("lng"),
                               p.get("gps_accuracy"), p.get("date_added")]
                              for p in osv.get("photos") or []]}
            out.write(json.dumps(rec) + "\n")
            out.flush()
            if n % 25 == 0:
                log(f"  seq {n}/{len(todo)}")
    return path


# ------------------------------------------------------------------ 3 write
def write_hanoi(path):
    seen, rows, stats = set(), [], {"photos_in_box": 0, "no_user": 0, "no_date": 0}
    recs = []
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            if r.get("user_id") is None:
                stats["no_user"] += 1
                continue
            user = f"{r['user_id']}|{r['user']}"
            for pid, shot, la, lo, acc, added in r["photos"]:
                try:
                    la, lo = float(la), float(lo)
                except (TypeError, ValueError):
                    continue
                if not inside(la, lo):
                    continue
                stats["photos_in_box"] += 1
                date, kind = (shot or "")[:19], "taken"
                if not date or date.startswith("0000"):
                    date, kind = (added or "").replace("  (", " ").rstrip(")")[:16], "uploaded"
                    stats["no_date"] += 1
                if not date:
                    continue
                recs.append((user, date, kind, la, lo, acc, pid, r["seq"]))
    recs.sort(key=lambda t: (t[0], t[1]))
    cos = math.cos(math.radians((S + N) / 2))
    for user, date, kind, la, lo, acc, pid, seq in recs:
        cell = (user, date[:10], int(la * 111320 / 50), int(lo * 111320 * cos / 50))
        if cell in seen:
            continue
        seen.add(cell)
        rows.append([pid, user, date.replace(" ", "T"), kind, f"{lo:.6f}", f"{la:.6f}",
                     acc if acc not in (None, "") else "",
                     f"https://kartaview.org/details/{seq}/0"])
    out = os.path.join(ROOT, "kartaview_hanoi.tsv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["id", "user", "date", "date_kind", "lon", "lat", "accuracy", "url"])
        w.writerows(rows)
    stats["rows_after_thinning"] = len(rows)
    users = sorted({r[1] for r in rows})
    stats["users"] = len(users)
    log("hanoi:", stats)
    return users, stats


# ------------------------------------------------------------------ 4 history
def history(users):
    done = load_json("history_done.json", {})
    out = os.path.join(ROOT, "kartaview_history.tsv")
    if not os.path.exists(out):
        with open(out, "w") as f:
            f.write("user\tdate\tdate_kind\tlon\tlat\n")
    for user in users:
        if user in done:
            continue
        uid = user.split("|")[0]
        seqs, page, truncated = [], 1, False
        while True:
            d = call("GET", "/2.0/sequence/", params={"userId": uid, "itemsPerPage": 100, "page": page})
            res = (d or {}).get("result") or {}
            for s in res.get("data") or []:
                try:
                    seqs.append((s["dateAdded"], s["id"], float(s["currentLat"]), float(s["currentLng"])))
                except (KeyError, TypeError, ValueError):
                    pass
            if not res.get("hasMoreData"):
                break
            page += 1
            if page > MAX_SEQ_PAGES:
                truncated = True
                break
        outside = sorted(s for s in seqs if not inside(s[2], s[3]))
        by_cell = {}
        for s in outside:
            by_cell.setdefault((math.floor(s[2] * 2), math.floor(s[3] * 2)), []).append(s)
        picks = {}
        for cell, ss in sorted(by_cell.items(), key=lambda kv: -len(kv[1])):
            for s in (ss[0], ss[-1]):
                if len(picks) < MAX_LOOKUPS:
                    picks[s[1]] = s
        n = 0
        with open(out, "a") as f:
            for sid in picks:
                d = call("GET", "/2.0/photo/", params={"sequenceId": sid, "itemsPerPage": 1})
                data = ((d or {}).get("result") or {}).get("data") or []
                if not data:
                    continue
                p = data[0]
                try:
                    la, lo = float(p["lat"]), float(p["lng"])
                except (KeyError, TypeError, ValueError):
                    continue
                shot = (p.get("shotDate") or "")[:19]
                if not shot or shot.startswith("0000") or inside(la, lo):
                    continue
                f.write(f"{user}\t{shot.replace(' ', 'T')}\ttaken\t{lo:.6f}\t{la:.6f}\n")
                n += 1
        done[user] = {"sequences": len(seqs), "outside": len(outside), "cells": len(by_cell),
                      "rows": n, "truncated": truncated}
        save_json("history_done.json", done)
        log(f"  history {user}: {done[user]}")
    return done


if __name__ == "__main__":
    seq_ids, failed = discover()
    log(f"{len(seq_ids)} sequences; failed circles: {failed}")
    users, _ = write_hanoi(details(seq_ids))
    if "--no-history" not in sys.argv:
        history(users)
    log("done")
