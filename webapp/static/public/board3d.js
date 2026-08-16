/* The Living Atlas — atlas relief board, rendered in three.js.
 *
 * WHAT THIS IS ALLOWED TO DRAW (docs/MARKETING_CLOSED_ALPHA.md, "Visual
 * contract: atlas board"):
 *
 *   - the twelve cities at their exact x/y under one uniform scale;
 *   - the fourteen roads exactly as listed, weighted by quality;
 *   - around each city a terrain-textured *mound* from its terrain label —
 *     "local relief only";
 *   - empty surrounding space left empty;
 *   - and: "The page may rotate or tilt the board."
 *
 * WHAT IT MUST NEVER DRAW: "Inventing coastlines, continents, or elevation the
 * map does not have." So there is no heightfield, no interpolated ground
 * between cities, no shore and no sea. The sheet is a printed board on a table,
 * not a landmass, and it stops at the frame. Every millimetre of elevation in
 * this scene comes from one of twelve `terrain` labels; nothing is invented
 * between them.
 *
 * The mound heights are the terrain labels and nothing else:
 *   hills -> tall, plain -> low, desert -> lowest and flattest.
 */

import * as THREE from "three";
import { OrbitControls } from "./vendor/OrbitControls.js?v=h2";

/* Board units. One unit of fractional map coordinate = SU units, on both
   axes, so the recorded geometry is never stretched. */
