# Building the world map

The map is generated, not drawn. Every town, route, mileage and grid
reference comes from the gamemaster's own gazetteer, and the geography is
traced from the original raster, so the poster and the engine read from the
same file and cannot drift apart.

## Sources

> **This pipeline is being retired.** Both of its inputs are third-party
> material and are no longer tracked in the repo — they now live in the
> untracked `reference/` directory. Its replacement is
> `scripts/generate_world.py`, which synthesises an equivalent world from a
> seed:
>
> ```
> python scripts/generate_world.py --seed 1 --out maps/world.json
> python scripts/generate_world.py --seed 1 --stats
> ```
>
> See [`ip_cleanroom.md`](ip_cleanroom.md). What follows documents the legacy
> pipeline for anyone rebuilding the traced map locally.

| File | What it is |
|---|---|
| `reference/soe_map_index.txt` | The gamemaster's gazetteer: 154 towns with population, terrain, magic-free status and grid reference, plus all 460 route legs with quality and mileage. Recovered from the Internet Archive capture of `srv.net/~ram/soe_map_index.txt` cited by the original map print. |
| `reference/soe_map_sample.png` | The author's original 586x452 map. A flat 19-colour palette, so terrain is recoverable exactly by colour-keying. |

Both are authoritative inputs and should not be hand-edited.

## Pipeline

Install the build-time extras once — they are not needed to run the engine:

```
pip install -e ".[map]"
```

Then run the five stages in order:

```
python scripts/build_world_map.py     # gazetteer  -> maps/soe_world.json
python scripts/extract_geography.py   # raster     -> maps/soe_geography.json
python scripts/solve_positions.py     # adds x_miles/y_miles to soe_world.json
python scripts/assign_regions.py      # adds region to soe_world.json
python scripts/render_map.py          # both       -> maps/soe_world_map.svg
```

`extract_geography.py --debug` also writes `docs/debug_terrain.png`, a flat
render of the classified terrain useful for checking the colour keying.

For a print-resolution copy, raise the pixels-per-mile:

```
python scripts/render_map.py --scale 3.0 --out maps/soe_world_map_print.svg
```

## Surface textures

`maps/textures/*.jpg` are neutral greyscale tiles applied as multiply
overlays — paper, sea, and one per terrain type. They are the only part of
the map not derived from the gamemaster's data, and they carry no
information: they change how the ground *looks*, never where anything is.
Because they are greyscale and multiplied, the palette, every coastline,
label, route and position come through exactly as the deterministic layers
produced them.

They were generated once with an image model and are committed as
processed tiles; `docs/texture_sources.json` records the model, prompts and
(now-expired) source URLs. Rebuilding them is only needed to change the
look:

```
python scripts/build_textures.py --manifest docs/texture_sources.json
```

`build_textures.py` makes each tile seamless by four-way mirroring, which
is exact rather than approximate, and normalises it to sit near white so
the multiply darkens only where the texture has detail. Tile sizes in
`render_map.py` are quoted at `--scale 1.6` and scale with the output, so
the texture reads the same at any poster size.

Render without them for a flat, faster map:

```
python scripts/render_map.py --no-textures
```

Outlines are smoothed with two rounds of Chaikin corner-cutting at draw
time. The geography is traced from a 586px raster, so every outline arrives
as a staircase of axis-aligned steps; the smoothing moves points by well
under the 2.5-mile source pixel.

## How the geography is recovered

The raster's margins carry grid ticks exactly 40px apart, which registers
the field to 13x10 cells and fixes the scale at **2.5 miles per pixel** —
so one grid square is exactly 100 miles and the field is 1300 x 1000 miles.
Terrain is colour-keyed against the legend swatches; roads, rivers and
labels are drawn *over* the terrain, so their line-shaped holes are closed
morphologically before contours are traced. Two colour collisions are
resolved by shape: sea lanes share the desert yellow (an opening removes
the 1-2px lanes), and swamp is teal stipple over the forest green (the
speckled components become swamp).

## How towns are positioned

The gazetteer gives a grid cell but not a point. Positions are solved from
three constraints at once:

- the town's grid cell (100 miles square),
- the terrain it is stated to sit on,
- the mileages of its routes.

`solve_positions.py` runs stress majorization against the route mileages,
projecting each town back onto the legal pixels of its cell after every
step. Because a route is longer than the straight line it spans, the
detour factor is fitted per route type each iteration rather than assumed,
and clamped at 1.0.

Current fit: land routes run 1.075x crow-flight, sea lanes 1.116x, with a
median residual of ~15 miles on a 1300-mile map.

Grid references are treated as a *preference*, not a hard bound. A handful
were hand-assigned by the gamemaster and name a cell holding no land at
all, so a town falls back to the surrounding ring of cells rather than
being stranded in the sea. `solve_positions.py --report` lists every town
that needed the fallback.

## How regions are named

The gazetteer names towns but never lands, so the fifteen region names —
Kyupaa, Slamoniya, Olighotsi and the rest — exist only as blue labels
painted on the raster. Transcribing them is the one step in the pipeline
that needed a pair of eyes; it is confined to the `LABELS` table at the
top of `assign_regions.py`, which records each name with the pixel box of
its label.

From there it is derivation again. Each label's box centre is converted to
miles and matched to the nearest coastline, and the script asserts the
result is a bijection: fifteen labels, fifteen coastlines, one each. Every
town then takes the name of the landmass it stands on, by point-in-polygon
against the traced coastlines, falling back to the nearest coast within 60
miles for towns whose solved position sits just offshore. All 154 towns
land inside that tolerance.

Four labels — `Ajd`, `Juansaye`, `Ipsen` and `Taatun`, covering 14 towns
between them — are set in the map's smallest and most horizontally
squeezed face, and their letters are genuinely ambiguous at 586px. They
are marked `certain=False` in the table and `--report` flags them. No
larger scan of the map survives: the only capture is the 586x452 PNG the
author himself called "very squished", and neither the rules nor the
gazetteer mentions a region by name.

## Known data features (not bugs)

- **Wishiyam** (B4, pop 0, desert, magic-free) has no routes at all and is
  listed in the source with a trailing full stop marking the entry as
  complete. It is a genuinely unreachable ruin in the deep desert, and the
  engine's `isolated_cities` warning about it is correct.
- Forty-five of the gazetteer's non-water routes join towns the coastline
  trace puts on different landmasses — Ajapit to Tuus Gan across the strait
  north of Slamoniya, Benkamu to Chandri Oasis, and so on. Road
  connectivity is therefore not a reliable proxy for "same island" on this
  map, which is why `validate_map_warnings` reports Hamrika, Kyupaa,
  Olighotsi and Slamoniya as spanning landmasses "no land road joins". The
  regions are right; the warning is measuring something else, and turn
  reports fall back to `Landmass N` for those four.
- The world's largest town is 134,000. The engine's population bands are
  therefore the original's own four-tier legend (>100k / 10k-99,999 /
  1k-9,999 / <1k), which splits the 154 towns 4 / 22 / 50 / 78. Pitching
  them at real-world city sizes instead left the top band empty and put
  128 towns in the bottom one. The map renders symbols from the exact
  `population` against the same four tiers, plus a mark for the 20 ruins.
