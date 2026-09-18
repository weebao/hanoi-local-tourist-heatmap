/* Locals and Tourists: Hanoi - static viewer.
 *
 * Nothing here decides anything about the map. lat/web.py exports the marks
 * the 6137 px renderer draws (same gates, same counts) as integer-delta
 * arrays; this file expands them and hands them to MapLibre.
 *
 * Deliberate choices, so they are not mistaken for accidents:
 *  - MapLibre projects in Web Mercator, the renderer in equirectangular. Over
 *    a 0.218 deg box the difference is a differential stretch of 0.08%, about
 *    5 px on a 6137 px sheet, so the coordinates are shipped as lon/lat and
 *    left alone.
 *  - points are gl.POINTS in one custom layer: a GL point IS an opaque
 *    axis-aligned square, and one draw call keeps 42k of them cheap on a
 *    phone. The three classes share one buffer in shuffled order, which is
 *    the renderer's interleaving, so no class buries another.
 *  - 3 px is the mark size at the zoom where the box spans 6137 px (z 14.18).
 *    It scales with zoom from there, clamped to [2, 24] px: at the zoom that
 *    fits the whole box a 3 px mark would be half a pixel.
 */
'use strict';

var BOUNDS = [20.926386, 105.728233, 21.144091, 105.961466]; // Fischer's box
var S = BOUNDS[0], W = BOUNDS[1], N = BOUNDS[2], E = BOUNDS[3];
var PAD = 0.02;                       // max-bounds slack, ~2 km
var CLASSES = ['local', 'tourist', 'unknown'];
var COLORS = { local: '#0000FF', tourist: '#FF0000', unknown: '#FFFF00' };
var RGB = { local: [0, 0, 1], tourist: [1, 0, 0], unknown: [1, 1, 0] };
var LINE_ALPHA = 0.55;                // measured on the original, see STYLE.md
// zoom at which 512 px tiles put 6137 px across the box
var Z_NATIVE = Math.log(6137 * 360 / (512 * (E - W))) / Math.LN2;
var PT_MIN = 2, PT_MAX = 24, PT_AT_NATIVE = 3;

var $ = function (id) { return document.getElementById(id); };
var fmt = function (n) { return n.toLocaleString('en-US'); };
var status_ = function (t) { $('status').textContent = t || ''; };

/* ------------------------------------------------------------- projection */
function mercX(lon) { return (180 + lon) / 360; }
function mercY(lat) {
  return (180 - (180 / Math.PI) *
          Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360))) / 360;
}
// Mercator unit coordinates near 0.79 exhaust float32 at about 2 m, so the
// buffer holds offsets from the box centre and the origin is folded into the
// matrix in doubles instead.
var OX = mercX((W + E) / 2), OY = mercY((S + N) / 2);

/* ---------------------------------------------------------------- decoding */
// Every file is flat integers in units of 1e-5 deg with an [x, y] offset.
function decodePolylines(doc, chunk) {
  var d = doc.d, sc = doc.scale, ox = doc.off[0], oy = doc.off[1];
  var feats = [], cur = [], i = 0;
  while (i < d.length) {
    var n = d[i++], x = d[i++], y = d[i++];
    var co = [[(x + ox) / sc, (y + oy) / sc]];
    for (var k = 1; k < n; k++) {
      x += d[i++]; y += d[i++];
      co.push([(x + ox) / sc, (y + oy) / sc]);
    }
    cur.push(co);
    if (cur.length >= chunk) {
      feats.push({ type: 'Feature', properties: {},
                   geometry: { type: 'MultiLineString', coordinates: cur } });
      cur = [];
    }
  }
  if (cur.length) {
    feats.push({ type: 'Feature', properties: {},
                 geometry: { type: 'MultiLineString', coordinates: cur } });
  }
  return { type: 'FeatureCollection', features: feats };
}

