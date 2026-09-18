"""Resolve Hanoi place names to coordinates via Nominatim (OSM), with an
on-disk cache. Used to turn the visual-identification pass's free-text answers
into coordinates without hand-asserting any lat/lon.
"""
import json, os, time
import re
import requests

CACHE = "data/reloc/geocode_cache.json"
UA = "hanoi-locals-tourists/1.0 (+https://github.com/weebao/hanoi-local-tourist-heatmap)"
# Hanoi viewbox: left, top, right, bottom
VIEWBOX = "105.55,21.30,106.15,20.80"


def _load():
    if os.path.exists(CACHE):
        return json.load(open(CACHE))
    return {}


def _save(c):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(c, open(CACHE, "w"), indent=1, ensure_ascii=False)


def _variants(name):
    """Progressively simpler queries. The vision pass returns rich labels like
    "Hoa Lo Prison (Maison Centrale), 1 Hoa Lo, Hanoi"; Nominatim resolves the
    plain landmark name but not the decorated one, so try the decorations off.
    """
    import re
    out, seen = [], set()

    def add(q):
        q = re.sub(r"\s+", " ", q).strip(" ,;")
        if q and q.lower() not in seen:
            seen.add(q.lower()); out.append(q)

    add(name)
    bare = re.sub(r"\([^)]*\)", " ", name)      # drop parentheticals
    add(bare)
    parts = [p.strip() for p in bare.split(",") if p.strip()]
    if parts:
        add(parts[0])                            # leading landmark alone
        # a leading house number is noise for a landmark lookup
        add(re.sub(r"^\s*\d+[A-Za-z]?\s+", "", parts[0]))
        if len(parts) >= 2:
            add(", ".join(parts[:2]))
            add(parts[1])                        # e.g. the street, not the shop
    return out


def geocode(name, cache=None, pause=1.1):
    """-> (lon, lat, display_name) or None. Bounded to the Hanoi viewbox."""
    cache = _load() if cache is None else cache
    key = name.strip().lower()
    if key in cache:
        v = cache[key]
        return tuple(v) if v else None

    val = None
    for cand in _variants(name):
        low = cand.lower()
        q = cand if ("hanoi" in low or "hà nội" in low or "vietnam" in low) \
            else f"{cand}, Hanoi, Vietnam"
        try:
            r = requests.get("https://nominatim.openstreetmap.org/search",
                             params={"q": q, "format": "json", "limit": 1,
                                     "viewbox": VIEWBOX, "bounded": 1},
                             headers={"User-Agent": UA}, timeout=25)
            time.sleep(pause)   # Nominatim asks for <= 1 req/sec
            js = r.json() if r.status_code == 200 else []
        except Exception:
            js = []
        if js:
            val = (float(js[0]["lon"]), float(js[0]["lat"]),
                   js[0].get("display_name", ""))
            break
    cache[key] = val
    _save(cache)
    return val


if __name__ == "__main__":
    import sys
    tests = sys.argv[1:] or [
        "Hoan Kiem Lake", "Temple of Literature", "Ho Chi Minh Mausoleum",
        "Long Bien Bridge", "St Joseph's Cathedral", "Dong Xuan Market",
        "West Lake", "Hanoi Opera House", "Tran Quoc Pagoda",
        "Imperial Citadel of Thang Long", "Hoa Lo Prison", "Bat Trang",
    ]
    c = _load()
    for t in tests:
        v = geocode(t, c)
        print(f"  {t:36s} -> " + (f"{v[0]:.5f},{v[1]:.5f}  {v[2][:60]}" if v else "NOT FOUND"))


# Administrative fallbacks are the trap. Asked for a street it cannot find,
# Nominatim answers with the city: "Thành phố Hà Nội, Việt Nam" at
# 105.8540,21.0283. Accepting that would pile every unresolvable title onto one
# pixel, which is precisely the place-pin pathology the rest of this project
# exists to undo. So a result only counts if it names a specific FEATURE.
REJECT_CLASS = {"boundary"}
REJECT_TYPE = {"administrative", "city", "province", "state", "country",
               "municipality", "region", "county", "suburb", "city_district"}


