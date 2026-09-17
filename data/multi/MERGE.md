# Merging several photo sources

The single-source build is a faithful reproduction of Erica Fischer's *Locals
and Tourists* for Hanoi from one table, YFCC100M. This directory is a separate
experiment: what the same map looks like when every other reachable source of
geotagged photographs is added. It renders to `out/multi/` and never overwrites
`out/`. Read `../../README.md` for the faithful one.

Figures below are re-measured against the current build. Live counts are in
`out/multi/stats.json`, which is the authority if the two ever disagree.

## Why a separate map at all

Fischer's colours are a residency test. Blue means a photographer's photos
inside the Hanoi box span 30 days or more; red means they look resident in a
15-mile box that does not overlap Hanoi's and were here under a month; yellow
means neither. That needs each photographer's worldwide history over time.
Adding a source that cannot supply one does not add data to this map, it adds
uncoloured dots to a map whose only content is the colour.

So the question for every candidate was never "does it have photos of Hanoi"
but "does it have a stable photographer id, a date, a coordinate, and a
queryable global history". Most do not.

## Decisions

**Ids are namespaced and never reconciled.** `flickr:7997148@N05`,
`commons:Orizan`, `inat:benjamin`. The same human with accounts on two
platforms counts as two photographers. Cross-platform identity resolution is
not attempted: it would mean matching people across services on name or image
similarity, which is unreliable and a privacy problem this map does not need to
create. The Commons routes (API, SQL dumps) share one `commons:` namespace,
because there one uploader is one uploader.

**`date_kind` travels with every row**, because a 30-day span measures
different things per source. Flickr gives date *taken*, iNaturalist *observed*,
the Commons SQL dumps *uploaded*. Upload dates are the dangerous one: a
photographer who uploads a five-year backlog in a week shows a one-week span
and reads as a visitor, while one who drip-feeds the same trip over years looks
resident. `RESIDENCY_DATE_KINDS` restricts which kinds enter the residency
test; all kinds are still plotted. As harvested, Commons is 17,168 capture dates against 400 upload, so including
it costs about 2%.

**Precision is normalised to metres.** Flickr's 1–16 ordinal, iNaturalist's
`positional_accuracy` and the rest land on one scale, and `precision_level` is
written back into the `acc` key so the existing renderer's accuracy >= 12 line
gate works untouched. Missing accuracy in a column that exists is treated as
unknown (1,000 m, flagged coarse) rather than fine or coarse.

**iNaturalist obscured coordinates are refused, and the history path is now
covered too.** For taxa with conservation concerns iNaturalist randomises the
published position inside roughly 0.2 degrees, about 22 km. On a 24 km map that
is not a coordinate, and in a residency test it invents presence in a city the
observer may never have visited. The Hanoi tables were always filtered. The
*history* files were not: they carried only `user, date, lon, lat`, so the
reader had no flag to check, rated every history row at the finest possible
iNaturalist fix, and an audit found 229 randomised coordinates from a
pre-filter harvest being used as evidence of presence, flipping one
photographer red. Fixed three ways: the affected users were stripped and the 154 of them that
are actually Hanoi observers re-harvested through the filtering fetcher, the
history writer now records an explicit `geoprivacy` column, and a cross-check
against the live API finds zero overlap between the history and those
observers' obscured observations.

What the column does and does not buy is worth stating precisely, because an
audit pushed back on an earlier wording here. Every value in it is the literal
string `open`, written by the fetcher for rows it has already refused to
obscure, so the column records the fetcher's assurance rather than the API's
answer per row. What it genuinely guarantees is that the *column exists*, so
the merge's reader resolves an `obscured` field instead of silently rating a
history row at the finest possible precision. Column absence was the actual
failure, so that is the useful guarantee.

Two further legacy files were found and removed in the same pass: one carried 3
observers with 3,434 rows from a deep-paging harvester the code no longer
contains, retro-stamped `open` when the column was added. Those 3 were
re-harvested too, and no legacy file remains on disk.

