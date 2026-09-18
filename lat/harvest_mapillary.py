#!/usr/bin/env python3
"""Mapillary (API v4) -> data/multi/mapillary_hanoi.tsv + mapillary_history.tsv

Metadata only: no thumbnail or image file is ever requested. The token is read
from .secrets/.mapillary_creds at run time and sent only as an
`Authorization: OAuth` header; it is never written anywhere.

What the v4 graph API actually does (measured, September 2026):
  * images?bbox=   area capped at 0.010 sq deg, `limit` capped at 2000 and NO
                   paging link. Below the cap the answer is a time-budgeted
                   partial SAMPLE: the same tile returned 575 then 1,345 rows,
                   with different id sets, and dense central tiles wider than
                   ~0.0025 deg fail with "reduce the amount of data". So a
                   bbox query can only *discover* sequences and users.
  * images?sequence_ids=a,b   deterministic and complete (matches /image_ids),
                   ignores `limit`. This is how discovered sequences are made
                   complete.
  * images?creator_username=u   works without a bbox, pages deterministically
                   in captured_at-descending order, and accepts
                   start_captured_at / end_captured_at. This gives casual
                   users' complete Hanoi rows and everyone's history.

Stages (each resumable; state under data/multi/mapillary/):
  1 discover  quadtree from 0.01 deg tiles; a tile is split on the "reduce
              data" error or when it returns the 2000 cap, down to a minimum
              width per window (see WINDOWS). Dense answers are sampled twice.
  2 sequences every discovered sequence of a non-bulk user is fetched whole.
              Bulk accounts (camera rigs, see is_bulk) keep their sampled rows:
              a four-camera rig shooting every second saturates a 50 m cell
              from a sample just as well as from the whole drive.
  3 users     each contributor's images are paged (newest first) up to
              MAX_USER_PAGES. Rows inside the box complete the Hanoi set; rows
              outside are the history. Users with more images than that also
              get one page per calendar year (quarters when a year is full),
              so the temporal extremes are still reached.
  4 write     Hanoi rows deduplicated by image id, THINNED to one row per user
              per 50 m lattice cell per calendar day (earliest wins); history
              reduced to the earliest and latest capture per 0.5 deg cell, at
              most MAX_HIST_ROWS per user.

Only usernames, ids, coordinates and capture dates are kept. No profile field
is requested.

Run:  .venv/bin/python lat/harvest_mapillary.py [--stage discover|sequences|users|write] [--no-history]
"""
import csv, json, math, os, re, sys, time
from collections import Counter, defaultdict
import requests

S, W, N, E = 20.926386, 105.728233, 21.144091, 105.961466
API = "https://graph.mapillary.com"
UA = "hanoi-locals-tourists/1.0 (+https://github.com/weebao/hanoi-local-tourist-heatmap)"
SLEEP = 0.3
FIELDS = ("id,captured_at,geometry,computed_geometry,creator{id,username},"
          "sequence,is_pano,camera_type,compass_angle")
HIST_FIELDS = "id,captured_at,geometry,computed_geometry,sequence,is_pano"
LIMIT = 2000
TILE_W = 0.01
SEQ_BATCH_IDS, SEQ_BATCH_IMAGES = 20, 1500
MAX_USER_PAGES = 15
MAX_HIST_ROWS = 60
FIRST_YEAR = 2013            # Mapillary launched in 2013
BULK_SHARE = 0.40            # share of raw Hanoi rows that marks a bulk account
BULK_ROWS = 5000             # sampled Hanoi rows that mark a fleet/rig regardless of share
BULK_PATTERNS = [            # camera-rig / organisation-looking usernames
    r"^[a-z]{2,6}_(front|back|rear|left|right|cam|camera)_?\d*$",
    r"(org|corp|company|city|gov|municipal|survey|mapping|maps|osm|team|ltd|inc|gmbh|llc)$",
]

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "multi")
ST = os.path.join(ROOT, "mapillary")
os.makedirs(ST, exist_ok=True)
SECRETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".secrets", ".mapillary_creds")


def read_token():
    with open(SECRETS) as f:
        for line in f:
            if line.startswith("ACCESS_TOKEN="):
                tok = line.split("=", 1)[1].strip()
                if tok:
                    return tok
    sys.exit("no ACCESS_TOKEN in .secrets/.mapillary_creds")


sess = requests.Session()
sess.headers["User-Agent"] = UA
sess.headers["Authorization"] = "OAuth " + read_token()
COS = math.cos(math.radians((S + N) / 2))


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


