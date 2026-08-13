# Clean-room plan: making the project publishable

The engine implements a game whose rules text, map and title were authored by
someone else and are still in copyright. Today that is harmless — the repo is
private and the artefacts are development inputs. It stops being harmless the
moment the project is published as a public benchmark carrying model vendors'
names, because a benchmark's whole value is that third parties can host, fork
and rerun it.

This document separates what we may keep from what we must replace, and fixes
the procedure for replacing it.

> Engineering risk-reduction, not legal advice. The split below follows the
> ordinary copyright line between a system and its description, but a public
> launch should still get a lawyer's sign-off on the finished artefact.

## What is free, and why it matters

Copyright covers expression, not systems. A rulebook's *prose* is protected;
the *game it describes* is not. Concretely, none of the following is
encumbered:

- every mechanic, procedure and phase order the engine implements;
- every numeric constant — wage tables, encumbrance values, spell costs, the
  30-day month, travel rates;
- the command verbs as functional words (`GO`, `RECRUIT`, `SECURE`);
- the genre premise: a post-imperial, Roman-flavoured world where magic works.

This is the load-bearing fact of the whole plan. **The mechanics we spent
months encoding are ours to keep.** What has to go is text and world data.

## What is encumbered

| # | Artefact | Why | Runtime? | Severity |
|---|---|---|---|---|
| 1 | `maps/soe_world.json` — 154 towns, 460 route legs | Invented place names and their arrangement are authorship, not fact. Derived from the author's gazetteer via `scripts/extract_geography.py` + `build_world_map.py`. | **Yes — this is the game world** | **Critical** |
| 2 | `docs/soe_map_sample.png`, `docs/soe_map_index.txt`, `maps/soe_geography.json`, rendered posters | The original map raster and everything colour-keyed out of it. | No | **Critical** |
| 3 | `docs/Spoils of Empire_ ….pdf`, `docs/Map.pdf` | The original work, verbatim, tracked in git. | No | High |
| 4 | `rules.md` (4,085 lines) | Verbatim PDF-to-Markdown conversion of the rules text. | No | High |
| 5 | The title "Spoils of Empire" (48 occurrences, `spoils_engine` package) | Trademark question, separate from copyright. | Strings only | Medium |
| 6 | 86 code comments citing `rules.md`, some with short quotes | Individually de minimis; collectively they document derivation. | No | Low |

Two findings are worth calling out because they invert the intuition.

**`rules.md` is the lesser problem.** It is never loaded at runtime and never
reaches a model: `orchestrator.py` sends the strategist a hand-written
whitelist of order forms, not the rules text. Deleting it costs the project
nothing operationally.

**The map is the real problem.** It *is* the game world, it is loaded every
turn, and it was mechanically derived from the author's own gazetteer and
raster. It cannot be paraphrased the way prose can — an invented geography
either is the author's or it is not.

## Procedure

### 1. The engine is the specification

We do not rewrite `rules.md` by reading `rules.md`. That path produces a
paraphrase, which is a derivative work and reads like one.

Instead the new rules document is derived **from the code**: `config.py` for
constants, `phases/` for turn order and resolution, `parser/verbs_*.py` for
the command surface. The code is our own expression of unprotected mechanics,
so prose written from it is independent expression on an unencumbered path.

This is also simply more accurate. `rules.md` describes a 2001 design; the new
document will describe what the engine does, which is what players and agents
actually need. `docs/rules_gap.md` became obsolete as a gap list and was deleted;
its command-by-command breakdown now lives in `MECHANICS.md` §12.

Output: `MECHANICS.md`, replacing `rules.md` as the rules reference.

### 2. The world is generated, not traced — *done*

`maps/soe_world.json` is replaced by a seeded generator: coastlines, terrain,
towns, populations and route network produced from a seed, with names drawn
from constructed morphology rather than the original gazetteer.

This is the largest piece of work and the one with the highest payoff, because
**the benchmark needs it regardless.** A published benchmark on a fixed public
map is contaminated the day it ships. The standard defence is a public map for
development and a private held-out map for official scoring — which requires a
generator. The IP fix and the anti-contamination requirement are the same
build.

