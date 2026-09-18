"""Who the Mapillary contributors in the Hanoi box are, and what their own
imagery says about residency.

The box is dominated by a handful of accounts, which is fine: the question the
map asks is per photographer, not per photograph. It is answered the same way
for a survey fleet as for anybody else - does their own imagery span 30 days
inside the city box, and do they hold a 30-day span in some other city box.
This module reports the in-box half of that from the discovery dump; the
out-of-box half needs lat/harvest_mapillary.py's history stage.
"""
import datetime as dt
import json
from collections import Counter, defaultdict

SEEN = "data/multi/mapillary/seen.jsonl"
OPERATORS = "data/multi/mapillary_operators.json"
S, W, N, E = 20.926386, 105.728233, 21.144091, 105.961466


def _day(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).date()


def actors(path=SEEN):
    seen = set()
    days = defaultdict(set)
    seqs = defaultdict(set)
    n = Counter()
    pano = Counter()
    cams = defaultdict(Counter)
    uid = {}
    for line in open(path):
        try:
            d = json.loads(line)
        except Exception:
            continue                      # the file is appended to while we read
        i = d.get("id")
        if not i or i in seen:
            continue
        if not (W <= d["lon"] <= E and S <= d["lat"] <= N):
            continue
        seen.add(i)
        u = d.get("user") or "?"
        n[u] += 1
        days[u].add(_day(d["t"]))
        seqs[u].add(d.get("seq"))
        pano[u] += bool(d.get("pano"))
        cams[u][d.get("cam") or "?"] += 1
        uid.setdefault(u, d.get("uid"))
    out = []
    for u, c in n.most_common():
        dd = sorted(days[u])
        out.append({"user": u, "uid": uid[u], "images": c,
                    "distinct_days": len(dd), "first": dd[0].isoformat(),
                    "last": dd[-1].isoformat(), "span_days": (dd[-1] - dd[0]).days,
                    "sequences": len(seqs[u]), "pano_share": pano[u] / c,
                    "camera": cams[u].most_common(1)[0][0]})
    return out


def provisional_label(r):
    """The in-box half of the residency test, which is all the discovery dump
    can answer. LOCAL is final: rule 1 fires before any other evidence is
    consulted, so a 30-day in-box span settles it whoever the contributor is.
    Everything else waits on the out-of-box history.
    """
    return "local" if r["span_days"] >= MONTH_DAYS else "pending history"


MONTH_DAYS = 30


def with_operators(rows, path=OPERATORS):
    try:
        ops = json.load(open(path))
    except OSError:
        ops = {}
    for r in rows:
        o = ops.get(r["user"], {})
        r["operator"] = o.get("operator")
        r["hq_country"] = o.get("hq_country")
        r["operator_confidence"] = o.get("confidence")
        r["label"] = provisional_label(r)
    return rows


if __name__ == "__main__":
    rows = with_operators(actors())
    tot = sum(r["images"] for r in rows)
    print(f"{tot:,} images in the drawn box from {len(rows)} accounts\n")
    print(f"{'account':22s} {'images':>9s} {'days':>5s} {'span':>6s} "
          f"{'seqs':>5s} {'pano':>5s}  first .. last")
    for r in rows:
        print(f"{r['user'][:22]:22s} {r['images']:9,d} {r['distinct_days']:5d} "
              f"{r['span_days']:6d} {r['sequences']:5d} "
              f"{100*r['pano_share']:4.0f}%  {r['first']} .. {r['last']}")
    print(f"\n{'account':18s} {'label':16s} {'images':>9s}  operator / HQ")
    for r in rows:
        who = r["operator"] or "not established"
        hq = f" ({r['hq_country']})" if r.get("hq_country") else ""
        print(f"{r['user'][:18]:18s} {r['label']:16s} {r['images']:9,d}  "
              f"{who[:34]}{hq}")
    n = sum(1 for r in rows if r["label"] == "local")
    img = sum(r["images"] for r in rows if r["label"] == "local")
    print(f"\nlocal on a 30-day in-box span: {n} of {len(rows)} accounts, "
          f"{img:,} of {sum(r['images'] for r in rows):,} images "
          f"({100*img/sum(r['images'] for r in rows):.1f}%)")
    json.dump(rows, open("data/multi/mapillary/actors.json", "w"), indent=1)