def geocode_specific(name, cache=None, pause=1.1, min_parts=3):
    """-> (lon, lat, display_name, cls, typ) or None.

    Like `geocode`, but refuses administrative areas and anything whose
    display name is too short to be a specific place. `min_parts` counts
    comma-separated components: "Đường Bờ Sông Sét, Giáp Tứ, Kẻ Sét, Phường
    Hoàng Mai" passes; "Thành phố Hà Nội, Việt Nam" does not.
    """
    cache = _load() if cache is None else cache
    key = "strict::" + name.strip().lower()
    if key in cache:
        v = cache[key]
        return tuple(v) if v else None
    val = None
    for cand in _variants(name):
        low = cand.lower()
        q = cand if ("hanoi" in low or "hà nội" in low or "vietnam" in low) \
            else f"{cand}, Hanoi, Vietnam"
        try:
            r = requests.get("https://nominatim.openstreetmap.org/search",
                             params={"q": q, "format": "json", "limit": 1,
                                     "viewbox": VIEWBOX, "bounded": 1,
                                     "addressdetails": 1},
                             headers={"User-Agent": UA}, timeout=25)
            time.sleep(pause)
            js = r.json() if r.status_code == 200 else []
        except Exception:
            js = []
        if not js:
            continue
        hit = js[0]
        cls = (hit.get("class") or "").lower()
        typ = (hit.get("type") or "").lower()
        disp = hit.get("display_name", "")
        if cls in REJECT_CLASS or typ in REJECT_TYPE:
            continue
        if len([x for x in disp.split(",") if x.strip()]) < min_parts:
            continue
        val = (float(hit["lon"]), float(hit["lat"]), disp, cls, typ)
        break
    cache[key] = val
    _save(cache)
    return val


# --- plausibility of a geocoded hit -----------------------------------------
# Two defects an audit of the title route found, both invisible to the
# specificity guard above because the hit *is* a specific feature:
#   * a through-road resolves to the centroid of the whole way. "44 Hồ Tùng
#     Mậu" landed 1.6 km from where the vision route put the same file.
#   * a title with no place name in it still matches some POI on generic words.
#     "Food market, July 2003" became "Weekend Night Market food stalls" and
#     put 33 photographs on a point nothing supports.
LONG_ROAD = {"motorway", "trunk", "primary", "secondary", "tertiary",
             "motorway_link", "trunk_link", "primary_link"}
GENERIC = set("""
    hanoi ha noi vietnam viet nam city street road st rd pho duong ngo lane
    market cho food stall stalls shop store restaurant cafe coffee hotel house
    building tower bridge cau lake ho park temple pagoda chua den dinh church
    museum bao tang school university truong hospital station ga square gate
    night weekend old new quarter district quan phuong ward the of and in at
    de la le du view photo image picture scene people vendor vendors seller
    january february march april may june july august september october
    november december jan feb mar apr jun jul aug sep sept oct nov dec
    dscf dsc img pict jpg jpeg png
    cong vien lang truong tieu hoc dai benh nha hang quoc te toa khu tap the
    van hoa trung tam cua thi xa thon
""".split())

