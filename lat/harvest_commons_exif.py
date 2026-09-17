"""EXIF-GPS rescue for Commons files that carry no {{Location}} coordinate.

Commons' GeoData only knows a file's position when someone added a
{{Location}} template. Plenty of Hanoi files never got one but still carry the
camera's GPS in their EXIF block, which the API exposes as *metadata*
(`prop=imageinfo&iiprop=metadata`). Nothing here ever fetches an image.

    PYTHONPATH=. .venv/bin/python lat/harvest_commons_exif.py nocoord
    PYTHONPATH=. .venv/bin/python lat/harvest_commons_exif.py search [--max 3000]
    PYTHONPATH=. .venv/bin/python lat/harvest_commons_exif.py history

Single process, sequential, resumable: every examined pageid is appended to
commons_exif_checked.txt and skipped next time. The photographer id is the
UPLOADER (user + userid), not the Artist credit; the merge namespaces it as
`commons:` later. Rows already in commons_objloc.tsv are never rewritten.
"""
import argparse
import csv
import html
import os
import re
import sys
import time

import requests

MULTI = "data/multi"
API = "https://commons.wikimedia.org/w/api.php"
UA = ("hanoi-locals-tourists/1.0 (non-commercial research map of Hanoi; "
      "metadata only, single-threaded; python-requests)")
S, W, N, E = 20.926386, 105.728233, 21.144091, 105.961466
BATCH, PAUSE = 50, 0.5

NOCOORD = f"{MULTI}/commons_nocoord.tsv"
HANOI = f"{MULTI}/commons_objloc.tsv"
ALLGPS = f"{MULTI}/commons_exif_allgps.tsv"
CHECKED = f"{MULTI}/commons_exif_checked.txt"
UPLOADERS = f"{MULTI}/commons_nocoord_uploaders.tsv"
SEARCH_IDS = f"{MULTI}/commons_exif_search_ids.tsv"
SOURCE = f"{MULTI}/commons_exif_source.tsv"
SRC_HDR = ["id", "source", "raw_lat", "raw_lon", "verdict"]
EXIF_HIST = f"{MULTI}/commons_objloc_uploaders_hist.tsv"
HANOI_HDR = ["id", "user", "date", "date_kind", "lon", "lat", "accuracy",
             "url", "title", "user_id", "found_via", "date_raw"]
ALLGPS_HDR = ["id", "user", "date", "date_kind", "lon", "lat", "accuracy",
              "url", "title", "user_id", "had_coord_entry"]
UPL_HDR = ["pageid", "user", "userid", "upload_timestamp", "datetimeoriginal"]
TERMS = ["Hà Nội", "Hanoi", "Hoàn Kiếm", "Hồ Tây", "Long Biên", "Văn Miếu",
         "phố cổ Hà Nội"]


# ------------------------------------------------------------------ http
def api_get(session, params, tries=8):
    """GET with backoff on 429/503, maxlag and transport errors."""
    params = dict(params, format="json", formatversion="2", maxlag="5")
    delay = 5
    for _ in range(tries):
        try:
            r = session.get(API, params=params, timeout=90)
        except requests.RequestException as ex:
            print(f"  transport {type(ex).__name__}; sleep {delay}s",
                  flush=True)
            time.sleep(delay); delay = min(delay * 2, 300); continue
        if r.status_code in (429, 503) or r.status_code >= 500:
            wait = int(r.headers.get("Retry-After") or delay)
            print(f"  http {r.status_code}; sleep {wait}s", flush=True)
            time.sleep(wait); delay = min(delay * 2, 300); continue
        r.raise_for_status()
        d = r.json()
        err = d.get("error", {})
        if err.get("code") in ("maxlag", "ratelimited", "readonly"):
            wait = int(r.headers.get("Retry-After") or delay)
            print(f"  {err.get('code')}; sleep {wait}s", flush=True)
            time.sleep(wait); delay = min(delay * 2, 300); continue
        if err:
            raise RuntimeError(f"api error {err}")
        return d
    raise RuntimeError("gave up after repeated backoff")


# ------------------------------------------------------------ GPS parsing
def _num(tok):
    tok = tok.strip()
    if "/" in tok:
        a, b = tok.split("/", 1)
        return float(a) / float(b) if float(b) else None
    return float(tok)


