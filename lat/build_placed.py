"""Assemble the Commons files that had no camera coordinate into one source.

Three routes, in order of trust, first one to place a file wins:
  vision           the place was identified from the pixels, then geocoded
  title            the file title names a place, then geocoded
  object-location  Commons {{Object location}}: where the SUBJECT is

None of these is a camera position. They are site-level, so every row is
flagged site_level in lat.multi, which plots such rows but keeps
them out of the connecting lines and the coordinate dedup. A line drawn between
two landmark centroids would be a journey nobody recorded.

The photographer id is the uploader, as everywhere else in the commons
namespace - but only where the uploader IS the photographer. An audit of the
first version found 193 of 347 rows where the Artist credit named someone else:
mass-transferrers of other people's Flickr photos, press-photo uploaders, bots
the regex missed. Their "history" is other people's travels, it labelled them
LOCAL, and through the shared namespace it flipped 19 points of the existing
commons source and drew the Mausoleum blue. So a row is kept only when the
Artist credit and the uploader are the same name, and the history file the
merge reads is rebuilt here to hold the kept photographers and nobody else.
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lat.geocode import _fold



VISION = "data/multi/commons_vision_located.tsv"
TITLE = "data/multi/commons_located.tsv"
OBJECT = "data/multi/commons_objloc.tsv"
UPLOADERS = "data/multi/commons_nocoord_uploaders.tsv"
NOCOORD = "data/multi/commons_nocoord.tsv"
RAW_HISTORY = "data/multi/commonsplaced_uploaders_raw.tsv"   # harvest_history
HISTORY = "data/multi/commonsplaced_history.tsv"             # what merge reads
# One coordinate carrying this many object-location files is a generic point
# somebody reused (14 unrelated street scenes sat on one), not a subject.
OBJLOC_MAX_STACK = 3
OUT = "data/multi/commonsplaced_hanoi.tsv"
BOT = re.compile(r"bot\d*\b|\bbot|upload ?wizard|flickr ?upload|magnus manske",
                 re.I)
FLICKR_ID = re.compile(r"\(\d{9,}\)")     # "... (14563741979).jpg"


def _who(s):
    """A credit or a username reduced to something comparable."""
    s = re.sub(r"\((talk|thảo luận|discussion|diskussion)\)", "", s or "", flags=re.I)
    s = re.sub(r"^\s*([a-z]{2,3}:)?\s*user:", "", s.strip(), flags=re.I)
    return re.sub(r"[^a-z0-9]", "", _fold(s))


def own_work(artist, uploader):
    a, u = _who(artist), _who(uploader)
    return bool(a and u) and (a == u or (len(u) >= 4 and u in a)
                              or (len(a) >= 4 and a in u))


def _rows(path):
    if not os.path.exists(path):
        return []
    return list(csv.DictReader(open(path, newline=""), delimiter="\t"))


def main():
    from collections import Counter
    ups = {r["pageid"]: r for r in _rows(UPLOADERS)}
    artist = {r["pageid"]: r.get("user", "") for r in _rows(NOCOORD)}
    out, seen, dropped = [], set(), Counter()

    def add(pid, lon, lat, method, title, date, date_kind, user="", uid="",
            credit=None):
        if pid in seen:
            return
        u = ups.get(pid, {})
        user, uid = u.get("user") or user, u.get("userid") or uid
        if u.get("datetimeoriginal"):
            date, date_kind = u["datetimeoriginal"], "taken"
        elif not date and u.get("upload_timestamp"):
            date, date_kind = u["upload_timestamp"], "uploaded"
        credit = artist.get(pid) if credit is None else credit
        if not user:
            dropped["no uploader"] += 1
        elif BOT.search(user):
            dropped["bot uploader"] += 1
        elif FLICKR_ID.search(title):
            dropped["flickr transfer (id in title)"] += 1
        elif not own_work(credit, user):
            dropped["artist credit is not the uploader"] += 1
        elif not date:
            dropped["no date"] += 1
        else:
            seen.add(pid)
            out.append([pid, user, uid, date, date_kind, lon, lat, "150",
                        method, title.replace("\t", " ")])

    for r in _rows(VISION):
        add(r["pageid"], r["lon"], r["lat"], "vision", r["title"],
            r["date"], r["date_kind"])
    for r in _rows(TITLE):
        add(r["pageid"], r["lon"], r["lat"], "title", r["title"],
            r["date"], r["date_kind"])
    obj = [r for r in _rows(OBJECT) if "(exif)" not in r.get("found_via", "")]
    stack = Counter((r["lon"], r["lat"]) for r in obj)
    for r in obj:
        if stack[(r["lon"], r["lat"])] > OBJLOC_MAX_STACK:
            dropped["object-location point reused by unrelated files"] += 1
            continue
        # these rows were harvested with `user` = uploader; the credit, where
        # the category crawl saw the file, is in commons_nocoord.tsv
        add(r["id"], r["lon"], r["lat"], "object-location", r["title"],
            r["date"], r["date_kind"], r.get("user", ""), r.get("user_id", ""),
            credit=artist.get(r["id"], r.get("user", "")))

    with open(OUT, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["id", "user", "user_id", "date", "date_kind", "lon", "lat",
                    "accuracy_m", "method", "title"])
        w.writerows(out)

    kept_users = {r[1] for r in out}
    hist = [r for r in _rows(RAW_HISTORY) if r["user"] in kept_users]
    with open(HISTORY, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["user", "date", "lon", "lat", "geoprivacy"])
        for r in hist:
            w.writerow([r["user"], r["date"], r["lon"], r["lat"],
                        r.get("geoprivacy") or "open"])

    by = Counter(r[8] for r in out)
    print(f"{len(out):,} placed files from {len(kept_users):,} photographers "
          f"-> {OUT}")
    print(f"  by route {dict(by)}")
    for why, n in dropped.most_common():
        print(f"  dropped {n:4d}  {why}")
    print(f"  {len(hist):,} history rows for the kept photographers -> {HISTORY}")


if __name__ == "__main__":
    main()
