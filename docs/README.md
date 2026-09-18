# The pan-and-zoom version

`index.html` + `app.js` draw the same marks as `out/hanoi_locals_tourists_6137.png`,
blue local, red tourist and yellow unknown, with MapLibre GL JS from a CDN over
vector data generated in this repository: no API key, no tile service, nothing
but static files. `data/*.json` hold flat integer-delta arrays in units of
1e-5°, not GeoJSON, because the basemap is 440,368 vertices; `app.js` expands
them in the browser.

Rebuild them one process at a time (the Overpass extract alone costs ~1.2 GB):

    .venv/bin/python lat/web.py basemap     # data/basemap.json
    .venv/bin/python lat/web.py faithful    # data/faithful.json
    .venv/bin/python lat/web.py merged      # data/merged.json

The marks come out of `lat.fischer.build_marks` itself, and `lat/web.py`
refuses to write a file whose point and line counts disagree with
`out/stats.json` or `out/multi/stats.json`. Two deviations from the sheet are
deliberate and documented at the top of `app.js`: MapLibre projects in Web
Mercator rather than equirectangular (a 0.08% differential stretch across this
box), and the marks stop shrinking at 2 px so they stay visible when the whole
box is on screen. `?points=symbol` swaps the GL point path for icon symbols.