function decodeLines(doc) {
  var sc = doc.scale, ox = doc.off[0], oy = doc.off[1], feats = [];
  for (var g = 0; g < doc.lines.length; g++) {
    var grp = doc.lines[g], d = grp.d, segs = [], px = 0, py = 0;
    for (var k = 0; k < grp.n; k++) {
      var x0 = px + d[4 * k], y0 = py + d[4 * k + 1];
      var x1 = x0 + d[4 * k + 2], y1 = y0 + d[4 * k + 3];
      px = x0; py = y0;
      segs.push([[(x0 + ox) / sc, (y0 + oy) / sc],
                 [(x1 + ox) / sc, (y1 + oy) / sc]]);
    }
    feats.push({ type: 'Feature', properties: { c: grp['class'] },
                 geometry: { type: 'MultiLineString', coordinates: segs } });
  }
  return { type: 'FeatureCollection', features: feats };
}

// -> {buf: Float32Array [dx, dy, class] * n, n, byClass, geojson()}
function decodePoints(doc) {
  var sc = doc.scale, ox = doc.off[0], oy = doc.off[1];
  var total = 0, byClass = { local: 0, tourist: 0, unknown: 0 };
  for (var g = 0; g < doc.points.length; g++) {
    total += doc.points[g].n;
    byClass[doc.points[g]['class']] += doc.points[g].n;
  }
  var buf = new Float32Array(total * 3), lons = new Float64Array(total);
  var lats = new Float64Array(total), cls = new Uint8Array(total), i = 0;
  for (g = 0; g < doc.points.length; g++) {
    var grp = doc.points[g], d = grp.d, ci = CLASSES.indexOf(grp['class']);
    var x = 0, y = 0;
    for (var k = 0; k < grp.n; k++) {
      x += d[2 * k]; y += d[2 * k + 1];
      var lon = (x + ox) / sc, lat = (y + oy) / sc;
      lons[i] = lon; lats[i] = lat; cls[i] = ci;
      buf[3 * i] = mercX(lon) - OX;
      buf[3 * i + 1] = mercY(lat) - OY;
      buf[3 * i + 2] = ci;
      i++;
    }
  }
  // Interleave the classes, as draw_marks does, with a fixed seed: drawing
  // one class after another would let the last one bury the others.
  var seed = 20100615 >>> 0;                   // mulberry32: exact 32-bit
  var rnd = function () {
    seed = (seed + 0x6D2B79F5) >>> 0;
    var t = Math.imul(seed ^ (seed >>> 15), seed | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  for (var j = total - 1; j > 0; j--) {
    var s = Math.floor(rnd() * (j + 1));
    for (var c = 0; c < 3; c++) {
      var t = buf[3 * j + c]; buf[3 * j + c] = buf[3 * s + c]; buf[3 * s + c] = t;
    }
  }
  return {
    buf: buf, n: total, byClass: byClass,
    geojson: function () {                       // only for the fallback path
      var feats = new Array(total);
      for (var q = 0; q < total; q++) {
        feats[q] = { type: 'Feature',
                     properties: { c: CLASSES[cls[q]] },
                     geometry: { type: 'Point', coordinates: [lons[q], lats[q]] } };
      }
      return { type: 'FeatureCollection', features: feats };
    }
  };
}

/* -------------------------------------------------------------- point size */
function pointSizePx(z) {
  var s = PT_AT_NATIVE * Math.pow(2, z - Z_NATIVE);
  return Math.max(PT_MIN, Math.min(PT_MAX, s));
}

/* ---------------------------------------------------------------- the map */
var shown = { local: true, tourist: true, unknown: true };
var linesOn = true;
var datasets = {};                  // name -> {points, lines(geojson)}
var current = null;
var forceSymbols = /[?&]points=symbol/.test(location.search);

var map = new maplibregl.Map({
  container: 'map',
  style: {
    version: 8,
    sources: {},
    layers: [{ id: 'bg', type: 'background',
               paint: { 'background-color': '#ffffff' } }]
  },
  bounds: [[W, S], [E, N]],
  fitBoundsOptions: { padding: 6, animate: false },
  maxBounds: [[W - PAD, S - PAD], [E + PAD, N + PAD]],
  minZoom: 9.5,
  maxZoom: 17,
  renderWorldCopies: false,
  dragRotate: false,
  pitchWithRotate: false,
  attributionControl: false,
  fadeDuration: 0
});
map.touchZoomRotate.disableRotation();
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
map.addControl(new maplibregl.ScaleControl({ maxWidth: 90, unit: 'metric' }),
               'bottom-left');
map.addControl(new maplibregl.AttributionControl({
  compact: window.innerWidth < 560,
  customAttribution: [
    'Basemap &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors (ODbL)',
    'Photo metadata: YFCC100M, Wikimedia Commons, iNaturalist',
    'Method: <a href="https://www.flickr.com/photos/walkingsf/albums/72157624209158632/">Erica Fischer, Locals and Tourists</a>',
    '<a href="https://github.com/weebao/hanoi-local-tourist-heatmap">repo</a>'
  ]
}));

/* ----------------------------------------------------- points: one GL call */
var VS = [
  'attribute vec2 a_pos;',
  'attribute float a_cls;',
  'uniform mat4 u_matrix;',
  'uniform float u_size;',
  'uniform vec3 u_show;',
  'varying vec3 v_color;',
  'void main() {',
  '  float show = a_cls < 0.5 ? u_show.x : (a_cls < 1.5 ? u_show.y : u_show.z);',
  '  v_color = a_cls < 0.5 ? vec3(0.0, 0.0, 1.0)',
  '          : (a_cls < 1.5 ? vec3(1.0, 0.0, 0.0) : vec3(1.0, 1.0, 0.0));',
  '  if (show < 0.5) {',        // parked outside the clip volume, not drawn
  '    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);',
  '    gl_PointSize = 0.0;',
  '    return;',
  '  }',
  '  gl_Position = u_matrix * vec4(a_pos, 0.0, 1.0);',
  '  gl_PointSize = u_size;',
  '}'
].join('\n');

var FS = [
  'precision mediump float;',
  'varying vec3 v_color;',
  'void main() { gl_FragColor = vec4(v_color, 1.0); }'
].join('\n');

var pointsLayer = {
  id: 'points',
  type: 'custom',
  renderingMode: '2d',
  ready: false,
  _m: new Float32Array(16),
  _maxPt: 32,

  onAdd: function (m, gl) {
    var compile = function (type, src) {
      var sh = gl.createShader(type);
      gl.shaderSource(sh, src);
      gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
        throw new Error('shader: ' + gl.getShaderInfoLog(sh));
      }
      return sh;
    };
    var p = gl.createProgram();
    gl.attachShader(p, compile(gl.VERTEX_SHADER, VS));
    gl.attachShader(p, compile(gl.FRAGMENT_SHADER, FS));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
      throw new Error('link: ' + gl.getProgramInfoLog(p));
    }
    this.program = p;
    this.aPos = gl.getAttribLocation(p, 'a_pos');
    this.aCls = gl.getAttribLocation(p, 'a_cls');
    this.uMatrix = gl.getUniformLocation(p, 'u_matrix');
    this.uSize = gl.getUniformLocation(p, 'u_size');
    this.uShow = gl.getUniformLocation(p, 'u_show');
    this.gl = gl;
    this.vbo = gl.createBuffer();
    var range = gl.getParameter(gl.ALIASED_POINT_SIZE_RANGE);
    if (range && range[1]) { this._maxPt = range[1]; }
    this.ready = true;
    if (current) { this.upload(gl, current.points.buf); }
  },

  upload: function (gl, data) {
    gl.bindBuffer(gl.ARRAY_BUFFER, this.vbo);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
    this.count = data.length / 3;
  },

  setData: function (data) {
    this._pending = data;
    if (this.ready) { this.upload(this.gl, data); this._pending = null; }
    map.triggerRepaint();
  },

  render: function (gl, args) {
    if (!this.ready) { return; }
    if (this._pending) { this.upload(gl, this._pending); this._pending = null; }
    if (!this.count || !current) { return; }
    // 4.x hands over the matrix itself; 5.x an options object.
    var src = args;
    if (src && !src.length) {
      src = (src.defaultProjectionData && src.defaultProjectionData.mainMatrix)
            || src.modelViewProjectionMatrix;
    }
    if (!src) { return; }
    var m = this._m;
    for (var i = 0; i < 12; i++) { m[i] = src[i]; }
    for (var r = 0; r < 4; r++) {   // fold the buffer's origin into the matrix
      m[12 + r] = src[r] * OX + src[4 + r] * OY + src[12 + r];
    }
    var dpr = window.devicePixelRatio || 1;
    var size = Math.min(pointSizePx(map.getZoom()) * dpr, this._maxPt);

    gl.useProgram(this.program);
    gl.uniformMatrix4fv(this.uMatrix, false, m);
    gl.uniform1f(this.uSize, size);
    gl.uniform3f(this.uShow, shown.local ? 1 : 0, shown.tourist ? 1 : 0,
                 shown.unknown ? 1 : 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.vbo);
    gl.enableVertexAttribArray(this.aPos);
    gl.vertexAttribPointer(this.aPos, 2, gl.FLOAT, false, 12, 0);
    gl.enableVertexAttribArray(this.aCls);
    gl.vertexAttribPointer(this.aCls, 1, gl.FLOAT, false, 12, 8);
    gl.drawArrays(gl.POINTS, 0, this.count);
  }
};

