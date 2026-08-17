/* The Living Atlas — atlas relief board, rendered in three.js.
 *
 * WHAT THIS DRAWS (docs/MARKETING_CLOSED_ALPHA.md, "Visual contract: atlas
 * board", as opened by Amendment 2):
 *
 *   - the twelve cities at their exact x/y under one uniform scale, carrying
 *     their populations, grid references, terrain, port and magic-free flags;
 *   - the fourteen roads exactly as listed, weighted by quality, labelled with
 *     their mileage and movement cost;
 *   - around each city a terrain-textured *mound* from its terrain label;
 *   - the landmass the 2D map draws for this map, with its coast and the sea
 *     outside it, and the three region names;
 *   - and: "The page may rotate or tilt the board."
 *
 * THE ONE THING TO KEEP STRAIGHT ABOUT THE COAST. Before Amendment 2 this file
 * drew twelve mounds on empty paper, because the contract forbade a shoreline
 * the map does not have. The shoreline is still not surveyed: calib_12.json has
 * no geography file, so webapp/mapview.py falls back to a padded convex hull of
 * the road-connected cities and that hull is what both the app and this board
 * now draw. It is a confine, not a coast. The page says so in the legend, and
 * scripts/build_public_board.py carries mapview's own polygon across rather
 * than recomputing a lookalike — so if the app's land ever changes shape, this
 * board changes with it instead of quietly disagreeing.
 *
 * Elevation is still only the terrain labels; nothing is interpolated between
 * cities. The mound heights are the labels and nothing else:
 *   hills -> tall, plain -> low, desert -> lowest and flattest.
 */

import * as THREE from "three";
import { OrbitControls } from "./vendor/OrbitControls.js?v=h12";

/* Board units. One unit of fractional map coordinate = SU units, on both
   axes, so the recorded geometry is never stretched. */
const SU = 1000;
/* Water margin: how much sea is drawn outside the coast before the sheet
   ends. It was briefly 150, when the frame was measured from the CITIES and
   the margin had to be wide enough to cover a coastline that ran past them.
   The frame is measured from the coast itself now, so this is no longer
   holding anything in -- it only decides how much open water frames the land.
   The neatline sits REVEAL + SHEET_INSET = 39 units inside the sheet edge, so
   anything above that keeps the shore inside the ruling; 90 leaves the vale
   sitting in water without half the picture being empty sea. */
const PAD = 90;
/* Mound footprint, before the merge guard. The game draws a city as a 6-15px
   marker on a 1400px map — about 1% of the width — and everything between the
   cities is road network. Inflated to 72 the mounds swallowed the roads
   completely: 78 road pixels on the whole board, 0.02%. The web is the map, so
   the markers stay small. */
const DISK_R_MAX = 30;
const SHEET_T = 26;       // printed board thickness

/* Elevation, entirely derived from the terrain label. The board is ~810 units
   across and the closest two cities are 68 apart, which caps the footprint at
   DISK_R: any wider and neighbouring mounds would fuse into the interpolated
   continent the contract forbids. So legibility has to come from height, the
   way a relief map uses vertical exaggeration. The ordering is the data;
   the amplitude is presentation. */
const MOUND_H = { hills: 62, plain: 32, desert: 23 };

/* Colour, from the same terrain label as the height. This is not decoration:
   the four jpgs in textures/ are pure greyscale grain — measured saturation
   0.000, brightness 225-237 — so desert, hills and plain arrive as the same
   grey image and the board renders as one brown wash whatever the lighting
   does. The texture supplies grain; the label supplies identity. */
/* Hypsometric tinting, the relief-map convention: lowland green, upland ochre,
   arid gold. The previous set was three browns within 0.06 of each other in
   hue and 0.10 in value, which is a distinction the eye cannot make at this
   size — twelve mounds on a tan sheet came out as one wash. These are the same
   idea the code always had, finally far enough apart to be read. Green here is
   a lowland tint on a printed sheet, not water: the sea is forbidden by the
   contract and there is none, and no closed shoreline exists to imply one. */
const TERRAIN_TINT = {
  hills:  0x8f7140,       // upland ochre
  plain:  0x7f945a,       // calib_12 says "plain"; mapview says "plains"
  plains: 0x7f945a,       // lowland sage
  desert: 0xd2b168,       // arid gold
  forest: 0x4f7a55,
  woods:  0x4f7a55,
  mountains: 0x8b8172,
  coastal: 0x6f9aa6,
  river:  0x5f86a6,
  swamp:  0x6b7a52
};
/* The sheet is background and has to behave like it. A flat plane under a
   directional light shades identically at every point, so left bright it
   becomes one enormous flat mass — 86% of the frame inside a single 32-value
   band — and the mounds have nothing to stand against. Dropping it lets the
   relief be the subject. */
/* The stock the map is printed ON, which is not the same thing as the water.
   An earlier pass copied mapview._background wholesale, which brought the
   game's `#mapSea` gradient with it and made the entire board read as open
   ocean with twelve islands in it. The sheet is board stock; the sea is a
   printed layer on top of it, bounded by the coast, and it stops where the
   land starts. The 48-unit grid rules over both: a graticule is a map
   convention, not a claim about geography.

   Amendment 2 brought the land itself. It comes from compute_landmasses(),
   which hulls the road-connected cities — the same polygon the app draws for
   this map, carried across rather than recomputed. It is a confine and the
   legend says so. */
/* Paper, not mud. The sheet was a mid-tan (#9c9074) barely a step from the
   mound tints sitting on it, so relief and ground shared one value band and
   nothing had an edge. Cream reads as the printed stock it is meant to be and
   gives every tinted mound and inked road something to sit against. The DOM
   labels already assume a light ground (dark type on a pale halo). */
const SHEET_TOP = "#efe6d0";
const SHEET_BOTTOM = "#dccfb1";
/* Ink for the ruling. Parsed as rgba because these are line colours with an
   opacity each, and a one-pixel rule carries far less ink than the wide
   strokes an earlier pass drew into a texture — hence the stronger alphas. */
const GRID_MINOR = "rgba(96, 82, 58, 0.38)";
const GRID_MAJOR = "rgba(88, 73, 49, 0.62)";
const NEATLINE = "rgba(74, 61, 40, 0.92)";
const GRID_STEP = 48;          // board units per grid square, as in mapview
const GRID_MAJOR_EVERY = 5;    // a heavier rule every fifth square
const SHEET_INSET = 30;        // board units from sheet edge to the neatline

/* Sea, land and coast. Printed colours, not lighting: these are inks on the
   same plate as the graticule, laid under the ruling the way a printed map
   puts its water and its land under its grid. The sea is a pale plate blue
   rather than the game's near-black navy — the board is cream stock seen on a
   table, and a navy field on cream reads as a hole cut in the paper. */
/* How far the land stands out of the water. Everything else in the scene --
   mounds, roads, rings, tokens, labels -- is placed against y = 0, so y = 0 is
   the LAND surface and the water goes below it rather than the land being
   lifted above it. That keeps every existing height in the file meaning what
   it meant, and makes the coast a real edge with a real drop instead of a
   colour change painted on a flat plate. */
const LAND_H = 30;
const SEA_TINT = 0x9fc4d8;
const LAND_TINT = 0x76874f;   // matches HYPSO's shore band, so the
                              // terrain grid's ragged edge dies into the cap
const COAST_INK = 0x4a6070;
const LAND_CLIFF = 0x8f9670;   // the cut edge of the same ground, stepped down
const SHEET_EDGE = 0x3a3125;   // binder board under the print, seen at this tilt

/* Roads carry their quality in colour and dash, exactly as the game draws
   them. Width follows mapview's stroke weights, scaled to board units. */
/* Inked down a stop from mapview's screen values. Those are strokes on the
   game's near-black navy; here they are printed on cream, and a pale road on
   pale paper is not a road. Hue and dash — the parts that carry quality — are
   unchanged. */
const ROAD_STYLE = {
  excellent: { color: 0x2f7d4a, width: 7.0, dashed: false },
  good:      { color: 0x4a5a70, width: 6.1, dashed: false },
  fair:      { color: 0xa8702a, width: 5.3, dashed: true  },
  poor:      { color: 0xa8443a, width: 4.7, dashed: true  },
  sea:       { color: 0x2b7fa8, width: 5.7, dashed: true  }
};
const ROAD_FALLBACK = { color: 0x5a6474, width: 5.1, dashed: false };
/* Every road gets a wider, near-black bed under it, the way an engraved map
   carries a casing outside its ink. It is what stops a thin coloured ribbon
   from dissolving into the paper grain. */
const ROAD_CASING = 0x2b2317;

const PER_RING = 9;
const STEP_DEG = 17;

/* ------------------------------------------------------------ procedural art
   Generated on a canvas so the page still ships four jpgs and nothing else. */

function canvasTexture(w, h, draw) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  draw(c.getContext("2d"), w, h);
  const tex = new THREE.CanvasTexture(c);
  tex.anisotropy = 4;
  return tex;
}

/* A soft-edged stripe, used as the alpha of a road so its edges feather into
   the sheet instead of ending on a hard line. */
function roadAlpha(dashed) {
  return canvasTexture(64, 32, function (ctx, w, h) {
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    // Only just enough feathering to avoid a hard aliased edge: a wide ramp
    // ate most of the stroke's width and left the thin roads barely there.
    grad.addColorStop(0.0, "#000");
    grad.addColorStop(0.14, "#fff");
    grad.addColorStop(0.86, "#fff");
    grad.addColorStop(1.0, "#000");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);
    if (dashed) {
      ctx.globalCompositeOperation = "destination-out";
      ctx.fillStyle = "#000";
      for (let x = 0; x < w; x += 20) { ctx.fillRect(x + 13, 0, 7, h); }
    }
  });
}

/* An ownership ring: solid for a secured city, dashed for one merely stood in.
   Drawn white and tinted by the material, so two textures serve both seats. */
function ringTexture(dashed) {
  return canvasTexture(512, 512, function (ctx, w) {
    const r = w * 0.38;
    const mid = w / 2;
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = dashed ? w * 0.030 : w * 0.044;
    ctx.lineCap = "butt";
    if (dashed) { ctx.setLineDash([w * 0.052, w * 0.062]); }
    ctx.beginPath();
    ctx.arc(mid, mid, r, 0, Math.PI * 2);
    ctx.stroke();
  });
}

/* A small deterministic PRNG, so a mound's relief is a property of the city
   rather than of when the page happened to load. */
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function hashKey(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/* The paper itself, and nothing else. Every ruled line on this board is
   geometry, not texture — see graticuleGeometry below for why — so all this
   has to carry is tone, which is low-frequency and therefore safe to minify.
   Drawn at the sheet's own aspect ratio so the mottle is not stretched. */
function sheetTexture(sheetW, sheetD) {
  const W = 1024;
  const H = Math.max(256, Math.min(1024, Math.round(W * sheetD / sheetW)));
  return canvasTexture(W, H, function (ctx) {
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, SHEET_TOP);
    grad.addColorStop(1, SHEET_BOTTOM);
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);

    /* Plate tone: the uneven ink-take of a printed sheet. Kept broad and very
       faint, and warmer rather than darker. A first pass laid these down with
       multiply blending and took the whole sheet a stop and a half down —
       cream became a dirty grey, which is the exact failure this rewrite set
       out to undo. Paper varies; it does not soil. */
    const rnd = mulberry32(0x5A11E);
    for (let i = 0; i < 150; i++) {
      const cx = rnd() * W, cy = rnd() * H, r = 180 + rnd() * 420;
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
      g.addColorStop(0, rnd() < 0.55 ? "rgba(255,252,242,0.13)"
                                     : "rgba(206,190,158,0.10)");
      g.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = g;
      ctx.fillRect(cx - r, cy - r, r * 2, r * 2);
    }

  });
}

