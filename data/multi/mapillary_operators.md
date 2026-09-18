# Who operates the organisation accounts in the Mapillary Hanoi box

Scope: this file covers only the accounts that look like organisational camera
fleets or programmes. The remaining accounts in the box read as private
individuals and were deliberately not researched. Nothing here is about a
person: no names, no profile details, no residence. Where a source page named
individuals, those names were left out on purpose.

Method: public sources only, reached with web search and fetch. Company
websites, the Vietnamese business register aggregator, the OpenStreetMap wiki,
the Mapillary blog, LinkedIn company pages. No Mapillary account was probed
beyond the harvest dump that already exists in this repo.

| account | operator | HQ city | HQ country | fleet | countries | confidence |
| --- | --- | --- | --- | --- | --- | --- |
| bemaps2_hn | Be Group JSC (BeMaps) | Ho Chi Minh City | Vietnam | yes | Vietnam | high |
| bemaps_hn_kien | Be Group JSC (BeMaps) | Ho Chi Minh City | Vietnam | yes | Vietnam | high |
| bemaps3_sg | Be Group JSC (BeMaps) | Ho Chi Minh City | Vietnam | yes | Vietnam | high |
| bemaps_1pd | Be Group JSC (BeMaps) | Ho Chi Minh City | Vietnam | yes | Vietnam | medium |
| hn_right_1 | could not establish | - | - | yes | Vietnam (observed) | low |
| hn_right_2 | could not establish | - | - | yes | Vietnam (observed) | low |
| hn_left_2 | could not establish | - | - | yes | Vietnam (observed) | low |
| hn_front_1 | could not establish | - | - | yes | Vietnam (observed) | low |
| sg_front_3 | could not establish | - | - | yes | Vietnam (observed) | low |
| kaart_1 | Kaart Group, LLC | Grand Junction, Colorado | United States | yes | 65 to 75+ countries incl. Vietnam | medium |
| kaart_3 | Kaart Group, LLC | Grand Junction, Colorado | United States | yes | 65 to 75+ countries incl. Vietnam | medium |
| kaartcam | Kaart Group, LLC | Grand Junction, Colorado | United States | yes | 65 to 75+ countries incl. Vietnam | high |
| theonenetwork | TheOneNetwork JSC | Hanoi | Vietnam | yes | Vietnam | medium |
| phoenixmap_right | could not establish | - | - | yes | Vietnam (observed) | low |
| roadroid | Roadroid AB | Ljusdal | Sweden | yes | Sweden and client countries worldwide | medium |

## bemaps2_hn, bemaps_hn_kien, bemaps3_sg, bemaps_1pd

The prefix is a programme name, not a guess. Mapillary published a case study
in May 2024 on BeMaps, the in-house mapping programme of Be Group, the
Vietnamese ride hailing and delivery super app. The programme started in late
2022, began street-level capture in April 2023, put three riders on scooters
with GoPro Max 360 cameras, and covered close to all of Hanoi and Ho Chi Minh
City, about 9 million images and 27,000 km. Be Group JSC is registered in Ho
Chi Minh City, District 1, and uses OpenStreetMap as its primary map provider,
so the capture is a business programme rather than a hobby. The harvest agrees
with the case study on the technical side: these four accounts are 99.9 to 100
percent spherical, which is what a helmet-mounted GoPro Max produces, and the
suffixes match the two cities the programme covers, hn for Hanoi and sg for
Saigon. What no public source gives is a roster of account names, so the link
from each individual account to Be Group rests on the shared prefix plus the
matching capture profile. bemaps_1pd is marked medium rather than high because
it is small, 1,385 images over two days, and the suffix could belong to one
rider inside the programme rather than to a vehicle or city. If that is what it
is, it is an individual's account under an organisational prefix, and it was not
researched any further.

Sources:
- https://blog.mapillary.com/update/2024/05/16/Be-Group-Vietnam-Mapillary-Imagery.html
- https://be.com.vn/en/story/vietnamese-ride-hailing-startup-be-groups-alternative-approach-to-success/
- https://app.dealroom.co/companies/be_group_

## hn_right_1, hn_right_2, hn_left_2, hn_front_1, sg_front_3

Could not establish the operator. The naming is the clearest fleet signature in
the box, city code plus camera position plus a vehicle number, and the harvest
backs that reading: all five are 100 percent perspective imagery, the four
Hanoi accounts run on overlapping date ranges from November 2024 to October
2025 with 137 to 227 distinct capture days each, and together they hold about
470,000 images in the box. That is a multi-camera vehicle rig on a survey
schedule, not a hobbyist. But no public source names it. Searches across the
Mapillary blog and community forum, the OpenStreetMap community forum and wiki
organised editing lists, the OSM Vietnam channels, and Vietnamese-language
press for street-level capture turned up nothing carrying these account names
or this naming scheme. Two plausible contexts exist in Vietnam over the same
period, the Openmap.vn and Streetview.vn platform run by 44+ Technologies, and
Google Street View's Vietnam launch in June 2025, but neither is tied to these
accounts by any source found and Google does not publish to Mapillary. Recorded
as unknown rather than guessed. is_fleet is set true for these on the strength
of the repo's own harvest pattern, not on a public source.

Sources:
- https://en.wikipedia.org/wiki/List_of_street_view_services
- https://community.openstreetmap.org/t/osm-in-vietnam/86254
- https://virtualstreets.org/index.php/2025/06/29/google-street-view-returns-to-vietnam/

## kaart_1, kaart_3, kaartcam