/* Fallback: square icons in a symbol layer. Reachable with ?points=symbol so
 * the path can be looked at on purpose, not only after a GL failure. */
var symbolPoints = {
  added: false,
  sizeExpr: ['/', ['max', PT_MIN, ['min', PT_MAX,
              ['*', PT_AT_NATIVE, ['^', 2, ['-', ['zoom'], Z_NATIVE]]]]], 8],
  add: function () {
    var dpr = Math.max(1, Math.round(window.devicePixelRatio || 1));
    var side = 8 * dpr;
    for (var i = 0; i < CLASSES.length; i++) {
      var name = 'sq-' + CLASSES[i];
      if (map.hasImage(name)) { continue; }
      var rgb = RGB[CLASSES[i]], data = new Uint8Array(side * side * 4);
      for (var p = 0; p < side * side; p++) {
        data[4 * p] = rgb[0] * 255; data[4 * p + 1] = rgb[1] * 255;
        data[4 * p + 2] = rgb[2] * 255; data[4 * p + 3] = 255;
      }
      map.addImage(name, { width: side, height: side, data: data },
                   { pixelRatio: dpr });
    }
    map.addSource('pts', { type: 'geojson', data: current.points.geojson() });
    map.addLayer({
      id: 'points-sym', type: 'symbol', source: 'pts',
      layout: {
        'icon-image': ['concat', 'sq-', ['get', 'c']],
        'icon-size': this.sizeExpr,
        'icon-allow-overlap': true,
        'icon-ignore-placement': true
      }
    });
    this.added = true;
    this.filter();
  },
  setData: function () {
    if (this.added) { map.getSource('pts').setData(current.points.geojson()); }
  },
  filter: function () {
    if (!this.added) { return; }
    var on = CLASSES.filter(function (c) { return shown[c]; });
    map.setFilter('points-sym', ['in', ['get', 'c'], ['literal', on]]);
  }
};
var usingSymbols = false;