const SU = 1000;
const PAD = 105;          // empty margin around the city bounding box
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
/* The ground is a printed board, and it must not be water.
   An earlier pass copied mapview._background wholesale, which brought the
   game's `#mapSea` gradient with it — and the contract is explicit: "Empty
   surrounding space stays empty. No sea, no implied landmass, no invented
   shore." Navy ground reads as ocean and turns twelve cities into islands, so
   this is board stock instead. The 48-unit grid stays: a ruled grid is a map
   convention, not a claim about geography.

   calib_12.json contains `cities` and `roads` and nothing else — no coastline,
   no land polygon, no elevation. The game gets its land for this map from
   compute_landmasses(), which invents hulls around city clusters. The poster
   is not allowed to do that, so there is no land here by design. */
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
function roadRibbon(ax, az, bx, bz, width, key) {
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
    pos.push(px + nx * width / 2, 0, pz + nz * width / 2);
    pos.push(px - nx * width / 2, 0, pz - nz * width / 2);
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

  /* --- frame: cropped to the city bounding box plus one margin, so there is
         no dead space and no room to imply a coastline. */
  const xs = cities.map(function (c) { return c.x * SU; });
  const ys = cities.map(function (c) { return c.y * SU; });
  const minX = Math.min.apply(null, xs), maxX = Math.max.apply(null, xs);
  const minY = Math.min.apply(null, ys), maxY = Math.max.apply(null, ys);
  const midX = (minX + maxX) / 2, midY = (minY + maxY) / 2;
  const sheetW = (maxX - minX) + 2 * PAD;
  const sheetD = (maxY - minY) + 2 * PAD;
  const span = Math.max(sheetW, sheetD);

  // Map coordinates are y-down; the scene is z-in. One uniform scale, centred.
  function worldX(fx) { return fx * SU - midX; }
  function worldZ(fy) { return fy * SU - midY; }

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
        Math.hypot((c.x - o.x) * SU, (c.y - o.y) * SU));
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
  board.position.y = -PLATE_T - SHEET_T / 2;
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
  plate.position.y = -PLATE_T / 2;          // its printed face stays at y = 0
  plate.receiveShadow = true;
  scene.add(plate);

  // The ruling stops at the neatline, as it does on a printed plate.
  const ruled = graticuleGeometry(
    (sheetW - REVEAL * 2) / 2 - SHEET_INSET,
    (sheetD - REVEAL * 2) / 2 - SHEET_INSET,
    0.3);
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
  table.position.y = -SHEET_T - PLATE_T - 1;
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
                           style.width, key);
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
                 style.width + 3.4, key),
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
                 style.width + 4, key),
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

  const moundGeoCache = {};
  const ringByCity = {};
  const glowByCity = {};
  const labelByCity = {};
  const moundTopY = {};

  cities.forEach(function (city) {
    const x = worldX(city.x), z = worldZ(city.y);
    const touched = !!activeCities[city.id];
    const height = MOUND_H[city.terrain] !== undefined
      ? MOUND_H[city.terrain] : MOUND_H.plain;
    moundTopY[city.id] = height;

    const r = cityRadius(city);
    // Seeded from the id, so each city has its own landform and keeps it.
    const seed = hashKey(city.id + "|" + city.terrain);
    const cacheKey = city.terrain + "|" + height + "|" + r.toFixed(2) +
                     "|" + seed;
    if (!moundGeoCache[cacheKey]) {
      moundGeoCache[cacheKey] = moundGeometry(city.terrain, height, r, seed);
    }

    const map = terrainMap(city.terrain);
    const mound = new THREE.Mesh(
      moundGeoCache[cacheKey],
      applyContours(new THREE.MeshStandardMaterial({
        map: map,
        bumpMap: map,           // the jpg doubles as its own relief
        // Bump is a derivative-space perturbation, not a height in board
        // units: anything above ~0.1 tips the normals past the key light and
        // the mound falls back to ambient, which reads as flat grey.
        bumpScale: 0.16,
        roughness: 0.82,
        metalness: 0,
        envMapIntensity: 0.5,
        color: moundTint(city.terrain, touched),
        // A little self-colour, so a mound keeps its hue where the key light
        // does not reach instead of dropping to a grey silhouette.
        emissive: moundTint(city.terrain, touched).multiplyScalar(0.13)
      // Four and a half bands to the summit: enough to survey the form,
      // and never a whole number, which would put a contour on the plateau.
      }), Math.max(height, 1) / 4.5)
    );
    mound.position.set(x, 0, z);
    mound.castShadow = true;
    mound.receiveShadow = true;
    scene.add(mound);

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
    contact.position.set(x, 0.45, z);
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
    rim.position.set(x, 1.6, z);
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
    ring.position.set(x, 2.1, z);
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
    glow.position.set(x, 1.0, z);
    glow.renderOrder = 5;
    scene.add(glow);
    glowByCity[city.id] = glow;

    // Labels ride the DOM, so they stay crisp and keep the page's type.
    const label = document.createElement("span");
    label.className = "atlas-label" + (touched ? "" : " is-quiet");
    label.textContent = city.name;
    labelHost.appendChild(label);
    labelByCity[city.id] = {
      node: label,
      anchor: new THREE.Vector3(x, height + 12, z)
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

  /* --- projection for the DOM labels */
  const projected = new THREE.Vector3();
  let viewW = 1, viewH = 1;

  function placeLabels() {
    Object.keys(labelByCity).forEach(function (id) {
      const entry = labelByCity[id];
      projected.copy(entry.anchor).project(camera);
      const x = (projected.x * 0.5 + 0.5) * viewW;
      const y = (-projected.y * 0.5 + 0.5) * viewH;
      const node = entry.node;
      node.style.transform =
        "translate(-50%,-50%) translate(" + x.toFixed(1) + "px," +
        y.toFixed(1) + "px)";
      // Behind the camera, or outside the frustum: hide rather than smear.
      node.style.opacity = projected.z > 1 ? "0" : "";
    });
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
  const topY = Math.max.apply(null, cities.map(function (c) {
    return MOUND_H[c.terrain] !== undefined ? MOUND_H[c.terrain] : MOUND_H.plain;
  })) + 34;

  const sheetCorners = [];
  [minX - midX - FIT_M, maxX - midX + FIT_M].forEach(function (x) {
    [minY - midY - FIT_M, maxY - midY + FIT_M].forEach(function (z) {
      [0, topY].forEach(function (y) {
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

    addToken: function (kind, seatIdx, x, z) {
      const node = makeToken(kind, seatIdx);
      node.position.set(x, 0, z);
      return node;
    },

    moveToken: function (node, x, z, lift) {
      node.position.set(x, lift || 0, z);
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