**Per-user capping is exposed, and the measurement argued against using it.**
Commons alone is concentrated: 432 uploaders in the Hanoi box with the top three
at 46%, which is why capping was built. But the question is whether the *merged*
map is more concentrated than the faithful map beside it, and the comparison has
to be like-for-like. The merge precision-filters (it drops Flickr rows coarser
than 5 km), so the honest baseline is the merge's own Flickr layer under
identical filtering, not the published single-source map:

    merged, no cap, drawn                        top-5  22.4%
    the merge's own flickr layer, same filters    top-5  23.7%   <- like-for-like
    published single-source map, unfiltered       top-5  21.3%

    capped at 500:  merged  7.3%   single-source baseline capped at 500  13.3%

Two corrections to an earlier draft of this file, which an audit caught. First,
uncapped the merge is *less* concentrated than its like-for-like baseline
(22.4% against 23.7%); the earlier draft compared it to the unfiltered 21.3%
and reported the difference with the sign backwards. Second, the earlier draft
compared a capped merge against an *uncapped* baseline: capping both at 500
gives 7.3% against 13.3%, a 6.0-point gap rather than the 14.0-point gap
implied. The conclusion survives both corrections, so the default is **no cap**,
and `cap_sweep` still prints on every build so the choice stays visible.

## Sources

Kept: **flickr** (YFCC100M, the baseline), **commons** (Wikimedia Commons API),
**inat** (iNaturalist), and **commonsplaced**, which is small and different in
kind and has its own section below.

Excluded, each with its reason in `stats.json` under
`sources_present_but_excluded` so nobody re-harvests them: **gbif** (about half
the rows state no uncertainty, the stated ones have a p90 of 16.4 km,
`recordedBy` is free text rather than a stable id, and it largely republishes
iNaturalist), **panoramax** (319 rows from exactly one contributor),
**wikidata**, **openaerialmap**, **osmnotes** (not photographs).

**kartaview** and **osv5m** were harvested in a later round and are also
excluded. KartaView returned 5,016 thinned rows, but 4,185 of them belong to one
bulk-import account that is not a photographer, and of the 10 real contributors
only 4 have any history outside Hanoi. The OSV-5M test split has one row in the
box. Mapillary needs a token, and no Panoramio dump with coordinates survives.

A file on disk is not a source. `discover()` used to load any `*_hanoi.tsv` it
found with a default spec, and the half-finished KartaView harvest put 4,631
unreviewed points on the map, moving the top-5 contributor share from 22% to
27%, before anyone had looked at it. An unregistered prefix is now reported and
skipped; rendering it takes a `SourceSpec`.

Wikidata is worth a note because it was wrong here. An earlier version of this
file listed it as excluded while the code still rendered it, contributing 200
points and 58 photographers who existed only from those rows. The documentation
was right and the flag was wrong: the `user` column is whatever the Wikidata
item credits, which is often not a person at all ("Northern Vietnam"), so it
cannot anchor a per-photographer residency test. It is now genuinely off.

Not attempted, deliberately: Reddit, Instagram, TikTok, X. None exposes a
geotag the photographer attached, and inferring an individual account's home
city from their posting history in order to colour them is profiling of private
individuals. Every source above uses location data the photographer chose to
attach to their own photograph.

## Commons files with no camera coordinate (`commonsplaced`)

A walk of the Hanoi category tree on Commons found 4,170 files with no
`{{Location}}`. 95 of them are on the merged map. They got there by one of
three routes, and none of the three is a camera position:

- **vision** (22 files). Contact sheets of 750 files were read by agents doing
  what a GeoGuessr player does: name the place from what the pixels show, never
  a coordinate. 319 cells were located and 431 refused (portraits, documents,
  food, events abroad). Only verdicts at confidence 0.7 or higher are used,
  which excludes every cell placed mainly because its title said so.
- **title** (69 files). The file title names a place, which is geocoded.
- **object-location** (4 files). Commons `{{Object location}}`. No file in the
  set had a usable EXIF GPS fix; 16 had one axis only.

Read these points as follows.