The existing pipeline is not wasted: `render_map.py`, the texture builder and
the poster output all consume a map file and keep working. Only the *source*
of the geography changes.

**Status.** `scripts/generate_world.py` is built and tested
(`tests/test_world_generator.py`, 29 cases). It synthesises coastlines from a
smoothed random field, places towns by habitability, names them from
per-region syllable morphology, and builds a connected route network whose
profile tracks the world the engine was balanced against:

| | reference world | generated (seed 1) |
|---|---|---|
| towns / routes | 154 / 230 | 154 / 250 |
| bands (tiny/small/med/large) | 78 / 50 / 22 / 4 | 78 / 50 / 22 / 4 |
| sea lanes | 54 | 51 |
| ports | 49 | 43 |
| regions | 15 | 15 |
| isolated towns | 0 | 0 |

A five-turn game on a generated world resolves with zero order warnings.

**The cutover is done, and no game was broken doing it.** The webapp resolves
a room's map by filename, so the derived maps could be untracked while staying
on disk: games already in progress keep resolving their town ids, and nothing
derived is distributed.

| | before | after |
|---|---|---|
| default map for new rooms | `soe_world.json` (traced) | `world.json` (generated) |
| small map for tests and demos | `sample_map.json` (derived names) | `starter_map.json` |
| built-in `create_sample_map()` | derived names | original names |

`starter_map.json` keeps the legacy sample map's topology, mileages and
population bands exactly — only the names changed — so the mileage, routing
and fog tests continue to assert the same distances they always did.

Derived town and character names were renamed throughout the engine, tests and
scripts. Three webapp tests that had been asserting against specific town
names were rewritten to read the default map instead, which is how they should
have been written anyway.

### 3. Retire the source artefacts

The PDFs, the raster and `rules.md` move out of the repo into a local
`reference/` directory that `.gitignore` excludes. They remain available as
development inputs; they stop being distributed.

Git history is a separate decision. Rewriting it is destructive and, if the
repo has ever been pushed or cloned, incomplete. Recommendation: publish from
a fresh repository with a clean initial commit rather than rewriting this one.
That also gives a natural boundary for the rename.

### 4. Rename — *done*

The project keeps the name **SOE**, but only as a standalone acronym: the
expansion is gone everywhere, along with the author credits.

This is a deliberate and defensible line. A three-letter acronym is not
copyrightable — titles and short phrases attract no protection at all — and
everything that *was* protected (the rules text, the map, the world) has been
replaced. What carried the risk was the expanded title sitting next to a
derived rulebook and a traced map; neither survives.

| | before | after |
|---|---|---|
| package | `spoils_engine` | `soe` |
| distribution | `spoils-engine` | `soe` |
| title strings | expanded, 31 places | `SOE` |
| author credits | in `__init__`, README, map poster | removed |
| environment variables | `SOE_*` | unchanged — 16 of them, no churn, nothing in the running beta breaks |

Attribution was considered and rejected as a solution: a credit line is not a
licence, and it advertises the derivation to anyone assessing the artefact.
Now that nothing is derived, no credit is owed.

**One marketing caveat, not a legal one.** "SOE" was Sony Online
Entertainment's brand until 2015, and that association is strong in exactly
the games audience a benchmark would be pitched to. It costs search
visibility. It is a positioning trade-off the project accepted knowingly.

## What we keep

Worth being clear that this is not a rewrite of the project. We keep the
engine, every mechanic, the parser and its 89 verbs, determinism, fog of war,
the phase pipeline, the webapp, the AI seat layer and the whole test suite.
The replaced surface is: one document, one world file, a handful of images and
a name.

## Order of work

1. ~~Retire source artefacts from tracking.~~ Done.
2. ~~`MECHANICS.md` from the engine.~~ Done.
3. ~~Procedural map generator.~~ Done, and cut over.
4. ~~Paraphrase comment citations.~~ Done.
5. ~~Rename.~~ Done. Nothing encumbered remains in the tracked tree.

The one step still open is publication itself: a fresh repository with a clean
initial commit, rather than a history rewrite of this one.

The alternative to all of this is to contact the author for a licence. That is
a legitimate path and would preserve the world as it stands, but it makes a
public launch depend on a third party's answer, and the map generator would
still be wanted for contamination control.