/* ----------------------------------------------------------------- loading */
function fetchJSON(url) {
  return fetch(url).then(function (r) {
    if (!r.ok) { throw new Error(url + ': HTTP ' + r.status); }
    return r.json();
  });
}

function loadDataset(name) {
  if (datasets[name]) { return Promise.resolve(datasets[name]); }
  status_('loading ' + name + ' photographs...');
  return fetchJSON('data/' + name + '.json').then(function (doc) {
    datasets[name] = {
      points: decodePoints(doc),
      lines: decodeLines(doc),
      nLines: doc.counts.lines,
      label: doc.label
    };
    return datasets[name];
  });
}

function showDataset(name) {
  return loadDataset(name).then(function (ds) {
    current = ds;
    if (usingSymbols) { symbolPoints.setData(); } else { pointsLayer.setData(ds.points.buf); }
    if (map.getSource('lines')) { map.getSource('lines').setData(ds.lines); }
    for (var i = 0; i < CLASSES.length; i++) {
      $('n-' + CLASSES[i]).textContent = fmt(ds.points.byClass[CLASSES[i]]);
    }
    $('n-lines').textContent = fmt(ds.nLines);
    status_('');
    applyVisibility();
    map.triggerRepaint();
  }).catch(function (e) {
    status_('could not load ' + name + ': ' + e.message);
  });
}