def parse_coord(val, ref=None):
    """EXIF coordinate -> (signed decimal degrees, precise?) or (None, False).

    MediaWiki normally hands back a signed decimal, but older rows keep the
    raw rational triplet ("21/1 1/1 2745/100") or "21 deg 1' 27.45\" N".
    `precise` is False when the value carries under 4 real decimal places:
    at most 3 decimals, or a whole number of arc-minutes.
    """
    if val is None:
        return None, False
    if isinstance(val, (int, float)):
        v = float(val)
    else:
        s = str(val).strip()
        m = re.search(r"[NSEW]", s.upper()) if re.search(r"\d\s*[NSEWnsew]\s*$", s) else None
        if m and not ref:
            ref = m.group(0)
        toks = re.findall(r"-?\d+(?:\.\d+)?(?:/-?\d+(?:\.\d+)?)?", s)
        try:
            nums = [_num(t) for t in toks[:3]]
        except ValueError:
            return None, False
        if not nums or any(n is None for n in nums):
            return None, False
        sign = -1 if nums[0] < 0 else 1
        v = abs(nums[0])
        if len(nums) > 1:
            v += abs(nums[1]) / 60
        if len(nums) > 2:
            v += abs(nums[2]) / 3600
        v *= sign
    if ref and str(ref).strip()[:1].upper() in ("S", "W"):
        v = -abs(v)
    a = abs(v)
    coarse = (abs(a * 1000 - round(a * 1000)) < 1e-6
              or abs(a * 60 - round(a * 60)) < 1e-6)
    return v, not coarse


def exif_gps(metadata):
    md = {m.get("name"): m.get("value") for m in metadata or []
          if isinstance(m, dict)}
    lat, plat = parse_coord(md.get("GPSLatitude"), md.get("GPSLatitudeRef"))
    lon, plon = parse_coord(md.get("GPSLongitude"), md.get("GPSLongitudeRef"))
    return lat, lon, (plat or plon), md.get("DateTimeOriginal")


def gps_ok(lat, lon, precise):
    """Reject absent, out-of-range, null-island, and coarse coordinates.
    Coarse = BOTH axes under 4 real decimals (one axis can land on a round
    value by chance; both doing so is a typed-in or centroid coordinate)."""
    if lat is None or lon is None:
        return False
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return False
    if abs(lat) < 1e-4 and abs(lon) < 1e-4:
        return False
    return precise


MONTHS = {m: i + 1 for i, m in enumerate(
    "january february march april may june july august september october "
    "november december".split())}


def norm_date(raw):
    """Best-effort ISO date from EXIF / extmetadata text; None if hopeless."""
    if not raw:
        return None
    s = re.sub(r"<[^>]+>", " ", html.unescape(str(raw))).strip()
    m = re.match(r"(\d{4})[:\-](\d{2})[:\-](\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?", s)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        if not (1826 <= y <= 2026 and 1 <= mo <= 12 and 1 <= d <= 31):
            return None
        out = f"{y:04d}-{mo:02d}-{d:02d}"
        if m[4]:
            out += f"T{m[4]}:{m[5]}:{m[6] or '00'}"
        return out
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", s)
    if m and m[2].lower() in MONTHS:
        return f"{int(m[3]):04d}-{MONTHS[m[2].lower()]:02d}-{int(m[1]):02d}"
    m = re.fullmatch(r"(\d{4})(?:-(\d{2}))?", s)
    if m and 1826 <= int(m[1]) <= 2026:
        return s
    return None


# ------------------------------------------------------------------ files
def read_ids(path, col):
    if not os.path.exists(path):
        return set()
    with open(path, newline="") as f:
        return {r[col] for r in csv.DictReader(f, delimiter="\t") if r.get(col)}


def appender(path, hdr):
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    f = open(path, "a", newline="")
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    if new:
        w.writerow(hdr)
    return f, w


def load_checked():
    if not os.path.exists(CHECKED):
        return set()
    with open(CHECKED) as f:
        return {ln.strip() for ln in f if ln.strip()}


