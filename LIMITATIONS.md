# Limitations

Known gaps in the single-source Hanoi map. The multi-source variant has its own list in [`data/multi/MERGE.md`](data/multi/MERGE.md).

## Data

- YFCC100M is the Creative Commons slice of Flickr and stops in 2014. Hanoi here is far sparser than Fischer's London was in the full firehose, and the map is correspondingly emptier. That is data availability, not styling.
- Date-uploaded is discarded at harvest, so date-taken cannot be cross-checked against it without re-downloading 15 GiB.
- Present-day OSM is drawn against a 2010 original. The extract is stamped 2026-09-10.
- 1 of 41 candidate pin groups was never examined, and the vision pass saw 675 of the 2,327 photos sitting on such groups. The unexamined group sits at 105.5104, 21.0394, outside the drawn box, so it cannot affect the image.

## Marks

- The marks are fewer than the counts suggest. The 20,274 points occupy 5,823 distinct pixel positions, 28.7%. The largest single pixel carries 248 photos and draws exactly like one. Of the 2,524 lines, 1,818 exceed 5 px and none are zero-length.
- Relocations concentrate. 367 relocated photos land on 49 coordinates, the top five holding 57% and 25 landing on a coordinate of their own. No jitter is added: an identification gives landmark-level precision, and spreading the points would invent precision the data does not have.
- Connecting lines are longer than the original's. 101 segments exceed 1 km, the longest 4.0 km, and they read as a faint radial starburst the London original does not show. The longest thin straight line measurable in London is about 1.07 km, bracketed at 1.2–1.4 km on a gap-closed mask, while `tools/measure_style.py`'s own thin mask reaches only 0.59 km. The finding is that our chords are several times anything measurable in the original; the exact figure is mask-dependent. The build keeps Fischer's published 15,000 ft and 85 mph caps rather than invent a tighter one, and this is its most likely style deviation.
- 14 connecting segments have identical timestamps at both ends with real separation, up to 27 m. The speed cap treats `dt = 0` as 1 s, which asserts 1-second timestamp granularity. 27 m/s is physical, so they are kept.
- Line draw order is per class. Coincident same-colour segments accumulate correctly. Where two colours cross, one class is composited after the other and the crossing density is not accumulated, measured at 3,636 px from the drawing ops. A colour test cannot detect a blue/red crossing at all. Points are interleaved across classes and drawn last.
- The line-opacity law is a constant. Sub-unity opacity and accumulation are both measured. Whether alpha also varies with segment length is not established.
- The place-pin line gate barely bites. On the drawn set it identifies 3 shared pin coordinates covering 245 photos and removes 22 connecting lines.

## Classification

- A box just beyond the drawn box counts as a different city, so someone resident 2 km outside the Hanoi box comes out red. This follows from Fischer's fixed-box scheme but is an edge effect of using one box rather than the global set. Every tourist's maximal-span home box centre is at least 29.8 km from the city centre and only 1 of 613 is within 60 km, so it is not driving the red layer. A search minimising distance rather than maximising span does find month-long qualifying boxes about 25 km out, inside Hanoi municipality, for a handful of photographers.
- The recorded home box is neither the nearest nor the longest. The search returns at the first box reaching 30 days, so `home_box_centre` in the reason dict is scan-order dependent and no statistic in the README derives from it. The search is bounded by 5-decimal edge rounding and refuses candidate centres above |lat| 85.
- Undocumented choices: the 30-day threshold, no minimum photo count, the pin definition in the README, and the accuracy ≥ 12 line gate.
- Fischer's one stated cleaning rule is not implemented. She excluded photowalks and automated cameras from the residency computation while still plotting them. This build does not.
- The build drops 23,632 worldwide-history rows that duplicate a Hanoi row, keyed on the pre-relocation coordinate at 3 decimals, before classifying. This is verified label-neutral, but nothing in the result table or method section would otherwise reveal the step.
- Labels are sensitive to single dates. Dropping either of a photographer's two extreme dates flips 43 of 960 labels, 4.5%: 29 tourist to unknown, 10 local to unknown, 4 local to tourist. So 14 of the 145 blue labels hinge on one date, and the affected photographers account for 1.1% of plotted photos.
- Box size matters less. Scaling the residency box by ±25%, in both the membership test and the disjointness check, changes 4 labels at ×0.75 and 0 at ×1.25. An independent implementation scaling only the membership test reports 3 and 5. The figure depends on which half of the test you scale, so the operation is stated alongside the number.

## Method notes

Detail that supports the README's numbers without belonging in it.