/* The ruling: the graticule, the neatline and the corner ticks, as line
   geometry lying just above the plate.

   This does not belong in a texture, and two passes at putting it in one both
   failed the same way. The board is seen at 48 degrees, so its far half is
   minified several times over; a ruled line there falls well under one screen
   pixel, and a minified hairline does not fade politely — it beats against the
   mip chain and shatters the plate into horizontal dashes. Thickening the rule
   only moved the failure further back. Anisotropic filtering is the textbook
   answer and it is not a guarantee: the level is capped by the driver, and a
   software rasteriser may ignore it entirely.

   Lines have none of that problem. They are rasterised from the geometry every
   frame under the renderer's own multisampling, so they stay one clean pixel
   at any depth and simply thin out with distance — which is what an engraved
   rule does anyway. Major and minor separate by value rather than by width,
   as on a printed plate.

   Nothing drawn here is geography. A ruled grid, a border and corner ticks are
   print conventions and make no claim about land, water or elevation. */
function graticuleGeometry(halfX, halfZ, y) {
  const minor = [], major = [], neat = [];

  function span(list, n, vertical) {
    const at = n * GRID_STEP;
    if (vertical) {
      if (Math.abs(at) >= halfX) { return; }
      list.push(at, y, -halfZ, at, y, halfZ);
    } else {
      if (Math.abs(at) >= halfZ) { return; }
      list.push(-halfX, y, at, halfX, y, at);
    }
  }
  // Ruled from the centre outwards, so the middle of the board lands on a
  // crossing however the sheet is sized.
  const nx = Math.ceil(halfX / GRID_STEP), nz = Math.ceil(halfZ / GRID_STEP);
  for (let n = -nx; n <= nx; n++) {
    span(Math.abs(n) % GRID_MAJOR_EVERY === 0 ? major : minor, n, true);
  }
  for (let n = -nz; n <= nz; n++) {
    span(Math.abs(n) % GRID_MAJOR_EVERY === 0 ? major : minor, n, false);
  }

  // Neatline: the plate border, doubled, with a tick run past each corner.
  function frame(hx, hz) {
    const c = [[-hx, -hz], [hx, -hz], [hx, hz], [-hx, hz]];
    for (let i = 0; i < 4; i++) {
      const a = c[i], b = c[(i + 1) % 4];
      neat.push(a[0], y, a[1], b[0], y, b[1]);
    }
  }
  frame(halfX, halfZ);
  frame(halfX - 7, halfZ - 7);
  const TICK = 15;
  [[-1, -1], [1, -1], [1, 1], [-1, 1]].forEach(function (s) {
    const x = halfX * s[0], z = halfZ * s[1];
    neat.push(x, y, z, x + TICK * s[0], y, z);
    neat.push(x, y, z, x, y, z + TICK * s[1]);
  });

  function geo(arr) {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(arr, 3));
    return g;
  }
  return { minor: geo(minor), major: geo(major), neat: geo(neat) };
}

/* A contact pool: the soft darkening where a solid form meets the sheet.
   Cheap stand-in for ambient occlusion, and the single thing that stops each
   mound from looking pasted on. Opaque at the centre, gone at the rim. */
function contactTexture() {
  return canvasTexture(256, 256, function (ctx, w) {
    const mid = w / 2;
    const g = ctx.createRadialGradient(mid, mid, 0, mid, mid, mid);
    g.addColorStop(0.00, "rgba(255,255,255,0.62)");
    g.addColorStop(0.42, "rgba(255,255,255,0.34)");
    g.addColorStop(0.72, "rgba(255,255,255,0.09)");
    g.addColorStop(1.00, "rgba(255,255,255,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, w);
  });
}

/* Contour lines, cut into a standard material rather than painted into a
   texture, so they follow the geometry exactly and stay one pixel wide at any
   zoom. This is what makes the mounds read as surveyed relief instead of as
   lumps: a relief map's whole grammar is the contour.

   `step` is deliberately never a whole fraction of the mound height. On a
   perfectly flat plateau fwidth() collapses to zero, and if the plateau sat
   exactly on a contour the smoothstep would flood the entire top. */
function applyContours(material, step) {
  material.onBeforeCompile = function (shader) {
    shader.uniforms.uContourStep = { value: step };
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>",
               "#include <common>\nvarying float vRelief;")
      .replace("#include <begin_vertex>",
               "#include <begin_vertex>\nvRelief = position.y;");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>",
               "#include <common>\nvarying float vRelief;\nuniform float uContourStep;")
      .replace("#include <map_fragment>", [
        "#include <map_fragment>",
        "{",
        "  float h = vRelief / uContourStep;",
        "  float f = fract(h);",
        "  float w = max(fwidth(h) * 1.15, 0.0012);",
        "  float line = 1.0 - smoothstep(0.0, w, min(f, 1.0 - f));",
        "  float major = (mod(floor(h), 5.0) < 0.5) ? 1.0 : 0.6;",
        "  diffuseColor.rgb *= mix(1.0, 0.66, line * 0.85 * major);",
        "}"
      ].join("\n"));
  };
  // Materials that differ only by uniform still share a program; without this
  // three would hand the contoured mounds a cached uncontoured shader.
  material.customProgramCacheKey = function () { return "atlas-contour"; };
  return material;
}

/* The soft field under a secured city. */
function glowTexture() {
  return canvasTexture(256, 256, function (ctx, w) {
    const mid = w / 2;
    const grad = ctx.createRadialGradient(mid, mid, 0, mid, mid, mid);
    grad.addColorStop(0.00, "rgba(255,255,255,0.85)");
    grad.addColorStop(0.45, "rgba(255,255,255,0.28)");
    grad.addColorStop(1.00, "rgba(255,255,255,0)");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, w);
  });
}

/* A road as the game draws it: not a straight line but a quadratic bow, so
   parallel routes read as paths rather than a grid. mapview bows by
   min(28, length * 0.08) and picks the side from the road id's character sum,
   which keeps the choice stable across renders — same rule here, off the
   endpoint ids, since the public board has no road ids. */