function applyVisibility() {
  for (var i = 0; i < CLASSES.length; i++) {
    var c = CLASSES[i];
    if (map.getLayer('lines-' + c)) {
      map.setLayoutProperty('lines-' + c, 'visibility',
                            (linesOn && shown[c]) ? 'visible' : 'none');
    }
  }
  if (usingSymbols) { symbolPoints.filter(); }
  map.triggerRepaint();
}

map.on('load', function () {
  status_('loading basemap...');
  fetchJSON('data/basemap.json').then(function (doc) {
    map.addSource('basemap', {
      type: 'geojson',
      data: decodePolylines(doc, 128),
      maxzoom: 15,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors (ODbL)'
    });
    map.addLayer({
      id: 'basemap', type: 'line', source: 'basemap',
      // one hue, one width, no hierarchy, no fills - as measured on the
      // London original (STYLE.md)
      paint: { 'line-color': '#AAAA00', 'line-width': 1 }
    // under the connecting lines: the basemap arrives after them, because it
    // is fetched, and a later addLayer would otherwise sit on top of them.
    }, 'lines-local');
    status_('');
  }).catch(function (e) {
    status_('could not load the basemap: ' + e.message);
  });

  map.addSource('lines', {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] }
  });
  for (var i = 0; i < CLASSES.length; i++) {
    var c = CLASSES[i];
    map.addLayer({
      id: 'lines-' + c, type: 'line', source: 'lines',
      filter: ['==', ['get', 'c'], c],
      paint: { 'line-color': COLORS[c], 'line-width': 1,
               'line-opacity': LINE_ALPHA }
    });
  }

  if (forceSymbols) {
    usingSymbols = true;
  } else {
    try {
      map.addLayer(pointsLayer);
    } catch (e) {
      usingSymbols = true;
      if (map.getLayer('points')) { map.removeLayer('points'); }
      status_('points: GL path unavailable (' + e.message + '), using icons');
    }
  }

  showDataset('faithful').then(function () {
    if (usingSymbols && !symbolPoints.added) { symbolPoints.add(); }
  });
});

/* ---------------------------------------------------------------- controls */
var radios = document.querySelectorAll('input[name="dataset"]');
for (var i = 0; i < radios.length; i++) {
  radios[i].addEventListener('change', function (ev) {
    if (ev.target.checked) { showDataset(ev.target.value); }
  });
}
var boxes = document.querySelectorAll('input.cls');
for (i = 0; i < boxes.length; i++) {
  boxes[i].addEventListener('change', function (ev) {
    shown[ev.target.value] = ev.target.checked;
    applyVisibility();
  });
}
$('lines').addEventListener('change', function (ev) {
  linesOn = ev.target.checked;
  applyVisibility();
});
if (window.innerWidth < 560) { $('panel').open = false; }