1. They mark where the **subject** is, not where the camera stood.
2. Every file at one site lands on **one centroid**. The source is flagged
   `site_level`: its rows are plotted, never joined by a connecting line, never
   coordinate-deduplicated, and they do not vote on what counts as a shared
   place pin.
3. The photographer is the uploader **only where the Artist credit names the
   uploader**. The first version skipped that test and an audit measured the
   result: 193 of 347 rows credited someone else. Mass-transferrers of other
   people's Flickr photographs were classified by other people's travels,
   labelled local, and through the shared `commons:` namespace flipped 19
   points of the existing commons source and drew the Mausoleum blue. Files
   with a Flickr id in the title, bot uploaders and mismatched credits are now
   dropped, and the history file the merge reads is rebuilt to hold the kept
   photographers only. With the source on, three pre-existing photographers
   change label, each on their own dated photographs.
4. Geocoding was the other failure. The same audit put the first version at
   14% wrong: chain shops resolving to whichever branch OSM knows, a district
   name matching a railway station, a village gate placed in a park 15 km
   away. `lat/geocode.plausible()` now requires every distinctive word of the
   name to be in the hit's name (English exonyms from a closed list excepted),
   requires a stated street or district to appear whole in the hit's address,
   and refuses roads altogether (a street centroid is not a site: "90 Thợ
   Nhuộm" landed 500 m from number 90) and one-word matches to shops. It is
   deliberately lossy: 1,202 of 1,319 place-naming titles are rejected,
   including real ones ("BoBaPop" against OSM's "BoBaBop"). Each rejected case
   the audit found is a test in `tests/test_multi.py`.
5. 347 files were placed by the first version, 97 survive the identity and
   geocoding rules, and 95 have a usable date (one credit reads "30 December
   2016 (according to Exif data)", one photograph is from 2001, before the
   window opens).

The same uploader-is-not-the-photographer problem exists in the main
**commons** source, which has always keyed on the uploader. It has not been
measured there. It is listed under Known gaps.

## What the merge shows

    photographers classified   local 430   tourist 1,998   unknown 944  (3 untestable)
    photographers on the map   local 410   tourist 1,522   unknown 675  = 2,607
    points                     local 24,938  tourist 14,194  unknown 3,262  = 42,394
    plus 7,601 connecting lines
    by source                  flickr 18,230   commons 14,158   inat 9,911   commonsplaced 95

Two populations, deliberately both shown: 3,372 photographers are classified
(the residency set, before the precision filter and before clipping to the
drawn box) and 2,607 put a mark on the canvas. Quoting one against the other is
how the earlier draft of this file produced a table that did not add up.

**The colour balance inverts against the faithful map, and the cause is
narrower than it first looks.** Single-source Flickr is 51% visitor
photographs; the merge is 59% local. But per source, on the drawn set:

    merged, all sources      58.8% local   33.5% tourist
    flickr alone             46.2% local   49.1% tourist
    commons alone            83.7% local    6.4% tourist
    inat alone               46.4% local   43.8% tourist
    merged without commons   46.2% local   47.2% tourist
    merged without inat      62.6% local   30.4% tourist

    per photographer, share local:  commons 23.9%   flickr 18.5%   inat 12.7%

The per-source table was measured before `commonsplaced` existed and has not
been re-run. That source adds 95 points (0.22% of the map) and changes the
label of three commons photographers holding five points between them, so no
row above moves by as much as 0.1 of a point; the merged line was recomputed and
is still 58.8% / 33.5%.

So the inversion is **entirely Wikimedia Commons**. Remove it and the merged map
is 46.2% local against 47.2% tourist, which is the visitor-leaning baseline
again. iNaturalist is not more local: at 46.4% it is indistinguishable from
Flickr's 46.2%, by photographer it is the *least* local source of the three at
12.7%, and removing it *raises* the merged local share to 62.6%. An earlier
draft of this file and of the README claimed Commons uploaders "and
iNaturalist observers" documenting a city are more likely to live in it. The
second half of that is wrong.

**Date coverage explains much of the rest.** The all-time merge is a 2004–2026
composite because YFCC stops in 2014 while iNaturalist is overwhelmingly 2020s.
Restricting every source to the period YFCC actually covers
(`--yfcc-window`, rendered as `hanoi_multi_yfccwin_6137.png` with its own
`stats_yfccwin.json`) gives 21,896 points at **11,084 local, 9,219 tourist,
1,593 unknown = 50.6% local**. The local-minus-tourist margin falls from +25.3
points to +8.5. So a large part of the effect is that the 30-day span rule pays
for a long baseline, and Commons rows have one where Flickr's cannot.

Read the inversion as a statement about Wikimedia Commons and about date
coverage, not as a correction to the original map.

## Known gaps

- **Uploader versus photographer in the main commons source.** `commonsplaced`
  drops a file when its Artist credit is not the uploader, and that removed 56%
  of its rows. The main commons harvest has never applied the test. Transferred
  files there are attributed to the transferrer and coloured by the
  transferrer's other uploads. Commons is 83.7% local and carries the whole
  local/visitor inversion discussed above, so this could matter a great deal.

- **LOCAL labels rest on very few days.** The span rule asks only that a
  photographer's earliest and latest Hanoi-box dates be 30 days apart. Of the
  81 Commons photographers labelled local, the median has 4 distinct photo-days
  spread over 638 days, and 28% have two distinct days or fewer. Two photo-days
  twenty months apart is LOCAL under this rule. That is
  Fischer's rule, not a bug introduced here, but it bites harder on a source
  with a decade-long baseline than on one capped at 2014.
- **History is truncated per photographer, and the bias is not one-directional
  as an earlier draft claimed.** Commons stops at 6 request pages per uploader;
  iNaturalist takes each observer's earliest and latest 200 observations. For
  the *foreign-box* route the argument holds: removing history can only shrink
  the best foreign span, so a false TOURIST cannot be gained that way. But
  `classify_users` decides LOCAL first, on the span of dates inside the Hanoi
  box, and history rows also supply Hanoi-box dates the Hanoi harvest lacks.
  Measured on the current build, 11 LOCAL labels exist only because of
  history-supplied dates; revoke those and the photographer falls into the
  foreign-box search and can come out red. An audit's truncation experiment
  produced 83 tourist→unknown, 2 local→unknown and 1 local→tourist. So
  truncation can also manufacture a false tourist, just rarely.
  On the other hand the iNaturalist extremes sample is span-*preserving*: span
  is max minus min, the extremes are exactly what is retained, and adding
  middle rows can never widen a box's span. It cannot manufacture a long span.
  It does mean a truncated observer's residency rests on two endpoints with no
  corroboration of continuous presence.
- **7 Commons uploaders have no history at all** after transport failures
  across the retried runs; every one of the 2,106 iNaturalist observers has
  some.
- **The Commons SQL-dump cross-check was never completed.** It was meant to give
  an independent count of geotagged namespace-6 files in the Hanoi box, to test
  whether the API harvest's quadtree geosearch was complete. That completeness
  is therefore unverified.
- **Commons Flickr-transfer dedup does not do what it claims.** The code can
  recover an original Flickr NSID from `extmetadata.Artist`, but the Commons
  harvest never requested that field, so `commons_hanoi.tsv` has no Artist
  column and the recovery path fires on zero rows. The 555 Commons/Flickr
  duplicates were all caught by the coordinate-plus-day key instead. For scale,
  1,690 Commons rows carry a 2.0-era licence, the Flickr-import signature, so
  up to about 1,100 possible transfers are unvalidated.
- **`data/multi/inat_history.tsv` is not in the repository** (21 MB), nor the
  histories of excluded sources. Regenerate with
  `PYTHONPATH=. .venv/bin/python lat/harvest_history.py inat --workers 3 --pause 3.0`,
  about 90 minutes, holding iNaturalist's requested 60 requests/minute in
  aggregate. A regenerated file is method-equivalent but not row-equivalent:
  the extremes sample moves as observers add records, so the exact row count
  the committed stats were computed from is not re-derivable.