function roadRibbon(ax, az, bx, bz, width, key, height) {
  const dx = bx - ax, dz = bz - az;
  const len = Math.hypot(dx, dz) || 1;
  let sum = 0;
  for (let i = 0; i < key.length; i++) { sum += key.charCodeAt(i); }
  const bow = Math.min(28, len * 0.08) * (sum % 2 === 0 ? 1 : -1);
  const cx = (ax + bx) / 2 + (-dz / len) * bow;
  const cz = (az + bz) / 2 + (dx / len) * bow;

  const SEG = 28;
  const pos = [], uv = [], idx = [];
  for (let i = 0; i <= SEG; i++) {
    const t = i / SEG, mt = 1 - t;
    const px = mt * mt * ax + 2 * mt * t * cx + t * t * bx;
    const pz = mt * mt * az + 2 * mt * t * cz + t * t * bz;
    const tx = 2 * mt * (cx - ax) + 2 * t * (bx - cx);
    const tz = 2 * mt * (cz - az) + 2 * t * (bz - cz);
    const tl = Math.hypot(tx, tz) || 1;
    const nx = -tz / tl, nz = tx / tl;
    /* Draped, not flat. A road laid at y = 0 across a landscape with 60 units
       of relief in it disappears into the first hill it meets and floats over
       the first valley. Each edge of the ribbon is sampled at its own point,
       so the strip banks with the ground it crosses instead of merely rising
       with it. */
    const lx = px + nx * width / 2, lz = pz + nz * width / 2;
    const rx = px - nx * width / 2, rz = pz - nz * width / 2;
    pos.push(lx, height(lx, lz), lz);
    pos.push(rx, height(rx, rz), rz);
    uv.push(t, 1, t, 0);
    if (i < SEG) {
      const b = i * 2;
      idx.push(b, b + 1, b + 2, b + 1, b + 3, b + 2);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  geo.setIndex(idx);
  geo.computeVertexNormals();
  geo.userData.length = len;
  return geo;
}

/* ----------------------------------------------------------------- geometry */

/* How much a terrain breaks up its own silhouette, and in what way.
     amp   — relief as a fraction of the mound height
     lobes — how many summits or ridges run around the mound
     skew  — a single one-per-turn term, i.e. an asymmetric form
   Hills get several ridges; a plain is a broad dome that barely moves; a
   desert mound is one crescent dune, low and lopsided. */
/* `plateau` is how much of the radius is held flat before the skirt begins.
   Kept small: a wide plateau with a smoothstep shoulder is a tree stump, which
   is what the first pass rendered twelve of. A dome that only flattens near
   the summit reads as ground. */
const MOUND_RELIEF = {
  hills:  { amp: 0.30, lobes: [3, 5, 8], skew: 0.10, plateau: 0.14 },
  plain:  { amp: 0.16, lobes: [2, 4],    skew: 0.08, plateau: 0.22 },
  plains: { amp: 0.16, lobes: [2, 4],    skew: 0.08, plateau: 0.22 },
  desert: { amp: 0.15, lobes: [2, 3],    skew: 0.28, plateau: 0.18 }
};
const MOUND_RELIEF_FALLBACK = MOUND_RELIEF.plain;
// How many times the terrain grain tiles across one mound. At 1 the jpg was
// stretched over the whole footprint and arrived as a smear.
const TERRAIN_TILE = 3.4;

/* A mound: flat enough on top to read its terrain, with a skirt that meets the
   sheet tangentially so it sits on the board rather than punching through it.
   Local relief only — it stops at DISK_R and never spreads.

   Built as a radial grid rather than a lathe, because a lathe can only make a
   solid of revolution and a solid of revolution is a cone. Twelve identical
   smooth cones is what the board had. Here the profile is modulated around the
   axis as well as along it, so a hills mound has ridges and a desert mound has
   a windward and a lee side — and the modulation is seeded from the city id,
   so no two are the same shape and each is the same shape every load.

   The relief rides on the profile and tapers to zero at the rim, so the merge
   guard is untouched: the footprint is still exactly `radius`. */
function moundGeometry(kind, height, radius, seed) {
  const RINGS = 30, SECT = 84;
  const spec = MOUND_RELIEF[kind] || MOUND_RELIEF_FALLBACK;
  const rnd = mulberry32(seed);

  // One harmonic per lobe count, each with its own phase and weight.
  const harm = spec.lobes.map(function (k) {
    return { k: k, phase: rnd() * Math.PI * 2, w: 0.45 + rnd() * 0.55 };
  });
  const skewPhase = rnd() * Math.PI * 2;
  const wsum = harm.reduce(function (a, h) { return a + h.w; }, 0) || 1;

  // The base profile: a plateau, then a smoothstep skirt to the sheet.
  const flat = spec.plateau;
  function profile(t) {
    if (t <= flat) { return 1; }
    const u = (t - flat) / (1 - flat);
    return 1 - u * u * (3 - 2 * u);
  }
  // Relief vanishes on the axis (where every angle meets) and at the rim
  // (where the skirt has to close on the sheet).
  function envelope(t) {
    return Math.pow(Math.sin(Math.PI * Math.min(t / 0.94, 1)), 1.15);
  }

  const pos = [], uv = [], idx = [];
  function push(t, a) {
    const r = t * radius;
    const x = Math.cos(a) * r, z = Math.sin(a) * r;
    let rel = 0;
    for (let i = 0; i < harm.length; i++) {
      rel += harm[i].w * Math.sin(harm[i].k * a + harm[i].phase);
    }
    rel = (rel / wsum) * spec.amp + Math.cos(a - skewPhase) * spec.skew;
    const y = height * profile(t) * (1 + rel * envelope(t));
    pos.push(x, Math.max(y, 0), z);
    // Planar (top-down) UVs, so the terrain jpg lies on the mound like printed
    // relief instead of smearing down the skirt.
    uv.push((x / (2 * radius) + 0.5) * TERRAIN_TILE,
            (z / (2 * radius) + 0.5) * TERRAIN_TILE);
  }

  push(0, 0);                                   // apex, one shared vertex
  for (let i = 1; i <= RINGS; i++) {
    const t = i / RINGS;
    for (let j = 0; j < SECT; j++) { push(t, (j / SECT) * Math.PI * 2); }
  }

  for (let j = 0; j < SECT; j++) {              // the fan around the apex
    idx.push(0, 1 + ((j + 1) % SECT), 1 + j);
  }
  for (let i = 1; i < RINGS; i++) {
    const a0 = 1 + (i - 1) * SECT, b0 = 1 + i * SECT;
    for (let j = 0; j < SECT; j++) {
      const jn = (j + 1) % SECT;
      idx.push(a0 + j, a0 + jn, b0 + j);
      idx.push(a0 + jn, b0 + jn, b0 + j);
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  geo.setIndex(idx);
  geo.computeVertexNormals();
  return geo;
}

/* A tiny studio, rendered once into a cube map so every PBR material on the
   board has something to reflect. Standard materials with no environment fall
   back to a flat diffuse term, which is most of why the first pass looked like
   painted card: the paper had no sheen, the tokens had no highlight, and the
   relief had no cool bounce in its shaded faces. Built from three coloured
   planes rather than an HDR file, so the page still ships four jpgs. */
function studioEnvironment(renderer) {
  const room = new THREE.Scene();
  const box = new THREE.BoxGeometry(1, 1, 1);
  function panel(color, intensity, sx, sy, sz, px, py, pz) {
    const m = new THREE.Mesh(box, new THREE.MeshBasicMaterial({
      color: new THREE.Color(color).multiplyScalar(intensity),
      side: THREE.BackSide
    }));
    m.scale.set(sx, sy, sz);
    m.position.set(px, py, pz);
    room.add(m);
  }
  // The room itself: warm floor bounce under a cool sky.
  panel(0x8fa6c8, 1.0, 12, 12, 12, 0, 0, 0);
  const lamp = new THREE.BoxGeometry(1, 1, 1);
  function light(color, intensity, sx, sy, sz, px, py, pz) {
    const m = new THREE.Mesh(lamp, new THREE.MeshBasicMaterial({
      color: new THREE.Color(color).multiplyScalar(intensity)
    }));
    m.scale.set(sx, sy, sz);
    m.position.set(px, py, pz);
    room.add(m);
  }
  light(0xfff4e2, 5.0, 5, 0.4, 5, -1.6, 5.2, 1.4);   // the key, overhead
  light(0xbcd4ff, 1.6, 0.4, 4, 5, 5.4, 1.2, -1.0);   // cool wall
  light(0xffd9a8, 1.1, 4, 3, 0.4, -1.0, 0.6, -5.4);  // warm bounce

  const pmrem = new THREE.PMREMGenerator(renderer);
  const target = pmrem.fromScene(room, 0.04);
  pmrem.dispose();
  room.traverse(function (o) { if (o.material) { o.material.dispose(); } });
  box.dispose();
  lamp.dispose();
  return target.texture;
}

/* -------------------------------------------------------------------- board */

/* `terrain` is a list on the map and always has been -- a city may sit on more
   than one. The board used to receive it flattened to its first entry, so
   indexing MOUND_H with it worked. It now arrives whole, and `MOUND_H[["plain"]]`
   still resolves because JS stringifies a one-element array to its element --
   but `["plain","hills"]` would become the key "plain,hills" and silently miss.
   The first label is the one the mound is built from; the rest are the city's
   to report, not the relief's. */
function primaryTerrain(city) {
  return Array.isArray(city.terrain) ? city.terrain[0] : city.terrain;
}

/* "182 · G11 · port · hills" — the same row, in the same order, that
   webapp/mapview.py prints under a city on a sparse map. A ruin's population
   is 0 and it says so rather than hiding the number: an abandoned city is a
   real thing on this board and the zero is the point. */
/* Emitted as parts rather than one string, so a narrow board can drop the
   tail of the row in CSS. mapview does the same thing by count -- past
   _DENSE_CITY_COUNT it stops drawing per-city meta at all, because a reading
   nobody can read is just ink. Here the board is small rather than crowded,
   and the first two readings (who lives there, where it is on the grid) are
   the ones worth keeping. The separator is drawn by CSS between surviving
   parts, so hiding one cannot leave a stranded middot behind. */
function cityMetaParts(city) {
  const parts = [];
  if (typeof city.population === "number") {
    parts.push(["pop", String(city.population)]);
  }
  if (city.grid_ref) { parts.push(["grid", city.grid_ref]); }
  if (city.is_ruin) { parts.push(["flag", "ruin"]); }
  if (city.is_port) { parts.push(["flag", "port"]); }
  if (city.is_magic_free) { parts.push(["flag", "magic-free"]); }
  const terrain = Array.isArray(city.terrain) ? city.terrain : [city.terrain];
  terrain.forEach(function (t) { if (t) { parts.push(["terrain", t]); } });
  return parts;
}

/* --- elevation ------------------------------------------------------------

   READ THIS BEFORE TRUSTING A CONTOUR. `calib_12.json` has twelve terrain
   LABELS and no elevation whatsoever -- no mesh, no heightfield, not a single
   spot height. What follows interpolates a surface from those twelve labels
   and adds fractal detail to it, which means every slope between two cities is
   a plausible invention and not a survey. It is the same bargain the coastline
   already struck, one step further in: draw the thing the game implies, and
   say plainly that it is implied. Amendment 3 in docs/MARKETING_CLOSED_ALPHA.md
   records it and the legend says it on the page.

   What IS data: which of the twelve cities stands on hills, on plain, on
   desert. A reader who sees high ground under Drelerford and Dunaen is reading
   the map correctly. A reader who counts the ridges between them is not. */
const TERRAIN_ELEV = {
  plain:     { base: 13,  rough: 8 },
  plains:    { base: 13,  rough: 8 },
  desert:    { base: 8,   rough: 5 },
  hills:     { base: 56,  rough: 30 },
  forest:    { base: 27,  rough: 14 },
  woods:     { base: 27,  rough: 14 },
  mountains: { base: 112, rough: 54 },
  swamp:     { base: 5,   rough: 3 },
  coastal:   { base: 8,   rough: 4 },
  river:     { base: 10,  rough: 5 }
};
const TERRAIN_FALLBACK = { base: 13, rough: 8 };

/* Hypsometric tints, the relief convention: lowland green through upland
   ochre to bare rock. Interpolated by height, so the colour is a reading of
   the surface rather than a second opinion about it. */
const HYPSO = [
  [0.00, [0.37, 0.47, 0.26]],   // shore green
  [0.20, [0.45, 0.52, 0.28]],
  [0.42, [0.56, 0.55, 0.30]],
  [0.64, [0.58, 0.47, 0.29]],   // upland ochre
  [0.84, [0.50, 0.40, 0.30]],
  [1.00, [0.45, 0.41, 0.37]]    // bare rock, and it is ROCK
];

/* Elevation is read against a fixed scale, not against this map's own tallest
   point. Normalising by the observed peak means whatever happens to be
   highest is always painted as a summit -- so a vale whose boldest feature is
   hill country came out capped in pale grey, and the hills read as cloud
   sitting on the board rather than as ground. Against a fixed ceiling, a map
   of plains stays green, hills reach ochre, and only a map that really has
   mountains on it ever gets bare rock. */
const HYPSO_CEILING = 190;

function hypso(t) {
  const u = Math.min(1, Math.max(0, t));
  for (let i = 1; i < HYPSO.length; i++) {
    if (u <= HYPSO[i][0]) {
      const a = HYPSO[i - 1], b = HYPSO[i];
      const k = (u - a[0]) / (b[0] - a[0] || 1);
      return [a[1][0] + (b[1][0] - a[1][0]) * k,
              a[1][1] + (b[1][1] - a[1][1]) * k,
              a[1][2] + (b[1][2] - a[1][2]) * k];
    }
  }
  return HYPSO[HYPSO.length - 1][1];
}

/* Value noise on a hashed lattice. Deterministic from position alone, so the
   same board renders the same hills on every machine and every reload -- the
   terrain is fake, but it is not different-every-time fake. */
function lattice(ix, iz, salt) {
  return (hashKey(ix + ":" + iz + ":" + salt) % 65536) / 65536;
}

function smoothstep(t) { return t * t * (3 - 2 * t); }

function valueNoise(x, z, salt) {
  const x0 = Math.floor(x), z0 = Math.floor(z);
  const fx = smoothstep(x - x0), fz = smoothstep(z - z0);
  const a = lattice(x0, z0, salt), b = lattice(x0 + 1, z0, salt);
  const c = lattice(x0, z0 + 1, salt), d = lattice(x0 + 1, z0 + 1, salt);
  return (a + (b - a) * fx) * (1 - fz) + (c + (d - c) * fx) * fz;
}

function fbm(x, z, salt) {
  let amp = 1, freq = 1, sum = 0, norm = 0;
  for (let o = 0; o < 4; o++) {
    sum += amp * valueNoise(x * freq, z * freq, salt + o);
    norm += amp;
    amp *= 0.5;
    freq *= 2.07;
  }
  return sum / norm;
}

export function createBoard(options) {
  const canvas = options.canvas;
  const labelHost = options.labelHost;
  const cities = options.cities;
  const roads = options.roads;
  const seatColors = options.seatColors;
  const activeCities = options.activeCities || {};
  const reducedMotion = !!options.reducedMotion;

  const cityById = {};
  cities.forEach(function (c) { cityById[c.id] = c; });

  /* --- frame.

     The scale is mapview's, not a square. A 0..1 fraction means a different
     number of miles on each axis (the field is 1300x1000) AND the app draws
     that field into a 1180x680 frame, so the arrangement a coach knows is
     wider than it is tall by more than either ratio alone. Multiplying both
     fractions by one constant -- which is what this did -- rendered the world
     23% too narrow for its height and made the board and the app read as two
     different places. `frame_units` carries the app's extents across and the
     cities land on the app's own arrangement.

     Normalised on the geometric mean so the frame's AREA stays what it was.
     Every tuned constant below -- mound footprints, the merge guard, road
     widths, token sizes, camera margins -- was fitted against a board about
     1000 units across, and rescaling the shape should not silently rescale
     all of them too. */
  const frameUnits = options.frameUnits || [SU, SU];
  const NORM = SU / Math.sqrt(frameUnits[0] * frameUnits[1]);
  const FX = frameUnits[0] * NORM;
  const FY = frameUnits[1] * NORM;

  /* The extent now includes the coast, not just the cities. The land is the
     subject of the picture; framing to the cities alone would run the
     shoreline off every edge, and the camera fits these same bounds. */
  const hullMasses = (options.landmasses || []).filter(function (mass) {
    return mass.hull && mass.hull.length >= 3;
  });
  const extentX = cities.map(function (c) { return c.x * FX; });
  const extentY = cities.map(function (c) { return c.y * FY; });
  hullMasses.forEach(function (mass) {
    mass.hull.forEach(function (point) {
      extentX.push(point[0] * FX);
      extentY.push(point[1] * FY);
    });
  });

  const minX = Math.min.apply(null, extentX), maxX = Math.max.apply(null, extentX);
  const minY = Math.min.apply(null, extentY), maxY = Math.max.apply(null, extentY);
  const midX = (minX + maxX) / 2, midY = (minY + maxY) / 2;
  const sheetW = (maxX - minX) + 2 * PAD;
  const sheetD = (maxY - minY) + 2 * PAD;
  const span = Math.max(sheetW, sheetD);

  // Map coordinates are y-down; the scene is z-in.
  function worldX(fx) { return fx * FX - midX; }
  function worldZ(fy) { return fy * FY - midY; }

  /* --- the ground.

     Elevation is interpolated from the city terrain labels by inverse distance
     -- a city on hills raises the ground around it, a city on desert keeps it
     flat -- and fractal noise supplies the detail no label can. It is then
     multiplied by a falloff that reaches zero at the shoreline, so the surface
     meets the coast at sea level and the island's edge stays the hull's edge
     rather than a cliff wherever the noise happened to be high.

     See the elevation block above the module for what this is and is not. */
  const COAST_FALL = 130;      // board units from shore to full inland height
  const NOISE_S = 1 / 125;     // broad landform scale
  const IDW_SOFT = 2600;       // softening, so a city is not a spike

  const influence = cities.map(function (c) {
    const spec = TERRAIN_ELEV[primaryTerrain(c)] || TERRAIN_FALLBACK;
    return { x: worldX(c.x), z: worldZ(c.y), base: spec.base, rough: spec.rough };
  });

  // Hull in world units, for the inside test and the shore distance.
  const shore = [];
  hullMasses.forEach(function (mass) {
    shore.push(mass.hull.map(function (pt) {
      return [worldX(pt[0]), worldZ(pt[1])];
    }));
  });

  function insideRing(ring, px, pz) {
    let hit = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const a = ring[i], b = ring[j];
      if ((a[1] > pz) !== (b[1] > pz) &&
          px < (b[0] - a[0]) * (pz - a[1]) / (b[1] - a[1]) + a[0]) {
        hit = !hit;
      }
    }
    return hit;
  }

  function edgeDistance(ring, px, pz) {
    let best = Infinity;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const ax = ring[j][0], az = ring[j][1];
      const bx = ring[i][0], bz = ring[i][1];
      const dx = bx - ax, dz = bz - az;
      const len2 = dx * dx + dz * dz || 1;
      let t = ((px - ax) * dx + (pz - az) * dz) / len2;
      t = Math.max(0, Math.min(1, t));
      const cx = ax + dx * t, cz = az + dz * t;
      best = Math.min(best, Math.hypot(px - cx, pz - cz));
    }
    return best;
  }

  /* Every settlement levels the ground it stands on. This is not decoration:
     a city's rim, ownership ring and harbour ring are flat discs, and a flat
     disc on a slope is half-buried -- twelve cities came out as twelve half
     moons. Real towns sit on levelled sites for the same reason, so the
     terrain is flattened toward the site height inside the marker's radius
     and eased back out over twice that. Roads leaving a city start level
     with it too, which is what stops them diving into the first slope. */
  const SITE_R = 46;
  let siteHeights = null;

  function rawHeight(px, pz) {
    let fall = 0;
    for (let i = 0; i < shore.length; i++) {
      if (insideRing(shore[i], px, pz)) {
        fall = Math.max(fall, smoothstep(
          Math.min(1, edgeDistance(shore[i], px, pz) / COAST_FALL)));
      }
    }
    if (fall <= 0) { return 0; }

    let wsum = 0, base = 0, rough = 0;
    for (let i = 0; i < influence.length; i++) {
      const t = influence[i];
      const d2 = (px - t.x) * (px - t.x) + (pz - t.z) * (pz - t.z);
      const w = 1 / (d2 + IDW_SOFT);
      wsum += w;
      base += w * t.base;
      rough += w * t.rough;
    }
    if (!wsum) { return 0; }
    base /= wsum;
    rough /= wsum;

    /* Ridged, not billowy. Plain fbm gives rolling blobs -- which is what
       lowland looks like, and is why the first pass read as a soft yellow
       cushion wherever it was meant to read as hill country. Folding the
       noise about its midpoint (1 - |2n-1|) turns the smooth maxima into
       creases, so high ground gets ridges and valleys instead of domes. It
       is applied in proportion to `rough`, so the plains stay rolling and
       only the hills crease. */
    const broad = fbm(px * NOISE_S, pz * NOISE_S, 11);
    const fine = fbm(px * NOISE_S * 3.1, pz * NOISE_S * 3.1, 71);
    const ridged = 1 - Math.abs(2 * fbm(px * NOISE_S * 1.7,
                                        pz * NOISE_S * 1.7, 33) - 1);
    const h = base * (0.5 + 0.75 * broad + 0.55 * ridged * ridged)
            + rough * (fine - 0.45) * 1.9;
    /* Vertical exaggeration, the relief-map convention. True to scale, 60
       units of hill across a 1300-unit vale is a 4.6% grade -- geologically
       honest and visually nothing, which is exactly how the first pass of
       this came out. Relief maps have exaggerated their vertical since the
       first one was moulded. The ORDERING is the data; the amplitude is
       presentation, the same bargain the mounds made before them. */
    return Math.max(0, h) * fall * 2.6;
  }

  function groundHeight(px, pz) {
    const raw = rawHeight(px, pz);
    if (!siteHeights) { return raw; }
    let out = raw;
    for (let i = 0; i < siteHeights.length; i++) {
      const site = siteHeights[i];
      const d = Math.hypot(px - site.x, pz - site.z);
      if (d >= SITE_R * 2) { continue; }
      // Flat inside the marker, easing back to the landscape outside it.
      const k = d <= SITE_R ? 1 : 1 - smoothstep((d - SITE_R) / SITE_R);
      out = out + (site.h - out) * k;
    }
    return out;
  }

  siteHeights = cities.map(function (c) {
    const cx = worldX(c.x), cz = worldZ(c.y);
    return { x: cx, z: cz, h: rawHeight(cx, cz) };
  });

  /* The merge guard. "Local relief only. No interpolated continent between
     cities" is a property of the footprint, not of good intentions: two mounds
     whose skirts touch read as one landform, and on this map Dreliwick and
     Narunon are 68.5 units apart against a 68-unit pair of footprints. That is
     half a unit of daylight. So the radius is derived from the closest pair
     rather than asserted, and a future map that moves a city cannot quietly
     turn the board into terrain. */
  /* Per city, not one flat radius for all twelve. Only Dreliwick and Narunon
     are genuinely tight (68.5 apart); everyone else has 100 to 227 units of
     room, and a single global radius throttled all twelve to that worst case —
     6.4% of the board in terrain where 20.5% is available.

     The guarantee survives the change: each radius is at most 0.46x that
     city's OWN nearest-neighbour distance, and a city's nearest-neighbour
     distance is by definition no greater than its distance to any particular
     other city. So for any pair, both radii are <= 0.46d and their skirts sum
     to <= 0.92d. They cannot touch. */
  const radiusById = {};
  cities.forEach(function (c) {
    let nearest = Infinity;
    cities.forEach(function (o) {
      if (o === c) { return; }
      nearest = Math.min(nearest,
        Math.hypot((c.x - o.x) * FX, (c.y - o.y) * FY));
    });
    radiusById[c.id] = Math.min(DISK_R_MAX, nearest * 0.46);
  });
  function cityRadius(city) { return radiusById[city.id] || 30; }
  const maxRadius = Math.max.apply(null, cities.map(cityRadius));

  /* --- renderer */
  const renderer = new THREE.WebGLRenderer({
    canvas: canvas, antialias: true, alpha: true
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  // ACES desaturates as it rolls off, which is exactly wrong here: it took
  // three already-muted earth tints and converged them on brown. Neutral
  // (Khronos PBR Neutral) keeps hue and saturation into the highlights.
  renderer.toneMapping = THREE.NeutralToneMapping;
  // Down from 1.30: the sheet is cream now rather than mud, and the exposure
  // that was rescuing a dark board clips a light one.
  renderer.toneMappingExposure = 1.18;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  // Applies to every MeshStandardMaterial in the scene automatically.
  scene.environment = studioEnvironment(renderer);
  scene.environmentIntensity = 0.42;

  /* The hero angle: turned a little off square so the board reads as an object
     on a table rather than a floor plan, but not so far that the rectangle
     stops being a rectangle. Distance is fitted to the sheet below. */
  const HERO_AZIMUTH = 0.26;      // radians off straight-on
  const HERO_POLAR = 0.74;        // from straight down; ~48 degrees of tilt

  const camera = new THREE.PerspectiveCamera(36, 1, 1, 12000);
  function placeCamera(azimuth, dist) {
    camera.position.set(
      controls.target.x + Math.sin(azimuth) * Math.sin(HERO_POLAR) * dist,
      controls.target.y + Math.cos(HERO_POLAR) * dist,
      controls.target.z + Math.cos(azimuth) * Math.sin(HERO_POLAR) * dist);
  }
  // Seeded directly: controls (and therefore the aim point) do not exist yet.
  camera.position.set(
    Math.sin(HERO_AZIMUTH) * Math.sin(HERO_POLAR) * span * 1.4,
    Math.cos(HERO_POLAR) * span * 1.4,
    Math.cos(HERO_AZIMUTH) * Math.sin(HERO_POLAR) * span * 1.4);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0, 0);
  controls.enableDamping = true;
  controls.dampingFactor = 0.075;
  controls.enablePan = false;
  controls.minDistance = span * 0.62;
  controls.maxDistance = span * 2.1;
  controls.minPolarAngle = 0.18;
  controls.maxPolarAngle = 1.32;          // never drop under the board
  controls.rotateSpeed = 0.55;
  controls.zoomSpeed = 0.7;
  // On touch, one finger still scrolls the page — this is a poster, not a
  // viewer. Two fingers turn the board.
  controls.touches.ONE = THREE.TOUCH.NONE;
  controls.touches.TWO = THREE.TOUCH.DOLLY_ROTATE;
  controls.update();

  // OrbitControls blanks touch-action; put vertical scrolling back, or the
  // board becomes a scroll trap on a phone.
  renderer.domElement.style.touchAction = "pan-y";

  let userDriving = false;
  controls.addEventListener("start", function () { userDriving = true; });

  /* --- light: one warm key that casts the relief, a cool fill, and sky bounce */
  // Less flat ambient than before: ambient fills the shadows back in and takes
  // the relief out with them.
  // Cool sky against a warm key: shadows go blue rather than grey, which is
  // what makes a saturated hue look saturated instead of merely bright.
  // Pulled back now that scene.environment carries the ambient term; at 0.85
  // on top of an environment the shaded faces filled in and the relief went
  // flat again.
  scene.add(new THREE.HemisphereLight(0x86b6ff, 0x40301c, 0.30));

  /* A spot, not a directional. The board is 94% flat plane, and a directional
     light shades a flat plane to a single value everywhere — which is exactly
     why the first pass put four fifths of the frame inside one 32-value band
     however the tints were graded. A spot with penumbra lays a pool of light
     across the sheet instead, so the board has a bright centre falling to warm
     shadow at the corners, and the relief has a gradient to sit against. */
  // decay 0 deliberately: the board sits ~900 units from the light, and any
  // physical falloff over that distance dims the whole scene by an order of
  // magnitude before the cone shape is even visible. The pool comes from the
  // angle and penumbra, not from distance.
  // Near-white, not amber. A warm key over greyscale textures tints every
  // terrain the same colour and is half the reason the board read as brown.
  // Tighter than the sheet, on purpose: the cone has to fall off inside the
  // frame or there is no pool, only an evenly lit rectangle.
  const key = new THREE.SpotLight(0xfffaf0, 4.6, 0, 0.60, 0.92, 0);
  key.position.set(-span * 0.42, span * 1.02, span * 0.36);
  key.target.position.set(0, 0, 0);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.bias = -0.0006;
  key.shadow.normalBias = 1.4;   // world units; the scene is ~800 across
  key.shadow.camera.near = span * 0.35;
  key.shadow.camera.far = span * 2.6;
  key.shadow.camera.fov = 78;
  key.shadow.camera.updateProjectionMatrix();
  scene.add(key);
  scene.add(key.target);

  // A soft directional bounce so the shadowed corners keep their terrain
  // colour instead of going to flat ambient.
  const bounce = new THREE.DirectionalLight(0xffd9a8, 0.55);
  bounce.position.set(span * 0.4, span * 0.5, -span * 0.3);
  scene.add(bounce);

  const fill = new THREE.DirectionalLight(0x6f9ad6, 0.55);
  fill.position.set(span * 0.6, span * 0.35, -span * 0.5);
  scene.add(fill);

  /* A low rim from behind the board. Nothing separates one earth-toned mound
     from the earth-toned sheet behind it at this tilt except a bright edge, and
     a key light from the front-left cannot put one there. Kept cool and weak:
     it is a silhouette cue, not a second key. */
  const rim = new THREE.DirectionalLight(0xdce9ff, 0.85);
  rim.position.set(span * 0.15, span * 0.16, -span * 0.95);
  scene.add(rim);

  /* --- textures */
  const ANISO = Math.min(16, renderer.capabilities.getMaxAnisotropy());
  const loader = new THREE.TextureLoader();
  const terrainTex = {};
  function terrainMap(name) {
    if (!terrainTex[name]) {
      const tex = loader.load("textures/" + name + ".jpg");
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
      tex.anisotropy = ANISO;
      terrainTex[name] = tex;
    }
    return terrainTex[name];
  }

  // The map surface, ruled at the game's 48-unit grid, drawn whole.
  const sheetTex = sheetTexture(sheetW, sheetD);
  sheetTex.colorSpace = THREE.SRGBColorSpace;
  sheetTex.anisotropy = ANISO;

  /* paper.jpg was shipped and never used. It is the right map for the one job
     no colour can do: as a roughness map it gives the sheet a tooth that
     breaks up the key light's reflection, so the plate stops being a perfectly
     smooth surface pretending to be paper.
     Roughness only, and at a coarse repeat. Fed to bump instead it would be
     differentiated before use, and a grain map differentiated on a surface
     seen at 48 degrees is guaranteed shimmer along the far half. */
  const paperTex = loader.load("textures/paper.jpg");
  paperTex.wrapS = paperTex.wrapT = THREE.RepeatWrapping;
  paperTex.repeat.set(sheetW / 330, sheetD / 330);
  paperTex.anisotropy = ANISO;

  const texRingSolid = ringTexture(false);
  const texRingDashed = ringTexture(true);
  const texGlow = glowTexture();
  const texContact = contactTexture();
  const texRoad = roadAlpha(false);
  const texRoadDashed = roadAlpha(true);
  texRoad.wrapS = texRoadDashed.wrapS = THREE.RepeatWrapping;

  /* --- the sheet the board is printed on. Not terrain and not a landmass:
         it covers the frame edge to edge and stops at the frame. */
  /* Two layers, not one slab: a dark binder board with the printed plate laid
     on top of it and a few units of reveal all round. A single tan box had no
     way to say what it was, and the eye had no thickness cue at the edge; a
     mounted print is legible as an object from the first frame. */
  const PLATE_T = 6;                       // the paper's own thickness
  const REVEAL = 9;                        // binder board showing past the print
  // envMapIntensity low: the studio's cool wall is the brightest thing the
  // near edge can see, and at full strength it lit a dark brown board blue.
  const edgeMat = new THREE.MeshStandardMaterial({
    color: SHEET_EDGE, roughness: 0.78, metalness: 0.04, envMapIntensity: 0.22
  });
  /* The plate sits ON the board, not inside it. Centring both on y = 0 put the
     board's top face and the plate's printed face in the same plane, and two
     coplanar faces are a depth-buffer coin toss decided per pixel — which is
     what covered the far half of the sheet in horizontal dashes. It reads as
     texture aliasing and is not: no filtering setting can fix geometry that
     occupies one place twice. */
  const board = new THREE.Mesh(
    new THREE.BoxGeometry(sheetW, SHEET_T, sheetD), edgeMat);
  board.position.y = -LAND_H - PLATE_T - SHEET_T / 2;
  board.receiveShadow = true;
  board.castShadow = true;              // onto the table, below
  scene.add(board);

  const plateSideMat = new THREE.MeshStandardMaterial({
    color: 0xcdbf9e, roughness: 0.95, metalness: 0
  });
  /* No bump map here, deliberately. Bump is a derivative of the texture, so a
     grain map that is merely noisy at 1:1 becomes violently noisy under
     minification — and the board is seen at 48 degrees, i.e. minified hard
     across its whole far half. Adding paper tooth as bump striped the plate
     end to end. Roughness carries the tooth instead: it varies the specular
     response without ever touching the normal. */
  const plateTopMat = new THREE.MeshStandardMaterial({
    map: sheetTex,
    roughnessMap: paperTex,
    roughness: 0.98,              // scaled by the map; the paper decides
    metalness: 0,
    envMapIntensity: 0.45         // paper takes a sheen, not a reflection
  });
  const plate = new THREE.Mesh(
    new THREE.BoxGeometry(sheetW - REVEAL * 2, PLATE_T, sheetD - REVEAL * 2),
    [plateSideMat, plateSideMat, plateTopMat,
     plateSideMat, plateSideMat, plateSideMat]
  );
  /* Dropped by LAND_H with the water. y = 0 is the land surface now, and a
     plate still at 0 would be a sheet of paper lying across the sea at
     exactly the height of the cliff tops. */
  plate.position.y = -LAND_H - PLATE_T / 2;
  plate.receiveShadow = true;
  scene.add(plate);

  /* --- sea, land and coast, printed on the plate under the ruling.

     Layering here is by renderOrder and a fraction of a unit of height, the
     same scheme the roads use: the plate's printed face is y = 0, the
     graticule rules at 0.3, road casing at 0.7, road ink at 0.9. Sea and land
     go below all of it so the grid crosses them, which is what a printed map
     does. depthWrite stays off so nothing in this stack z-fights with the
     coplanar layer above it.

     The hull arrives in the same 0..1 fractions the cities use, already
     mapped out of mapview's SVG frame by scripts/build_public_board.py. It is
     a road-connectivity confine and not a survey; see the file header. */
  const landHull = (options.landmasses || []).filter(function (mass) {
    return mass.hull && mass.hull.length >= 3;
  });
  let terrainPeak = 0;   // tallest ground, so the camera can frame the tops

  const ruledHalfW = (sheetW - REVEAL * 2) / 2 - SHEET_INSET;
  const ruledHalfD = (sheetD - REVEAL * 2) / 2 - SHEET_INSET;

  if (landHull.length) {
    const seaTex = loader.load("textures/sea.jpg");
    seaTex.colorSpace = THREE.SRGBColorSpace;
    seaTex.wrapS = seaTex.wrapT = THREE.RepeatWrapping;
    seaTex.repeat.set(ruledHalfW * 2 / 300, ruledHalfD * 2 / 300);
    seaTex.anisotropy = ANISO;

    /* Sea first, over the whole ruled field. Land is then printed on top of
       it, so the water needs no hole cut in it -- one fewer polygon operation
       to get wrong, and the coast stays exactly the hull's own edge. */
    const sea = new THREE.Mesh(
      new THREE.PlaneGeometry(ruledHalfW * 2, ruledHalfD * 2),
      /* Opaque, and it writes depth. An earlier pass had the sea transparent
         and the land not, which put them in different render queues: three.js
         draws every opaque object before any transparent one, so renderOrder
         never got a vote and the water painted over the land on every frame.
         Two opaque layers a tenth of a unit apart let the depth buffer settle
         it, which it does correctly and for free. */
      new THREE.MeshStandardMaterial({
        color: SEA_TINT, map: seaTex, roughness: 0.86, metalness: 0,
        envMapIntensity: 0.30
      })
    );
    sea.rotation.x = -Math.PI / 2;
    sea.position.y = -LAND_H + 1.2;
    sea.renderOrder = -3;
    sea.receiveShadow = true;
    scene.add(sea);

    landHull.forEach(function (mass) {
      /* Negated, and it has to be. A Shape is built in XY and this mesh is
         laid flat with rotation.x = -PI/2, which carries local (x, y) to world
         (x, 0, -y). Feeding it z directly mirrored the coastline about the
         board's centre line -- the fill and the LineLoop below, which is built
         in world coordinates and was therefore correct, traced two different
         polygons, and Drelerford came out standing in the sea. */
      const shape = new THREE.Shape();
      mass.hull.forEach(function (point, i) {
        const x = worldX(point[0]), z = -worldZ(point[1]);
        if (i === 0) { shape.moveTo(x, z); } else { shape.lineTo(x, z); }
      });
      shape.closePath();

      /* Extruded, not a printed fill. A flat polygon tinted green is a map OF
         land; a solid with a wall down to the seabed is land. The extrusion
         runs along local +z, which this mesh's -90deg rotation about X carries
         to world +y, so the body comes out spanning 0..LAND_H and is dropped
         by LAND_H to put its top face at 0 -- where every mound, road and
         token in the scene already stands. */
      const landTex = terrainMap("plain");
      const geo = new THREE.ExtrudeGeometry(shape, {
        depth: LAND_H, bevelEnabled: false, curveSegments: 1
      });
      /* Extrude UVs come out in model units, so the grain would stretch across
         a 700-unit body without this. Same tile size as the mounds' ground.
         The wall gets it too: at this scale a smeared cliff face is more
         obvious than a tiled one. */
      const uv = geo.attributes.uv;
      for (let i = 0; i < uv.count; i++) {
        uv.setXY(i, uv.getX(i) / 300, uv.getY(i) / 300);
      }
      uv.needsUpdate = true;

      /* Two materials: ExtrudeGeometry emits group 0 for the caps and group 1
         for the wall. The cliff is the cut edge of the same ground, so it is
         the same tint stepped down -- a shore reads as a shore because it is
         darker under its own overhang, not because it is a different colour. */
      const land = new THREE.Mesh(geo, [
        new THREE.MeshStandardMaterial({
          color: LAND_TINT, map: landTex, roughness: 0.95, metalness: 0,
          envMapIntensity: 0.28
        }),
        new THREE.MeshStandardMaterial({
          color: LAND_CLIFF, map: landTex, roughness: 0.98, metalness: 0,
          envMapIntensity: 0.18
        })
      ]);
      land.rotation.x = -Math.PI / 2;
      land.position.y = -LAND_H;
      land.castShadow = true;
      land.receiveShadow = true;
      scene.add(land);

      /* --- the ground surface itself.

         The extruded body above is the island's base and its cliff; this is
         the land ON it. A grid is laid over the mass's bounding box, every
         vertex lifted to groundHeight, and any cell whose centre falls outside
         the shore is dropped. Because the height falls to zero at the
         coastline, the dropped cells leave a ragged edge sitting at exactly
         the height of the base's flat cap underneath it -- so the raggedness
         is buried and the visible coast stays the hull's own outline.

         Coloured by height rather than by texture. Twelve terrain labels
         cannot paint a continent, but an elevation can read itself: low ground
         green, upland ochre, the tops bare. */
      const bounds = mass.hull.reduce(function (acc, pt) {
        const wx = worldX(pt[0]), wz = worldZ(pt[1]);
        return [Math.min(acc[0], wx), Math.min(acc[1], wz),
                Math.max(acc[2], wx), Math.max(acc[3], wz)];
      }, [Infinity, Infinity, -Infinity, -Infinity]);

      const STEP = 7;
      const cols = Math.ceil((bounds[2] - bounds[0]) / STEP) + 1;
      const rows = Math.ceil((bounds[3] - bounds[1]) / STEP) + 1;
      const shoreRing = shore[hullMasses.indexOf(mass)];

      const gPos = [], gCol = [], gUv = [], gIdx = [];
      let peak = 0;
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const px = bounds[0] + c * STEP;
          const pz = bounds[1] + r * STEP;
          const h = groundHeight(px, pz);
          if (h > peak) { peak = h; }
          gPos.push(px, h + 0.15, pz);
          gUv.push(px / 300, pz / 300);
          gCol.push(0, 0, 0);          // filled once the peak is known
        }
      }
      /* Cells are clipped to the shore, not merely dropped. Dropping whole
         cells left the coastline as a flight of 7-unit stairs -- the grid's
         edge, showing against the flat cap beneath it, in a place where the
         board has already promised the reader an exact hull. Sutherland-
         Hodgman against the shore ring gives each boundary cell its true
         shape, and those fragments are fanned into triangles and appended as
         loose vertices. The interior is still the cheap regular grid. */
      function clipToShore(poly, ring) {
        let out = poly;
        for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
          if (!out.length) { return out; }
          const ax = ring[j][0], az = ring[j][1];
          const bx = ring[i][0], bz = ring[i][1];
          // Positive side of the directed edge; the ring is convex here.
          const side = function (px, pz) {
            return (bx - ax) * (pz - az) - (bz - az) * (px - ax);
          };
          const input = out;
          out = [];
          for (let k = 0; k < input.length; k++) {
            const cur = input[k], prv = input[(k + input.length - 1) % input.length];
            const dc = side(cur[0], cur[1]), dp = side(prv[0], prv[1]);
            if (dc >= 0) {
              if (dp < 0) {
                const t = dp / (dp - dc);
                out.push([prv[0] + (cur[0] - prv[0]) * t,
                          prv[1] + (cur[1] - prv[1]) * t]);
              }
              out.push(cur);
            } else if (dp >= 0) {
              const t = dp / (dp - dc);
              out.push([prv[0] + (cur[0] - prv[0]) * t,
                        prv[1] + (cur[1] - prv[1]) * t]);
            }
          }
        }
        return out;
      }

      // The ring must wind consistently for the half-plane test above.
      let area2 = 0;
      for (let i = 0, j = shoreRing.length - 1; i < shoreRing.length; j = i++) {
        area2 += shoreRing[j][0] * shoreRing[i][1] - shoreRing[i][0] * shoreRing[j][1];
      }
      const windRing = area2 < 0 ? shoreRing.slice().reverse() : shoreRing;

      for (let r = 0; r < rows - 1; r++) {
        for (let c = 0; c < cols - 1; c++) {
          const x0 = bounds[0] + c * STEP, x1 = x0 + STEP;
          const z0 = bounds[1] + r * STEP, z1 = z0 + STEP;
          const corners = [[x0, z0], [x1, z0], [x1, z1], [x0, z1]];
          const allIn = corners.every(function (pt) {
            return insideRing(windRing, pt[0], pt[1]);
          });

          if (allIn) {
            const a = r * cols + c, b = a + 1;
            const d = (r + 1) * cols + c, e = d + 1;
            gIdx.push(a, d, b, b, d, e);
            continue;
          }

          const frag = clipToShore(corners, windRing);
          if (frag.length < 3) { continue; }
          const base = gPos.length / 3;
          frag.forEach(function (pt) {
            const h = groundHeight(pt[0], pt[1]);
            if (h > peak) { peak = h; }
            gPos.push(pt[0], h + 0.15, pt[1]);
            gUv.push(pt[0] / 300, pt[1] / 300);
            gCol.push(0, 0, 0);
          });
          for (let f = 1; f + 1 < frag.length; f++) {
            gIdx.push(base, base + f + 1, base + f);
          }
        }
      }

      /* Hypsometric tint needs the full range, so colour is a second pass --
         and it has to run after the clipped shore fragments have been added,
         or they arrive black. */
      for (let i = 0; i < gPos.length / 3; i++) {
        const tint = hypso((gPos[i * 3 + 1] - 0.15) / HYPSO_CEILING);
        gCol[i * 3] = tint[0];
        gCol[i * 3 + 1] = tint[1];
        gCol[i * 3 + 2] = tint[2];
      }

      if (gIdx.length) {
        const gGeo = new THREE.BufferGeometry();
        gGeo.setAttribute("position", new THREE.Float32BufferAttribute(gPos, 3));
        gGeo.setAttribute("color", new THREE.Float32BufferAttribute(gCol, 3));
        gGeo.setAttribute("uv", new THREE.Float32BufferAttribute(gUv, 2));
        gGeo.setIndex(gIdx);
        gGeo.computeVertexNormals();

        /* No colour map. The grain jpgs are near-white greyscale, so
           multiplying the hypsometric tint by one washed the whole landscape
           to cream and the relief lost the only cue it had left. The tint IS
           the surface colour; the jpg is demoted to roughness, where it gives
           the ground a tooth without touching its hue. */
        const ground = new THREE.Mesh(gGeo, new THREE.MeshStandardMaterial({
          vertexColors: true, roughnessMap: landTex, roughness: 0.98,
          metalness: 0, envMapIntensity: 0.20, flatShading: false
        }));
        ground.castShadow = true;
        ground.receiveShadow = true;
        scene.add(ground);
        terrainPeak = Math.max(terrainPeak, peak);
      }

      /* The coastline itself, inked. A fill against a fill has no edge of its
         own at this size -- the same reason the roads carry a casing. */
      const ring = [];
      mass.hull.forEach(function (point) {
        ring.push(new THREE.Vector3(worldX(point[0]), 0.30, worldZ(point[1])));
      });
      const coast = new THREE.LineLoop(
        new THREE.BufferGeometry().setFromPoints(ring),
        new THREE.LineBasicMaterial({
          color: COAST_INK, transparent: true, opacity: 0.75,
          depthWrite: false
        })
      );
      coast.renderOrder = -1;
      scene.add(coast);
    });
  }

  /* The ruling stops at the neatline, as it does on a printed plate -- and it
     now rules the WATER. When the land was a printed fill the grid crossed
     both, which is what a flat map does. The land is a solid standing 30 units
     proud of the sea, so a grid at sea level would disappear under it and a
     grid at land level would hang in the air over open water. Ruled water and
     clean relief is the older convention anyway: a chart grids its sea. */
  const ruled = graticuleGeometry(
    (sheetW - REVEAL * 2) / 2 - SHEET_INSET,
    (sheetD - REVEAL * 2) / 2 - SHEET_INSET,
    -LAND_H + 1.6);
  [[ruled.minor, GRID_MINOR], [ruled.major, GRID_MAJOR],
   [ruled.neat, NEATLINE]].forEach(function (pair) {
    const rgba = pair[1].match(/[\d.]+/g);
    const lines = new THREE.LineSegments(pair[0], new THREE.LineBasicMaterial({
      color: new THREE.Color(
        rgba[0] / 255, rgba[1] / 255, rgba[2] / 255).convertSRGBToLinear(),
      transparent: true,
      opacity: Number(rgba[3]),
      depthWrite: false
    }));
    lines.renderOrder = 0;
    scene.add(lines);
  });

  /* The table. The canvas is transparent and the frame's own CSS gradient is
     the surface the board lies on, so this plane draws nothing except the
     shadow the board throws onto it — which is the whole point. Without it the
     board floats in the backdrop with no contact anywhere. */
  const table = new THREE.Mesh(
    new THREE.PlaneGeometry(span * 2.4, span * 2.4),
    new THREE.ShadowMaterial({ opacity: 0.34 })
  );
  table.rotation.x = -Math.PI / 2;
  table.position.y = -LAND_H - SHEET_T - PLATE_T - 1;
  table.receiveShadow = true;
  scene.add(table);

  /* --- roads, lying on the sheet */
  const roadByPair = {};
  const pulses = [];

  function pairKey(a, b) { return a < b ? a + "|" + b : b + "|" + a; }

  roads.forEach(function (road) {
    const a = cityById[road.from], b = cityById[road.to];
    if (!a || !b) { return; }
    const style = ROAD_STYLE[road.quality] || ROAD_FALLBACK;
    const key = pairKey(road.from, road.to);

    const alpha = (style.dashed ? texRoadDashed : texRoad).clone();
    alpha.needsUpdate = true;
    alpha.wrapS = THREE.RepeatWrapping;

    const geo = roadRibbon(worldX(a.x), worldZ(a.y), worldX(b.x), worldZ(b.y),
                           style.width, key, groundHeight);
    alpha.repeat.set(Math.max(1, Math.round(geo.userData.length / 42)), 1);

    /* Unlit, deliberately. The game's roads are flat SVG strokes, and a lit
       MeshStandardMaterial on a dark navy board under a soft key rendered them
       almost to nothing — 78 road pixels across the whole board. Basic material
       holds the quality colour exactly as mapview specifies it, and the network
       reads as the drawn web it is in the game. */
    /* The casing: the same curve, wider and near-black, laid under the ink.
       An engraved map outlines its roads for exactly this reason — a coloured
       stroke on toned paper has no edge of its own, and at this size the four
       qualities were four pale ribbons the eye had to work to separate. */
    const casingAlpha = alpha.clone();
    casingAlpha.needsUpdate = true;
    const casing = new THREE.Mesh(
      roadRibbon(worldX(a.x), worldZ(a.y), worldX(b.x), worldZ(b.y),
                 style.width + 3.4, key, groundHeight),
      new THREE.MeshBasicMaterial({
        color: ROAD_CASING, transparent: true, opacity: 0.30,
        alphaMap: casingAlpha, depthWrite: false, side: THREE.DoubleSide
      })
    );
    casing.position.y = 0.7;
    casing.renderOrder = 1;
    scene.add(casing);

    const bed = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
      color: style.color, transparent: true,
      alphaMap: alpha, opacity: 1, depthWrite: false,
      // DoubleSide because a flat ribbon has no meaningful facing and the
      // triangle winding here puts its front underneath the board, where
      // back-face culling removed the entire road network from view.
      side: THREE.DoubleSide
    }));
    bed.position.y = 0.9;
    bed.renderOrder = 2;
    scene.add(bed);

    // The road a piece is currently using lights up in that seat's colour.
    const pulseAlpha = alpha.clone();
    pulseAlpha.needsUpdate = true;
    const pulse = new THREE.Mesh(
      roadRibbon(worldX(a.x), worldZ(a.y), worldX(b.x), worldZ(b.y),
                 style.width + 4, key, groundHeight),
      new THREE.MeshBasicMaterial({
        color: 0xffffff, transparent: true, opacity: 0,
        alphaMap: pulseAlpha, blending: THREE.AdditiveBlending,
        depthWrite: false, side: THREE.DoubleSide
      })
    );
    pulse.position.y = 1.3;
    pulse.renderOrder = 3;
    scene.add(pulse);
    roadByPair[key] = pulse;
  });

  /* --- cities: one terrain mound each, plus its ownership ring and field */
  /* A city no piece ever reaches this match is still on the map, just quieter:
     desaturated toward the sheet rather than swapped for grey, so it keeps its
     terrain identity while giving the contested cities the colour. */
  function moundTint(terrain, touched) {
    const tint = new THREE.Color(
      TERRAIN_TINT[terrain] !== undefined ? TERRAIN_TINT[terrain]
                                          : TERRAIN_TINT.plain);
    if (!touched) {
      // Toward a neutral stone, not toward the sheet. Lerping to SHEET_TOP was
      // fine when the sheet was mud; on cream it bleaches a quiet city until it
      // is brighter than the contested ones it is supposed to yield to.
      tint.lerp(new THREE.Color(0x8d8168), 0.44).multiplyScalar(0.92);
    }
    return tint;
  }

  const ringByCity = {};
  const glowByCity = {};
  const labelByCity = {};

  cities.forEach(function (city) {
    const x = worldX(city.x), z = worldZ(city.y);
    const touched = !!activeCities[city.id];

    const r = cityRadius(city);

    /* The mound is gone, and this is the point of the change. Twelve cones
       standing on a flat slab was the board saying "here is a city, and here
       is what it stands on" in one object -- which read, correctly, as pins
       pushed into a plane. The ground carries the relief now: a city on hills
       is high because the land under it is high, and Drelerford sits on the
       shoulder of real high ground rather than wearing a hill as a hat.

       What is left here is the settlement marker -- contact pool, rim,
       ownership ring, field, tokens -- all of it lifted to the height of the
       ground beneath it so nothing floats or sinks. */
    const gh = groundHeight(x, z);

    // Where the mound meets the paper. Everything above this is lit; this is
    // the only thing that says the two surfaces are touching.
    const contact = new THREE.Mesh(
      new THREE.PlaneGeometry(r * 3.1, r * 3.1),
      new THREE.MeshBasicMaterial({
        color: 0x3d3322, transparent: true, opacity: 0.3,
        alphaMap: texContact, depthWrite: false
      })
    );
    contact.rotation.x = -Math.PI / 2;
    contact.position.set(x, gh + 0.45, z);
    contact.renderOrder = 4;
    scene.add(contact);

    // Neutral rim at the foot of the mound; ruins are dashed and duller.
    const rim = new THREE.Mesh(
      new THREE.RingGeometry(r * 1.0, r * 1.05, 64),
      new THREE.MeshBasicMaterial({
        // Inked, not cream: a pale rim on a pale sheet is not a rim. Kept
        // light, though — under it sits the contact pool, and the two together
        // were reading as one heavy collar around every mound.
        color: city.is_ruin ? 0x8a7a5e : 0x6b5c41,
        transparent: true,
        opacity: touched ? 0.55 : 0.34,
        map: city.is_ruin ? texRingDashed : null,
        depthWrite: false
      })
    );
    if (city.is_ruin) {
      rim.geometry = new THREE.PlaneGeometry(r * 2.75, r * 2.75);
      rim.material.map = texRingDashed;
      rim.material.transparent = true;
    }
    rim.rotation.x = -Math.PI / 2;
    rim.position.set(x, gh + 1.6, z);
    rim.renderOrder = 6;
    scene.add(rim);

    // Ownership ring, painted per turn.
    const ring = new THREE.Mesh(
      new THREE.PlaneGeometry(r * 3.05, r * 3.05),
      new THREE.MeshBasicMaterial({
        color: 0xffffff, map: texRingSolid, transparent: true,
        opacity: 0, depthWrite: false
      })
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(x, gh + 2.1, z);
    ring.renderOrder = 7;
    scene.add(ring);
    ringByCity[city.id] = ring;

    // Soft field under a secured city.
    const glow = new THREE.Mesh(
      // Capped: at the widest radius an unbounded field would flood halfway
      // across the board and swallow its neighbours.
      new THREE.PlaneGeometry(Math.min(r * 7, 290), Math.min(r * 7, 290)),
      new THREE.MeshBasicMaterial({
        color: 0xffffff, map: texGlow, transparent: true, opacity: 0,
        blending: THREE.AdditiveBlending, depthWrite: false
      })
    );
    glow.rotation.x = -Math.PI / 2;
    glow.position.set(x, gh + 1.0, z);
    glow.renderOrder = 5;
    scene.add(glow);
    glowByCity[city.id] = glow;

    /* A port gets a ring of its own at the mound's foot, in the coast's ink
       rather than a seat colour, so it cannot be mistaken for ownership. The
       flag is on the map and the game reads it; a board that drops it is
       telling a coach the two harbours are ordinary inland towns. */
    if (city.is_port) {
      /* Outside the mound's skirt, not on it. At 0.72r the ring sat inside the
         footprint and the mound simply stood on top of it -- drawn every frame
         and never once visible. */
      const harbour = new THREE.Mesh(
        new THREE.TorusGeometry(r + 7, 1.5, 8, 44),
        new THREE.MeshBasicMaterial({
          color: COAST_INK, transparent: true, opacity: 0.85,
          depthWrite: false
        })
      );
      harbour.rotation.x = -Math.PI / 2;
      harbour.position.set(x, gh + 1.6, z);
      harbour.renderOrder = 4;
      scene.add(harbour);
    }

    // Labels ride the DOM, so they stay crisp and keep the page's type.
    const label = document.createElement("span");
    label.className = "atlas-label" + (touched ? "" : " is-quiet");
    const nameLine = document.createElement("span");
    nameLine.className = "atlas-label-name";
    nameLine.textContent = city.name;
    label.appendChild(nameLine);
    /* The row the 2D map prints under every city: population, grid reference,
       whatever flags it carries, then its terrain. Same order, same separator,
       so a coach reading the poster and a coach reading the app are reading
       one thing. */
    const parts = cityMetaParts(city);
    if (parts.length) {
      const metaLine = document.createElement("span");
      metaLine.className = "atlas-label-meta";
      parts.forEach(function (part) {
        const bit = document.createElement("span");
        bit.className = "bit is-" + part[0];
        bit.textContent = part[1];
        metaLine.appendChild(bit);
      });
      label.appendChild(metaLine);
    }
    labelHost.appendChild(label);
    labelByCity[city.id] = {
      node: label,
      /* A little vertical room, which cities did not have. They were placed at
         their anchor or not at all, so on a board scaled down to hold the
         whole coast a name lost to a neighbour's data row was simply gone.
         Vertical only, and small: a name that slid sideways would sit over the
         wrong mound, while one lifted a line still points down at its own. */
      candidates: [[0, 0], [0, -19], [0, 19], [0, -38]],
      anchor: new THREE.Vector3(x, gh + 26, z)
    };
  });

  /* --- tokens */
  const stackGeo = new THREE.CylinderGeometry(6.2, 7.0, 5.0, 22);
  const cmdBodyGeo = new THREE.CylinderGeometry(6.6, 8.4, 12.0, 24);
  const cmdHeadGeo = new THREE.SphereGeometry(5.4, 20, 14);
  const cmdCollarGeo = new THREE.TorusGeometry(7.4, 1.15, 10, 28);

  /* Enamelled pieces, not plastic. With an environment in the scene a low
     roughness finally buys something — a moving highlight along the shoulder
     of each token, which is what tells a small round object from a dot. */
  const seatMat = seatColors.map(function (hex) {
    return new THREE.MeshStandardMaterial({
      color: new THREE.Color(hex), roughness: 0.26, metalness: 0.05,
      envMapIntensity: 1.5,
      emissive: new THREE.Color(hex), emissiveIntensity: 0.12
    });
  });
  const creamMat = new THREE.MeshStandardMaterial({
    color: 0xf6ead0, roughness: 0.38, metalness: 0.03, envMapIntensity: 1.2
  });
  // The collar: aged brass, so the commander reads as the one piece with a
  // fitting on it rather than as a bigger chit.
  const brassMat = new THREE.MeshStandardMaterial({
    color: 0xc9a765, roughness: 0.28, metalness: 0.9, envMapIntensity: 1.8
  });

  function makeToken(kind, seatIdx) {
    const group = new THREE.Group();
    const mat = seatMat[seatIdx] || seatMat[0];

    if (kind === "character") {
      const body = new THREE.Mesh(cmdBodyGeo, mat);
      body.position.y = 6.0;
      const head = new THREE.Mesh(cmdHeadGeo, creamMat);
      head.position.y = 15.4;
      const collar = new THREE.Mesh(cmdCollarGeo, brassMat);
      collar.rotation.x = Math.PI / 2;
      collar.position.y = 11.6;
      [body, head, collar].forEach(function (m) {
        m.castShadow = true;
        group.add(m);
      });
    } else {
      const chit = new THREE.Mesh(stackGeo, mat);
      chit.position.y = 2.5;
      chit.castShadow = true;
      group.add(chit);
    }

    group.scale.setScalar(0.001);   // grown in by the caller's fade
    scene.add(group);
    return group;
  }

  /* --- region names and road mileages, on the same overlay as the city names.

     The region names are the one thing here the 2D map does NOT draw: it names
     the landmass instead, from a majority vote among its cities' regions. On
     this map that vote is a 4/4/4 tie, so a single name would describe a third
     of the board and imply it covered all of it. Three anchors, one per
     region, say what is actually true. */
  const extraLabels = [];

  (options.regions || []).forEach(function (region) {
    const node = document.createElement("span");
    node.className = "atlas-region";
    node.textContent = region.name;
    labelHost.appendChild(node);
    extraLabels.push({
      node: node,
      rank: 0,
      candidates: [[0, 0], [0, -26], [0, 26], [0, -52], [0, 52],
                   [-70, 0], [70, 0], [-70, -30], [70, 30]],
      anchor: (function () {
        const rx = worldX(region.x), rz = worldZ(region.y);
        return new THREE.Vector3(rx, groundHeight(rx, rz) + 3, rz);
      })()
    });
  });

  /* Mileage and movement cost at each road's midpoint, as the 2D map labels
     them on a sparse board. Both numbers or neither: a distance without its
     cost is trivia, and the cost is what a coach's orders are actually spent
     in. */
  roads.forEach(function (road) {
    const a = cityById[road.from], b = cityById[road.to];
    if (!a || !b) { return; }
    if (road.distance_miles == null && road.move_cost == null) { return; }
    const bits = [];
    if (road.distance_miles != null) { bits.push(road.distance_miles + " mi"); }
    if (road.move_cost != null) { bits.push(road.move_cost + " mv"); }
    const node = document.createElement("span");
    node.className = "atlas-road-label";
    node.textContent = bits.join(" \u00b7 ");
    labelHost.appendChild(node);
    extraLabels.push({
      node: node,
      rank: 1,
      candidates: [[0, 0], [0, -15], [0, 15], [-42, 0], [42, 0]],
      anchor: (function () {
        const mx = (worldX(a.x) + worldX(b.x)) / 2;
        const mz = (worldZ(a.y) + worldZ(b.y)) / 2;
        return new THREE.Vector3(mx, groundHeight(mx, mz) + 4, mz);
      })()
    });
  });

  /* --- projection for the DOM labels */
  const projected = new THREE.Vector3();
  let viewW = 1, viewH = 1;

  /* Label planning, which the 2D map has and this board did not.

     Twelve names was a set no arrangement could collide; twelve names each
     with a data row, three region titles and fourteen road readings is
     forty-one boxes on a board the reader can spin, and at some angles most of
     them land on each other. webapp/mapview.py solves the same problem with
     `_plan_city_labels` and `_boxes_overlap` -- it ranks its labels and drops
     the ones that will not fit. This is the same idea in screen space, where
     it has to be, because which labels collide depends on where the camera is
     and that changes every frame.

     Rank: a city's name outranks everything, then the region it stands in,
     then the road readings. Dropping a mileage costs a reader a number they
     can get by turning the board; dropping a city name costs them the city. */
  const placed = [];

  function place(entry) {
    const node = entry.node;
    projected.copy(entry.anchor).project(camera);
    // Behind the camera, or outside the frustum: hide rather than smear.
    if (projected.z > 1) { node.style.opacity = "0"; return; }

    const x = (projected.x * 0.5 + 0.5) * viewW;
    const y = (-projected.y * 0.5 + 0.5) * viewH;

    /* Measured once. The text never changes after it is built, and reading
       offsetWidth per label per frame would force a layout flush inside the
       render loop -- forty-one of them, sixty times a second. */
    if (!entry.w) {
      entry.w = node.offsetWidth || 1;
      entry.h = node.offsetHeight || 1;
    }
    /* Several boxes before giving up, as mapview's `_label_candidates` does.
       A name that will not fit where its anchor points may fit a line above or
       to one side, and a region title nudged 30px off a mound is still telling
       the truth about which ground it names. Cities do not move: their anchor
       IS the city. */
    /* Held inside the frame. `.atlas-labels` clips at overflow:hidden, so a
       label whose anchor sits near an edge does not run off the board -- it
       gets its right-hand half sliced away and reads as a truncated word.
       Bare city names were narrow enough never to hit it; a name over a data
       row is three times wider and hits it on a phone constantly.

       A clamp moves the label off its anchor, so it is bounded: past
       MAX_NUDGE the label is far enough from its city to be misread as
       naming a different one, and is dropped instead. */
    const MAX_NUDGE = 56;
    const pad = 2;
    const candidates = entry.candidates || [[0, 0]];
    for (let c = 0; c < candidates.length; c++) {
      const wantX = x + candidates[c][0], wantY = y + candidates[c][1];
      const half = entry.w / 2;
      const cx = Math.min(Math.max(wantX, half + pad), viewW - half - pad);
      const cy = Math.min(Math.max(wantY, entry.h / 2 + pad),
                          viewH - entry.h / 2 - pad);
      if (Math.abs(cx - wantX) > MAX_NUDGE ||
          Math.abs(cy - wantY) > MAX_NUDGE) { continue; }
      const box = [cx - entry.w / 2 - pad, cy - entry.h / 2 - pad,
                   cx + entry.w / 2 + pad, cy + entry.h / 2 + pad];
      let hit = false;
      for (let i = 0; i < placed.length; i++) {
        const other = placed[i];
        if (box[0] < other[2] && box[2] > other[0] &&
            box[1] < other[3] && box[3] > other[1]) { hit = true; break; }
      }
      if (hit) { continue; }
      placed.push(box);
      node.style.transform =
        "translate(-50%,-50%) translate(" + cx.toFixed(1) + "px," +
        cy.toFixed(1) + "px)";
      node.style.opacity = "";
      return;
    }
    node.style.opacity = "0";
  }

  function placeLabels() {
    placed.length = 0;
    // Highest rank first: whoever is placed owns the space.
    Object.keys(labelByCity).forEach(function (id) {
      place(labelByCity[id]);
    });
    extraLabels
      .slice()
      .sort(function (a, b) { return a.rank - b.rank; })
      .forEach(place);
  }

  /* --- framing: pull the camera in until the printed sheet just fills the
         frame. Fitting the eight corners beats a bounding sphere here, because
         the board is a flat slab seen at an angle and a sphere would leave a
         third of the frame empty. */
  /* Fit to the CITIES, not to the sheet. Framing the whole slab guarantees its
     corners are inside the frame, which for a rotated rectangle in perspective
     means roughly half the frame is left as backdrop — and the backdrop here is
     near-black, so the picture reads dark however well the board itself is lit.
     Framing the city box instead lets the sheet run off the edges, which is
     what "cropped to the city bounding box plus one margin, so there is no dead
     space" asks for anyway. The margin keeps each city's tokens, ring and label
     inside the frame with it. */
  // Room for the widest mound plus its tokens, ring and label.
  const FIT_M = maxRadius + 46;
  // The tallest ground, not the tallest mound -- there are no mounds now.
  const topY = terrainPeak + 34;

  /* Fit the OBJECT, not the land inside it. While the board was a printed
     plate the sheet was allowed to run off the edges -- it was backdrop, and
     cropping it cost nothing. It is a body of water with a landmass standing
     in it now, and a sea cut off mid-frame reads as a rendering that did not
     fit rather than as a map. So the box is the sheet's own extent, which is
     wider than the land box by PAD, and the picture scales down to hold it. */
  const fitHalfW = Math.max((maxX - minX) / 2 + FIT_M, (sheetW - REVEAL * 2) / 2);
  const fitHalfD = Math.max((maxY - minY) / 2 + FIT_M, (sheetD - REVEAL * 2) / 2);
  const sheetCorners = [];
  [-fitHalfW, fitHalfW].forEach(function (x) {
    [-fitHalfD, fitHalfD].forEach(function (z) {
      // Down to the waterline as well as up to the tallest mound: the land is
      // a solid now and its cliff and the sea around it are part of the
      // picture, so a box that starts at the land surface crops them off.
      [-LAND_H, 0, topY].forEach(function (y) {
        sheetCorners.push(new THREE.Vector3(x, y, z));
      });
    });
  });

  /* Two things have to happen together, which is why this iterates: the board
     is scaled until its widest projected axis fills the frame, and the aim
     point is slid until the projected box is centred. Scaling alone leaves the
     board high and to one side, because a tilted slab does not project
     symmetrically about the point you are looking at. */
  function fitCamera(fill) {
    const v = new THREE.Vector3();
    const right = new THREE.Vector3();
    const up = new THREE.Vector3();

    for (let iter = 0; iter < 14; iter++) {
      camera.updateMatrixWorld();
      camera.updateProjectionMatrix();

      let minx = Infinity, maxx = -Infinity, miny = Infinity, maxy = -Infinity;
      for (let i = 0; i < sheetCorners.length; i++) {
        v.copy(sheetCorners[i]).project(camera);
        if (v.x < minx) { minx = v.x; }
        if (v.x > maxx) { maxx = v.x; }
        if (v.y < miny) { miny = v.y; }
        if (v.y > maxy) { maxy = v.y; }
      }

      const dist = camera.position.distanceTo(controls.target);
      const worldH = 2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2) * dist;
      const worldW = worldH * camera.aspect;

      // Centre: slide the aim point across the camera's own plane.
      right.setFromMatrixColumn(camera.matrixWorld, 0);
      up.setFromMatrixColumn(camera.matrixWorld, 1);
      const shift = right.multiplyScalar((minx + maxx) / 2 * worldW / 2)
        .add(up.multiplyScalar((miny + maxy) / 2 * worldH / 2));
      controls.target.add(shift);
      camera.position.add(shift);

      // Scale: grow the board until its widest axis reaches the frame.
      const worst = Math.max((maxx - minx) / 2, (maxy - miny) / 2) / fill;
      if (Math.abs(worst - 1) < 0.004 && shift.length() < dist * 0.001) { break; }
      const dir = camera.position.clone().sub(controls.target).normalize();
      camera.position.copy(controls.target).addScaledVector(dir, dist * worst);
    }

    const dist = camera.position.distanceTo(controls.target);
    controls.minDistance = dist * 0.55;
    controls.maxDistance = dist * 1.85;
    return dist;
  }

  /* --- resize */
  function resize() {
    const rect = canvas.parentElement.getBoundingClientRect();
    viewW = Math.max(1, Math.round(rect.width));
    viewH = Math.max(1, Math.round(rect.height));
    renderer.setSize(viewW, viewH, false);
    camera.aspect = viewW / viewH;
    camera.updateProjectionMatrix();
    // Refit only while the board is still driving itself; once the reader has
    // taken the camera, a resize must not yank it back.
    if (!userDriving) { fitCamera(0.96); }
    /* Measured widths are cached, and a resize can cross the breakpoint that
       decides how much of each data row is shown -- so the cache has to die
       with the old width or every label is planned against a size it no
       longer has. */
    Object.keys(labelByCity).forEach(function (id) { labelByCity[id].w = 0; });
    extraLabels.forEach(function (entry) { entry.w = 0; });
    placeLabels();
  }

  if ("ResizeObserver" in window) {
    new ResizeObserver(resize).observe(canvas.parentElement);
  } else {
    window.addEventListener("resize", resize);
  }
  resize();

  /* --- the loop */
  let running = false;
  let onFrame = null;
  let last = performance.now();
  let swayT = 0;

  function loop(now) {
    if (!running) { return; }
    const dt = Math.min((now - last) / 1000, 0.1);
    last = now;

    // A slow sway around the hero angle, so the relief reads as relief and the
    // parallax sells the third dimension. Deliberately a sway and not a spin:
    // a full orbit would swing the board through every bad composition there
    // is, and the frame is fitted for this one.
    if (!userDriving && !reducedMotion) {
      swayT += dt;
      const dist = camera.position.distanceTo(controls.target);
      placeCamera(HERO_AZIMUTH + Math.sin(swayT * 0.16) * 0.13, dist);
      camera.lookAt(controls.target);
    }

    for (let i = pulses.length - 1; i >= 0; i--) {
      const p = pulses[i];
      p.t += dt;
      const k = 1 - p.t / p.life;
      p.mesh.material.opacity = k > 0 ? k * 0.9 : 0;
      if (k <= 0) { pulses.splice(i, 1); }
    }

    if (onFrame) { onFrame(now); }

    controls.update();
    placeLabels();
    renderer.render(scene, camera);
    requestAnimationFrame(loop);
  }

  /* ------------------------------------------------------------------- api */

  return {
    /* Where piece k of a seat stands at a city, in world units. Deterministic,
       so a piece keeps its place in the column between turns and only moves
       when it really moves. */
    slot: function (city, seatIdx, seatCount, k, total) {
      const ring = Math.floor(k / PER_RING);
      const idx = k % PER_RING;
      const inRing = Math.min(total - ring * PER_RING, PER_RING);
      const radius = cityRadius(city) + 17 + ring * 15;
      const base = seatCount > 1 ? (seatIdx === 0 ? 180 : 0) : 270;
      const angle = (base + (idx - (inRing - 1) / 2) * STEP_DEG) * Math.PI / 180;
      return {
        x: worldX(city.x) + radius * Math.cos(angle),
        z: worldZ(city.y) + radius * Math.sin(angle)
      };
    },

    /* Tokens stand ON the ground, which is no longer a plane. Both of these
       sample it: a piece walking the Dreliwick-Narunon road climbs with the
       road, and a piece raised on high ground is raised. */
    addToken: function (kind, seatIdx, x, z) {
      const node = makeToken(kind, seatIdx);
      node.position.set(x, groundHeight(x, z), z);
      return node;
    },

    moveToken: function (node, x, z, lift) {
      node.position.set(x, groundHeight(x, z) + (lift || 0), z);
    },

    /* Tokens fade by scale, which also reads as "raised here" / "gone". */
    setTokenPresence: function (node, k) {
      const s = Math.max(k, 0.0001);
      node.scale.setScalar(s);
    },

    dropToken: function (node) {
      scene.remove(node);
    },

    pulseRoad: function (fromCity, toCity, hex) {
      if (reducedMotion) { return; }
      const mesh = roadByPair[pairKey(fromCity, toCity)];
      if (!mesh) { return; }
      mesh.material.color.set(hex);
      mesh.material.opacity = 0.9;
      pulses.push({ mesh: mesh, t: 0, life: 1.0 });
    },

    paintCity: function (cityId, securedHex, occupiedHex) {
      const ring = ringByCity[cityId];
      const glow = glowByCity[cityId];
      if (!ring) { return; }
      if (securedHex) {
        ring.material.map = texRingSolid;
        ring.material.color.set(securedHex);
        ring.material.opacity = 1;
        glow.material.color.set(securedHex);
        // Additive on cream clips much sooner than it did on mud.
        glow.material.opacity = 0.34;
      } else if (occupiedHex) {
        ring.material.map = texRingDashed;
        ring.material.color.set(occupiedHex);
        ring.material.opacity = 0.9;
        glow.material.opacity = 0;
      } else {
        ring.material.opacity = 0;
        glow.material.opacity = 0;
      }
      ring.material.needsUpdate = true;
    },

    setFrameCallback: function (fn) { onFrame = fn; },

    startLoop: function () {
      if (running) { return; }
      running = true;
      last = performance.now();
      requestAnimationFrame(loop);
    },

    stopLoop: function () { running = false; },

    /* Redraw on demand when the loop is parked — the reduced-motion board and
       the scrolled-away board are both static, but the reader can still turn
       them with the mouse and that has to paint. */
    renderOnIdleChange: function () {
      controls.addEventListener("change", function () {
        if (!running) {
          controls.update();
          placeLabels();
          renderer.render(scene, camera);
        }
      });
    },

    /* One frame on demand, for a paused or reduced-motion board. */
    renderOnce: function () {
      controls.update();
      placeLabels();
      renderer.render(scene, camera);
    },

    resize: resize
  };
}