Kaart Group, LLC is a geospatial services company registered with the Colorado
Secretary of State on 24 October 2013, registered office 734 Main Street, Grand
Junction, Colorado. It sells managed field data collection, OpenStreetMap
editing, street-level imagery and QA across a claimed 75 or more countries,
with staff in Colorado, California, Washington, Argentina, Brazil, Chile,
Colombia, Guatemala, Indonesia, Malaysia, Mexico, the Philippines and Romania.
The OpenStreetMap wiki lists it under Organised Editing as a corporate data
team, it is a bronze corporate member of the OSM Foundation, and its country
list includes Vietnam. The wiki and the OSM community record name kaartcam as
the username Kaart uses to upload street-level imagery to Mapillary and
OpenStreetCam, with over 11 million images shared to Mapillary, so kaartcam is
directly documented. kaart_1 and kaart_3 are marked medium: the naming reads as
numbered survey vehicles under the same brand, and the harvest puts all three
inside the same three-day window in Hanoi, 17 to 21 April 2019, with the same
100 percent perspective profile, but no source names the numbered accounts.

Sources:
- https://wiki.openstreetmap.org/wiki/Kaart
- https://kaart.com/
- https://opengovus.com/colorado-business/20131613940
- https://www.mapillary.com/showcase

## theonenetwork

TheOneNetwork is a Vietnamese real-estate data and advisory business in Hanoi.
Its LinkedIn company page gives the industry as real estate, the location as
Hanoi, a size of 11 to 50 employees and a founding year of 2023. A Vietnamese
business register aggregator lists Công ty Cổ phần TheOneNetwork, tax code
0111085880, registered address in Thanh Luong ward, Hai Ba Trung district,
Hanoi, registered 12 June 2025, with software publishing as the primary line
and real estate services among the others. Its own site sells a "360 Streetview
& Virtual Tour" service alongside flycam work, and feeds ground-level imagery
into its TheOneMap property price and planning map, with deployments listed in
Hanoi, Hung Yen, Vinh Phuc and Quang Ninh. So the organisation does run
street-level capture as a paid service, in Vietnam only, though the service page
frames it as property and development shoots rather than systematic road
coverage. The match to the account is name plus city plus capture type, the
account being 100 percent spherical in Hanoi across 16 days from June 2024 to
August 2025, which is consistent with commissioned shoots. No source ties the
Mapillary account to the company explicitly, hence medium. The 2025
registration date is later than the account's first upload, which fits a brand
that traded before it incorporated but is worth knowing.

Sources:
- https://www.theonenetwork.vn/streetview-virtual-tour
- https://www.theonenetwork.vn/gi%E1%BB%9Bi-thi%E1%BB%87u
- https://infocom.vn/cong-ty-co-phan-theonenetwork-0111085880.html
- https://www.linkedin.com/company/theonenetwork-vietnam
- https://theonemap.net/

## phoenixmap_right

Could not establish the operator. No mapping, survey or imagery business under
a Phoenix name could be tied to Vietnam or to this account. Searches returned
only Phoenix, Arizona city mapping, a US LiDAR hardware vendor, and unrelated
atlas publishers. The one internal signal is that the account carries the same
"_right" camera-position suffix as the hn and sg accounts above and its Hanoi
window, 29 November to 19 December 2024 over 21 days, sits inside theirs, so it
may be the same rig convention or the same operation under a different label.
That is an observation about the harvest, not evidence about a company, and it
is not enough to name one.

Sources:
- https://en.wikipedia.org/wiki/List_of_street_view_services
- https://ensun.io/search/geospatial-data/vietnam

## roadroid

Roadroid AB is a Swedish company founded in 2011 and based in Ljusdal, Sweden,
with a handful of employees. Its product is a smartphone app that measures road
roughness from the phone's accelerometer, reports it against the international
IRI standard, and captures geo-referenced photos or video of the road surface
alongside the measurements, uploading to a cloud service for road authorities.
The work grew out of research for the Swedish Road Administration and is sold
to road agencies and consultants in many countries, so the capture is a
business, but it is road condition survey work with imagery attached rather than
a street-view fleet. The name is distinctive enough that the account is almost
certainly the company's or its product's, which is why the operator identity is
solid, but nothing published confirms the Mapillary account itself, hence medium.
Worth noting for the map: this account holds exactly one image in the Hanoi box,
from 1 September 2017, so whatever it is, it has no bulk presence here.

Sources:
- https://www.crunchbase.com/organization/roadroid-ab
- https://pitchbook.com/profiles/company/118692-10
- https://www.davidpublisher.com/public/uploads/contribute/55472096c5198.pdf
- https://trid.trb.org/view/1264278

## What this file is and is not evidence for

The map's axis is residency, and residency is inferred from a contributor's own
imagery, nothing else. A contributor is read as local when their own uploads
span at least 30 days inside the Hanoi box, and as a visitor when their span
inside the box is shorter while they hold a 30-day span in some other city box.
That test looks only at dates and coordinates in the imagery the contributor
published. It does not use nationality, birthplace, citizenship, or any profile
field, and it cannot, because none of those are in the data.

An organisation's domicile is a different kind of fact and it answers a
different question. Kaart being registered in Colorado is evidence about Kaart
Group, LLC. It is not evidence that the person driving the car in Hanoi in April
2019 was American, and the map never claims that. What the domicile is useful
for here is reading the shape of the data: it explains why a single account can
hold a quarter of a million images, why several accounts share one date window,
and why a fleet's in-box span may be three days in one city and years in
another. An account like kaartcam falls on the visitor side of the residency
test because its Hanoi imagery spans two days while the same operator has long
spans elsewhere, which is a true statement about that account's imagery and
about a survey trip, not a statement about anyone's home.

So this file should be read as fleet bookkeeping. It says which accounts are
one organisation's cameras, so that the per-photographer count is not mistaken
for a count of people, and so that a fleet's classification can be explained
without anybody being labelled by nationality. Where the operator could not be
established, the account keeps its harvest-based fleet reading and no origin
claim is attached to it.