- Box search. An unconstrained optimum can be slid until its bottom edge sits on a point's latitude and its left edge on a point's longitude, so those positions are enumerated. Sliding can push a box into Hanoi's, so the four positions flush against Hanoi's box are added. Over the 590 tourists with two or more photos in their home box, the greatest pairwise ground distance has a median of 16.9 km and a maximum of 33.4 km against a box diagonal of 34.27 km.
- Timestamps use an explicit epoch. `datetime.timestamp()` uses the host zone and made one boundary label depend on the machine.
- Data volume. 905 of the 960 classified photographers have a photo inside the drawn box; 55 have none and the pin mask removes the last marks of 88 more. The date window admits 48 rows predating Flickr's February 2004 launch. The raw stamps include 1826, 1925, 1950, 1951, 1966, 1980 and 1995 to 2002. One photo was dropped after the vision pass placed it in the Hạ Long / Cát Bà karst, 150 km away. The 143 rows dropped by date cleaning are of the 23,775 harvested.
- Worldwide history. Without it, 610 of 960 labels change; the three tourists that survive shoot in the far-west group at 105.51, inside the harvested box but outside the drawn one. The 1,114,773 history rows pulled become 1,106,583 after cleaning.
- Line caps. The 15,000 ft and 85 mph caps come from Fischer's 2015 code and are undocumented for the 2010 series. The accuracy ≥ 12 gate and the place-pin gate are ours. Lines join consecutive photos at most 10 min apart, with both endpoints at accuracy ≥ 12 and neither on a shared pin. Line alpha was read as 255(1−α) in the red channel of an isolated blue segment.
- Ink. Lines carry 74,783 px of data ink against 44,518 px for points.
- Basemap. 164,398 of 191,100 candidate ways are stroked. Footway, path, steps, cycleway, bridleway and corridor are excluded by default (`--include-paths` keeps them); the extract holds 24,655 footways. The exclusion takes bare-basemap coverage from 7.96% to 6.99%, of which 6.96% survives in the composite. Basemap ink is near parity with London's: a median 1.08× across radially matched rings, 0.80 to 1.29× ring to ring. That is a property of the road network and its OSM vintage, not evidence of style fidelity.
- Pin identity. A pin is a coordinate occurring 5 or more times, merged with others within 5 m, and counts only with 12 or more photos from 3 or more photographers. Exact equality splits the Old Quarter pin into five values within 4 m (105.85, 105.849998, 105.849997 crossed with 21.033333, 21.0333) and drops 91 photos; rounding to 4 decimals makes the pin count 5× sensitive to the decimals; 15 m single-link finds 75 pins covering 6,041 photos. Detection and masking use the same identity and relocation destinations are exempt.
- Vision pass. 41 candidate groups at 4 decimals, 40 adjudicated. Of 675 photos examined, 535 were given a place and 140 were unidentified; of the 535, 161 fell below a 0.6 confidence gate, 6 failed to geocode, 1 was outside Hanoi, 367 were accepted. Genuine pins include Ngọc Sơn Temple, the Temple of Literature, Hỏa Lò Prison, St Joseph's Cathedral, the Sofitel Metropole, Ho Chi Minh's Mausoleum, the Vietnam Military History Museum and Hữu Tiệp Lake. The clearest dumping ground held 575 photos from 137 photographers pinned to an alley off Phố Kim Mã. Six of the ten dumping grounds are one photographer's mis-tagged batches; at 105.8519,21.0318 it is 134 of 136 photos from one account. Of the 1,351 masked photos, 44 were named a place but 42 sat below the gate and 2 could not be geocoded. `lat/apply_vision.py` writes `data/reloc/masked_ids.json`, 1,355 ids of which four resolve to nothing, and fails if an adjudicated pile resolves to no photos.
- Commons, single-source view. Per-uploader history is queryable through `allimages` plus `prop=coordinates`: 124,095 rows over 425 uploaders. Its Hanoi files are concentrated, 17,568 from 432 uploaders with the top three at 46%. The Flickr API needs a key issued to a logged-in account and is not used.
- `tools/measure_style.py` reproduces the accumulation ladder, the point/line ink split and the colour-model check on the shipped 800 px reference. Given the 6137 px London original it also re-runs the basemap hue ratio, the isolated-line alpha and the longest-straight-line test. The ring-matched ink ratio, London's accumulation strata and the dot-size mode have no shipped implementation.

## Superseded approaches

Each of these was wrong and is recorded so nobody repeats it.

- Box search centred on the photographer's own photo positions. The best box usually lies between points, and this cost 8 tourist labels.
- Box search with point-edge alignment only. It missed one photographer whose only qualifying box lies flush against Hanoi's western edge.
- Single-link clustering as a proxy for a city. It over-merged along dense corridors, with a median qualifying cluster 70 km across, 39% wider than 100 km and one at 2,479 km, and it called a few people a local of a "different city" that was greater Hanoi.
- A mask keyed on a coordinate string. When pin identity changed, 8 of the 10 keys silently stopped matching and 333 condemned photos went back onto the map while the file still claimed they were masked. The mask is now keyed on photo ids.
- Density squares sized by photographs. 44 of the 50 largest squares held a single photographer, with a rank correlation of 0.06 between photographs and photographers. It drew who uploads in bulk from one spot, not where people go.