# ------------------------------------------------------------- the check
def check_ids(ids, found_via, session, write_uploaders=False):
    """ids: {pageid: found_via-or-None}. Returns stats dict."""
    checked = load_checked()
    in_hanoi = read_ids(HANOI, "id")
    in_all = read_ids(ALLGPS, "id")
    in_upl = read_ids(UPLOADERS, "pageid") if write_uploaders else set()
    todo = [i for i in ids if i not in checked
            or (write_uploaders and i not in in_upl)]
    print(f"{len(ids)} ids, {len(todo)} to examine", flush=True)
    fh, wh = appender(HANOI, HANOI_HDR)
    fa, wa = appender(ALLGPS, ALLGPS_HDR)
    fc = open(CHECKED, "a")
    fs, ws = appender(SOURCE, SRC_HDR)
    fu = wu = None
    if write_uploaders:
        fu, wu = appender(UPLOADERS, UPL_HDR)
    st = dict(examined=0, missing=0, exif_gps=0, object_loc=0, rejected=0, had_coord=0,
              new_allgps=0, new_inbox=0)
    for k in range(0, len(todo), BATCH):
        chunk = todo[k:k + BATCH]
        pages, cont = {}, None
        while True:  # imageinfo/coordinates may continue within a batch
            p = {"action": "query", "pageids": "|".join(chunk),
                 "prop": "imageinfo|coordinates", "colimit": "max",
                 "coprimary": "all", "coprop": "type",
                 "iiprop": "metadata|user|userid|timestamp|extmetadata",
                 "iiextmetadatafilter": "DateTimeOriginal"}
            if cont:
                p.update(cont)
            d = api_get(session, p)
            for pg in d.get("query", {}).get("pages", []) or []:
                cur = pages.setdefault(str(pg.get("pageid")), {})
                for key, v in pg.items():
                    if key not in cur or not cur[key]:
                        cur[key] = v
            cont = d.get("continue")
            if not cont:
                break
            time.sleep(PAUSE)
        for pid in chunk:
            pg = pages.get(pid) or {}
            ii = (pg.get("imageinfo") or [None])[0]
            st["examined"] += 1
            if not ii:
                st["missing"] += 1
                if wu and pid not in in_upl:
                    wu.writerow([pid, "", "", "", ""]); in_upl.add(pid)
                if pid not in checked:
                    fc.write(pid + "\n"); checked.add(pid)
                continue
            user, uid = ii.get("user", ""), ii.get("userid", "")
            ts = ii.get("timestamp", "")
            lat, lon, precise, dto = exif_gps(ii.get("metadata"))
            ext = ((ii.get("extmetadata") or {}).get("DateTimeOriginal")
                   or {}).get("value")
            raw = dto or (re.sub(r"<[^>]+>", " ", html.unescape(ext)).strip()
                          if ext else "")
            raw = " ".join(str(raw).split())  # no embedded newlines/tabs
            if wu and pid not in in_upl:
                wu.writerow([pid, user, uid, ts, raw]); in_upl.add(pid)
            if pid in checked:
                continue
            fc.write(pid + "\n"); checked.add(pid)
            cos = pg.get("coordinates") or []
            primary = any(c.get("primary") for c in cos)
            md = {m.get("name"): m.get("value") for m in ii.get("metadata") or []
                  if isinstance(m, dict)}
            src = None
            if lat is not None or lon is not None:
                st["exif_gps"] += 1
                ok = gps_ok(lat, lon, precise)
                ws.writerow([pid, "exif", md.get("GPSLatitude"),
                             md.get("GPSLongitude"), "ok" if ok else "rejected"])
                if ok:
                    src = "exif"
                else:
                    st["rejected"] += 1
            if src is None:
                # No usable camera GPS. A secondary GeoData coordinate is an
                # {{Object location}}: where the SUBJECT is, not the camera.
                sec = [c for c in cos if not c.get("primary")]
                if not sec:
                    continue
                st["object_loc"] += 1
                lat, pa = parse_coord(sec[0].get("lat"))
                lon, po = parse_coord(sec[0].get("lon"))
                ok = gps_ok(lat, lon, pa or po)
                ws.writerow([pid, "object-location", sec[0].get("lat"),
                             sec[0].get("lon"), "ok" if ok else "rejected"])
                if not ok:
                    st["rejected"] += 1
                    continue
                src = "object-location"
            iso = norm_date(dto) or norm_date(ext)
            date, kind = (iso, "taken") if iso else (ts.rstrip("Z"), "uploaded")
            had = "yes" if primary else "no"
            url = f"https://commons.wikimedia.org/?curid={pid}"
            title = pg.get("title", "")
            if pid not in in_all:
                wa.writerow([pid, user, date, kind, f"{lon:.6f}", f"{lat:.6f}",
                             "", url, title, uid, had])
                in_all.add(pid); st["new_allgps"] += 1
            if had == "yes":
                # a {{Location}} file: the main Commons harvest owns it
                st["had_coord"] += 1
                continue
            if re.search(r"CAPELLA|Sentinel-|Landsat", title):
                continue  # satellite scene, not a photograph taken in the city
            if S <= lat <= N and W <= lon <= E and pid not in in_hanoi:
                wh.writerow([pid, user, date, kind, f"{lon:.6f}", f"{lat:.6f}",
                             "", url, title, uid,
                             (ids[pid] or found_via) + f" ({src})",
                             raw or ts])
                in_hanoi.add(pid); st["new_inbox"] += 1
        for f in (fh, fa, fc, fu, fs):
            if f:
                f.flush()
        if (k // BATCH) % 10 == 0:
            print(f"  {k + len(chunk)}/{len(todo)} {st}", flush=True)
        time.sleep(PAUSE)
    for f in (fh, fa, fc, fu, fs):
        if f:
            f.close()
    print("done", st, flush=True)
    return st


# ---------------------------------------------------------------- search
def discover(session, cap):
    """Full-text File: search for Hanoi terms -> pageids we have never seen."""
    known = read_ids(NOCOORD, "pageid") | read_ids(f"{MULTI}/commons_hanoi.tsv", "id")
    got = {}
    if os.path.exists(SEARCH_IDS):
        with open(SEARCH_IDS, newline="") as f:
            got = {r["pageid"]: r["term"] for r in csv.DictReader(f, delimiter="\t")}
        if got:
            print(f"reusing {len(got)} saved search ids", flush=True)
            return got
    per_term = -(-cap // len(TERMS))
    for term in TERMS:
        n0, off = len(got), 0
        while len(got) - n0 < per_term and len(got) < cap and off < 10000:
            d = api_get(session, {"action": "query", "list": "search",
                                  "srnamespace": "6", "srsearch": term,
                                  "srlimit": "500", "sroffset": str(off),
                                  "srprop": "", "srinfo": ""})
            hits = d.get("query", {}).get("search", [])
            for h in hits:
                pid = str(h["pageid"])
                if pid not in known and pid not in got \
                        and len(got) - n0 < per_term and len(got) < cap:
                    got[pid] = term
            nxt = (d.get("continue") or {}).get("sroffset")
            if not hits or nxt is None:
                break
            off = int(nxt)
            time.sleep(PAUSE)
        print(f"  search {term!r}: +{len(got) - n0} new ids", flush=True)
    with open(SEARCH_IDS, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["pageid", "term"])
        w.writerows(got.items())
    return got


# --------------------------------------------------------------- history
def history(session):
    from lat.harvest_history import commons_history, done_users, open_appender
    with open(HANOI, newline="") as f:
        users = {r["user"] for r in csv.DictReader(f, delimiter="\t")
                 if r.get("user_id")}  # blank user_id = credit, not an account
    have = done_users(f"{MULTI}/commons_history.tsv") | done_users(EXIF_HIST)
    todo = sorted(users - have)
    print(f"{len(users)} uploaders, {len(todo)} need history", flush=True)
    f, w = open_appender(EXIF_HIST)
    for u in todo:
        rows, kinds, note = commons_history(u, session)
        for date, lon, lat in rows:
            w.writerow([u, date, lon, lat, "open"])
        f.flush()
        print(f"  {u}: {len(rows)} rows {dict(kinds)} {note or ''}", flush=True)
        time.sleep(1.0)
    f.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["nocoord", "search", "history"])
    ap.add_argument("--max", type=int, default=3000)
    a = ap.parse_args()
    s = requests.Session()
    s.headers["User-Agent"] = UA
    if a.step == "nocoord":
        with open(NOCOORD, newline="") as f:
            ids = {r["pageid"]: None for r in csv.DictReader(f, delimiter="\t")}
        check_ids(ids, "category-tree", s, write_uploaders=True)
    elif a.step == "search":
        ids = discover(s, a.max)
        check_ids({i: "text-search" for i in ids}, "text-search", s)
    else:
        history(s)