# Nominatim also matches on name:en / alt_name, which the hit does not return,
# so "Temple of Literature" legitimately resolves to "Văn Miếu - Quốc Tử Giám"
# with no word in common. The first version of this filter excused that for any
# landmark-class hit, and an audit found what that lets through: "Keangnam"
# resolving to the Cầu Giấy railway station, "Chùa Yên Phú, Thanh Trì" to Trấn
# Quốc, a village gate to a park 15 km away. So the excuse is now a closed list:
# an English exonym is believed only when the hit's own name is the landmark it
# is an exonym OF.
EXONYMS = {
    "temple of literature": "van mieu",
    "one pillar pagoda": "chua mot cot",
    "opera house": "nha hat lon",
    "flag tower": "cot co",
    "turtle tower": "thap rua",
    "sword lake": "ho hoan kiem", "lake of the restored sword": "ho hoan kiem",
    "west lake": "ho tay",
    "mausoleum": "lang chu tich",
    "presidential palace": "phu chu tich",
    "st joseph": "nha tho lon", "saint joseph": "nha tho lon",
    "hanoi hilton": "nha tu hoa lo", "maison centrale": "nha tu hoa lo",
    "imperial citadel": "hoang thanh", "citadel of thang long": "hoang thanh",
    "jade mountain": "den ngoc son",
}


def _fold(s):
    import unicodedata
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower()


def _tokens(s):
    import re
    return {t for t in re.findall(r"[a-z]{2,}", _fold(s))
            if t not in GENERIC and not t.isdigit()}


def _split_query(query):
    """-> (name part, locality parts). A title like "Ding Tea, 12 Xuân Thủy,
    Cầu Giấy, Hanoi" names a thing and then says where it is; the trailing
    parts are a check on the hit, not part of the name."""
    parts = [p.strip() for p in query.split(",") if p.strip()]
    ctx = [p for p in parts[1:] if _tokens(p)]
    return (parts[0] if parts else ""), ctx


def plausible(query, hit):
    """-> (ok, reason). `hit` is a geocode_specific() tuple.

    Three tests, each added for a defect somebody measured:
      * a through-road is a centroid, not a place;
      * the hit's NAME must share a distinctive word with the name in the
        query (or be the landmark a listed English exonym refers to);
      * when the query states a street or district, the hit's full address
        must contain one of them. Chain shops fail here: three Ding Tea
        addresses all resolved to the one branch OSM knows, and "Tòa nhà C1,
        ĐH Bách khoa" to an apartment block of the same name 9 km away.
    """
    _, _, disp, cls, typ = hit
    if cls == "highway":
        # Through-roads were refused first; a re-audit then found the short
        # ones are no better. "90 Thợ Nhuộm" lands on the street's centroid
        # 500 m from number 90, and Trần Huy Liệu is 900 m long. A street is
        # not a site, and the source's stated 150 m would be a fib.
        return False, f"a road is not a site ({cls}/{typ})"
    name = disp.split(",")[0]
    qname, ctx = _split_query(query)
    q = _tokens(qname) or _tokens(query)
    if not q:
        return False, "title names no place (generic words only)"
    # EVERY distinctive word of the name must be in the hit's name. A bag of
    # words with one overlap is what let "Cổng làng Văn Trì" become "Làng Văn
    # Hóa Công Viên Yên Sở" and "Công viên Cầu Giấy 2" become an institute
    # whose name contains "viện".
    if len(q) == 1 and (cls == "shop" or typ in {"restaurant", "cafe", "bar",
                                                 "fast_food", "pub"}):
        # "Lang Toi.jpg" -> a restaurant called Làng Tôi: one word, and the
        # only thing tying the photograph to the place is that word
        return False, "one-word title matched to a shop or restaurant"
    missing = q - _tokens(name)
    if missing:
        fq = _fold(query)
        fn = " ".join(re.findall(r"[a-z0-9]+", _fold(name)))
        if not any(en in fq and fn.startswith(vi) for en, vi in EXONYMS.items()):
            return False, (f"'{sorted(missing)[0]}' is not in the hit's name "
                           f"'{name[:40]}'")
    if ctx:
        # a stated street/district counts only if ALL of its words are in the
        # hit's address: "Văn Bình, Thường Tín" must not be satisfied by the
        # "Vân" of a namesake pagoda in another district
        addr = _tokens(disp)
        if not any(_tokens(c) <= addr for c in ctx):
            return False, (f"stated locality '{ctx[0][:30]}' not in the "
                           f"hit's address")
    return True, ""