class TooBig(Exception):
    """The server refused the query as too expensive (its 500 / code 1)."""


def call(params=None, url=None, path="/images"):
    """-> parsed JSON dict. Backoff on 429/5xx/network. Raises TooBig on the
    Graph 'reduce the amount of data' answer, which is not transient."""
    delay = 5
    for attempt in range(7):
        try:
            r = sess.get(url or API + path, params=params, timeout=120)
            if r.status_code == 200:
                time.sleep(SLEEP)
                return r.json()
            try:
                err = r.json().get("error", {})
            except ValueError:
                err = {}
            msg = err.get("message", "")
            if r.status_code == 500 and err.get("code") == 1 and "reduce" in msg:
                raise TooBig(msg)
            if r.status_code == 400 or (r.status_code == 500 and err.get("type") == "MLYApiException"):
                log("  api error:", msg[:160])
                return {"error": err}
            raise IOError(f"http {r.status_code} {msg[:80]}")
        except (requests.RequestException, IOError, ValueError) as e:
            log("  retry", (params or {}).get("bbox") or (params or {}).get("creator_username") or "page",
                str(e)[:80], f"sleep {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, 300)
    return {"error": "gave up"}


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


def rec(e):
    """Graph image object -> compact record. Position is computed_geometry
    (SfM-adjusted) when present, else the original GPS geometry."""
    g = e.get("computed_geometry") or e.get("geometry")
    if not g or not e.get("captured_at"):
        return None
    try:
        lon, lat = float(g["coordinates"][0]), float(g["coordinates"][1])
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    c = e.get("creator") or {}
    return {"id": str(e["id"]), "t": int(e["captured_at"]), "lon": lon, "lat": lat,
            "user": c.get("username"), "uid": str(c["id"]) if c.get("id") is not None else None,
            "seq": e.get("sequence"), "pano": bool(e.get("is_pano")),
            "cam": e.get("camera_type"), "ang": e.get("compass_angle"),
            "geo": "computed" if e.get("computed_geometry") else "original"}


def append_jsonl(name, recs):
    with open(os.path.join(ST, name), "a") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")


def read_jsonl(name):
    p = os.path.join(ST, name)
    if not os.path.exists(p):
        return
    with open(p) as f:
        for line in f:
            try:
                yield json.loads(line)
            except ValueError:
                pass


# ------------------------------------------------------------------ 1 discover
# Windows: "all" samples everything. Capture-date windows were tried as extra
# passes (they come back complete and stable when the answer is small) but the
# server's cost is the spatial scan, so a windowed 0.01 deg tile fails exactly
# where the unwindowed one does; they were dropped as not worth their time.
WINDOWS = {"all": (None, 0.00125)}
DENSE = LIMIT                # rows from one query above which a second look is taken (off)


def tile_key(lon0, lat0, w):
    return f"{lon0:.6f},{lat0:.6f},{w:.6f}"


def children(lon0, lat0, w):
    """The four quadrants of a 0.01 deg tile; below that only the two diagonal
    quadrants (a checkerboard). Dense tiles exist to discover contributors,
    whose sequences run for hundreds of metres, and the per-user walk in stage
    3 then completes them; sampling every second 0.0025 deg tile halves the
    cost of the fleet-saturated centre."""
    h = w / 2
    quads = [(lon0, lat0, h), (lon0 + h, lat0, h), (lon0, lat0 + h, h), (lon0 + h, lat0 + h, h)]
    return quads if w > 0.0051 else [quads[0], quads[3]]


def query_tile(lon0, lat0, w, window="all", pano=None):
    """-> (records, n_per_query) or raises TooBig. pano=True/False restricts
    the query with is_pano, the last resort for a tile at its minimum width."""
    bbox = f"{lon0:.6f},{lat0:.6f},{min(lon0 + w, E):.6f},{min(lat0 + w, N):.6f}"
    out, ns = {}, []
    for _ in range(2):
        p = {"bbox": bbox, "fields": FIELDS, "limit": LIMIT}
        span = WINDOWS[window][0]
        if span:
            p["start_captured_at"], p["end_captured_at"] = span
        if pano is not None:
            p["is_pano"] = "true" if pano else "false"
        d = call(p)
        if "data" not in d:
            raise TooBig(str(d.get("error"))[:100])
        ns.append(len(d["data"]))
        for e in d["data"]:
            r = rec(e)
            if r:
                out[r["id"]] = r
        if ns[-1] < DENSE:   # small answers are complete; only dense ones are samples
            break
    return list(out.values()), ns


def discover():
    state = load_json("tiles.json", {})
    seen_ids = set()
    for r in read_jsonl("seen.jsonl"):
        seen_ids.add(r["id"])
    base = []
    la = S
    while la < N:
        lo = W
        while lo < E:
            base.append((round(lo, 6), round(la, 6), TILE_W))
            lo += TILE_W
        la += TILE_W
    log(f"discover: {len(base)} base tiles, {len(state)} tile records, {len(seen_ids)} images seen")

    def skey(lon0, lat0, w, window):
        k = tile_key(lon0, lat0, w)
        return k if window == "all" else k + "|" + window

    def accept(key, recs, ns, extra=None):
        new = [r for r in recs if r["id"] not in seen_ids]
        seen_ids.update(r["id"] for r in new)
        append_jsonl("seen.jsonl", new)
        state[key] = {"status": "ok", "n": ns, "distinct": len(recs), "new": len(new),
                      "seqs": len({r["seq"] for r in recs}), "capped": bool(ns) and max(ns) >= LIMIT}
        if extra:
            state[key].update(extra)

    done_n = 0
    predicted_w = TILE_W     # widest leaf of the previous base tile: start there
    for bi, (blon, blat, bw) in enumerate(base):
        leaf_ws = []
        for window, (span, min_w) in WINDOWS.items():
            queue = [(blon, blat, bw)]
            while queue:
                lon0, lat0, w = queue.pop(0)
                key = skey(lon0, lat0, w, window)
                st = state.get(key)
                if st is None and window == "all" and w > predicted_w * 1.001:
                    st = state[key] = {"status": "split", "why": "predicted"}
                if st:
                    if st["status"] == "split":
                        queue[:0] = children(lon0, lat0, w)
                    elif st["status"] == "ok":
                        leaf_ws.append(w)
                    continue
                try:
                    recs, ns = query_tile(lon0, lat0, w, window)
                except TooBig as e:
                    if w / 2 >= min_w * 0.999:
                        state[key] = {"status": "split", "why": "too big"}
                        queue[:0] = children(lon0, lat0, w)
                    else:
                        # splitting by is_pano was tried here and rescued 1 tile
                        # in 35: these are fleet depots, thousands of panoramas
                        # within 140 m, and are given up.
                        state[key] = {"status": "failed", "why": str(e)[:80]}
                        log(f"  FAILED at min width {key}")
                    save_json("tiles.json", state)
                    continue
                if max(ns) >= LIMIT and w / 2 >= min_w * 0.999:
                    state[key] = {"status": "split", "why": "cap", "n": ns}
                    queue[:0] = children(lon0, lat0, w)
                    save_json("tiles.json", state)
                    continue
                accept(key, recs, ns)
                leaf_ws.append(w)
                save_json("tiles.json", state)
                done_n += 1
                if done_n % 25 == 0:
                    log(f"  base {bi}/{len(base)} leaves {done_n} images {len(seen_ids)}")
        predicted_w = max(leaf_ws) if leaf_ws else TILE_W
    ok = sum(1 for v in state.values() if v["status"] == "ok")
    log(f"discover done: {ok} leaf tiles, {sum(1 for v in state.values() if v['status']=='split')} split, "
        f"{sum(1 for v in state.values() if v['status']=='failed')} failed, {len(seen_ids)} images")
    return state


# ------------------------------------------------------------------ bulk rule
def is_bulk(user, share, rows=0):
    if share > BULK_SHARE or rows >= BULK_ROWS:
        return True
    return any(re.search(p, user or "", re.I) for p in BULK_PATTERNS)


def user_shares():
    """raw discovered Hanoi rows per username (stage-1 sample only)."""
    c = Counter()
    for r in read_jsonl("seen.jsonl"):
        if r["user"] and inside(r["lat"], r["lon"]):
            c[r["user"]] += 1
    tot = sum(c.values()) or 1
    return c, {u: n / tot for u, n in c.items()}


# ------------------------------------------------------------------ 2 sequences
def sequences():
    counts, shares = user_shares()
    bulk = {u for u in counts if is_bulk(u, shares[u], counts[u])}
    log(f"sequences: bulk accounts skipped: {sorted(bulk)}")
    seq_user, seq_n = {}, Counter()
    for r in read_jsonl("seen.jsonl"):
        if r["seq"] and r["user"] and r["user"] not in bulk:
            seq_user[r["seq"]] = r["user"]
            seq_n[r["seq"]] += 1
    done = load_json("seq_done.json", {})
    todo = [s for s in seq_user if s not in done]
    log(f"sequences: {len(seq_user)} non-bulk sequences, {len(todo)} to fetch")
    batch, exp = [], 0
    def flush():
        nonlocal batch, exp
        if not batch:
            return
        d = call({"sequence_ids": ",".join(batch), "fields": FIELDS, "limit": LIMIT})
        got = Counter()
        recs = []
        for e in d.get("data") or []:
            r = rec(e)
            if r:
                recs.append(r)
                got[r["seq"]] += 1
        append_jsonl("seqs.jsonl", recs)
        for s in batch:
            done[s] = got.get(s, 0)
            if got.get(s, 0) < seq_n[s]:    # fewer than the sample saw: refetch alone
                d1 = call({"sequence_ids": s, "fields": FIELDS, "limit": LIMIT})
                r1 = [rec(e) for e in d1.get("data") or []]
                r1 = [r for r in r1 if r]
                append_jsonl("seqs.jsonl", r1)
                done[s] = len(r1)
        save_json("seq_done.json", done)
        batch, exp = [], 0
    for n, s in enumerate(todo):
        if len(batch) >= SEQ_BATCH_IDS or exp + seq_n[s] > SEQ_BATCH_IMAGES:
            flush()
        batch.append(s)
        exp += seq_n[s]
        if n % 200 == 0:
            log(f"  seq {n}/{len(todo)}")
    flush()
    log(f"sequences done: {len(done)} fetched, {sum(done.values())} images")


# ------------------------------------------------------------------ 3 users
def all_users():
    users = {}
    for name in ("seen.jsonl", "seqs.jsonl"):
        for r in read_jsonl(name):
            if r["user"] and inside(r["lat"], r["lon"]):
                users.setdefault(r["user"], r["uid"])
    return users


def page_user(user, params, max_pages):
    """-> (records, exhausted). Pages newest-first."""
    out, url, p = [], None, dict(params, creator_username=user, fields=HIST_FIELDS, limit=LIMIT)
    for _ in range(max_pages):
        d = call(p if url is None else None, url=url)
        if "data" not in d:
            return out, False
        for e in d["data"]:
            r = rec(e)
            if r:
                r["user"] = user
                out.append(r)
        url = (d.get("paging") or {}).get("next")
        if not url:
            return out, True
    return out, False


def users(with_history=True):
    counts, shares = user_shares()
    ulist = all_users()
    done = load_json("users_done.json", {})
    hist_path = os.path.join(ROOT, "mapillary_history.tsv")
    if not os.path.exists(hist_path):
        with open(hist_path, "w") as f:
            f.write("user\tdate\tdate_kind\tlon\tlat\n")
    todo = [u for u in sorted(ulist, key=lambda u: -counts.get(u, 0)) if u not in done]
    log(f"users: {len(ulist)} contributors, {len(todo)} to do")
    for n, user in enumerate(todo):
        bulk = is_bulk(user, shares.get(user, 0), counts.get(user, 0))
        recs, exhausted = page_user(user, {}, MAX_USER_PAGES if not bulk else 2)
        windows = 0
        if not exhausted:
            # one page per calendar year back to FIRST_YEAR (quarters if full),
            # only before what the page walk already covered.
            earliest = min((r["t"] for r in recs), default=int(time.time() * 1000))
            y_end = time.gmtime(earliest / 1000).tm_year
            for y in range(y_end, FIRST_YEAR - 1, -1):
                spans = [(f"{y}-01-01T00:00:00Z", f"{y}-12-31T23:59:59Z")]
                while spans:
                    a, b = spans.pop(0)
                    rr, _ = page_user(user, {"start_captured_at": a, "end_captured_at": b}, 1)
                    windows += 1
                    rr = [r for r in rr if r["t"] < earliest]
                    recs.extend(rr)
                    if len(rr) >= LIMIT and b[5:7] == "12" and a[5:7] == "01":
                        spans = [(f"{y}-{m:02d}-01T00:00:00Z", f"{y}-{m+2:02d}-{'30' if m+2 in (6, 9) else '31'}T23:59:59Z")
                                 for m in (1, 4, 7, 10)]
        by_id = {r["id"]: r for r in recs}
        recs = list(by_id.values())
        inbox = [r for r in recs if inside(r["lat"], r["lon"])]
        out = [r for r in recs if not inside(r["lat"], r["lon"])]
        for r in inbox:
            r["uid"] = ulist[user]
        append_jsonl("user_inbox.jsonl", inbox)
        # history: earliest + latest per 0.5 deg cell, busiest cells first
        by_cell = defaultdict(list)
        for r in out:
            by_cell[(math.floor(r["lat"] * 2), math.floor(r["lon"] * 2))].append(r)
        picks = {}
        for cell, rs in sorted(by_cell.items(), key=lambda kv: -len(kv[1])):
            rs.sort(key=lambda r: r["t"])
            for r in (rs[0], rs[-1]):
                if len(picks) < MAX_HIST_ROWS:
                    picks[r["id"]] = r
        if with_history:
            with open(hist_path, "a") as f:
                for r in sorted(picks.values(), key=lambda r: r["t"]):
                    f.write(f"{user}\t{iso(r['t'])}\ttaken\t{r['lon']:.6f}\t{r['lat']:.6f}\n")
        done[user] = {"bulk": bulk, "exhausted": exhausted, "windows": windows,
                      "fetched": len(recs), "inbox": len(inbox), "outside": len(out),
                      "cells": len(by_cell), "history_rows": len(picks)}
        save_json("users_done.json", done)
        log(f"  user {n+1}/{len(todo)} {user}: {done[user]}")
    return done


# ------------------------------------------------------------------ 4 write
def iso(ms):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ms / 1000))


def write():
    by_id = {}
    for name in ("seen.jsonl", "seqs.jsonl", "user_inbox.jsonl"):
        for r in read_jsonl(name):
            if inside(r["lat"], r["lon"]):
                by_id[r["id"]] = r
    stats = {"raw_in_box": len(by_id), "no_user": 0, "pano": 0, "computed_geometry": 0,
             "before_2013": 0}
    raw_users = Counter()
    recs = []
    for r in by_id.values():
        if not r["user"]:
            stats["no_user"] += 1
            continue
        raw_users[r["user"]] += 1
        stats["pano"] += r["pano"]
        stats["computed_geometry"] += r["geo"] == "computed"
        stats["before_2013"] += r["t"] < 1356998400000
        recs.append(r)
    del by_id
    recs.sort(key=lambda r: (r["user"], r["t"]))
    seen, rows = set(), []
    for r in recs:
        date = iso(r["t"])
        cell = (r["user"], date[:10], int(r["lat"] * 111320 / 50), int(r["lon"] * 111320 * COS / 50))
        if cell in seen:
            continue
        seen.add(cell)
        rows.append([r["id"], r["user"], r["uid"] or "", date, "taken", f"{r['lon']:.6f}",
                     f"{r['lat']:.6f}", "", r["seq"] or "", "1" if r["pano"] else "0"])
    out = os.path.join(ROOT, "mapillary_hanoi.tsv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["id", "user", "user_id", "date", "date_kind", "lon", "lat", "accuracy",
                    "sequence", "is_pano"])
        w.writerows(rows)
    stats["rows_after_thinning"] = len(rows)
    stats["users"] = len(raw_users)
    thin_users = Counter(r[1] for r in rows)
    tot = sum(raw_users.values()) or 1
    stats["bulk_accounts"] = {u: {"raw": n, "thinned": thin_users[u], "share": round(n / tot, 4),
                                  "by_share": n / tot > BULK_SHARE, "by_rows": n >= BULK_ROWS,
                                  "by_name": is_bulk(u, 0)}
                              for u, n in raw_users.items() if is_bulk(u, n / tot, n)}
    if rows:
        ds = sorted(r[3] for r in rows)
        stats["date_range"] = [ds[0], ds[-1]]
    stats["top_users_thinned"] = thin_users.most_common(10)
    stats["top_users_raw"] = raw_users.most_common(10)
    save_json("users_raw.json", {"raw_rows_per_user": raw_users, "thinned_rows_per_user": thin_users,
                                 "stats": stats})
    log("hanoi:", json.dumps(stats))
    return stats


if __name__ == "__main__":
    args = sys.argv[1:]
    stage = args[args.index("--stage") + 1] if "--stage" in args else None
    if stage in (None, "discover"):
        discover()
    if stage in (None, "sequences"):
        sequences()
    if stage in (None, "users"):
        users(with_history="--no-history" not in args)
    if stage in (None, "write"):
        write()
    log("done")
