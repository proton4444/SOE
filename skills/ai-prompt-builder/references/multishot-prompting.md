# Multi-Shot Video Prompting Reference

Multi-shot prompting builds a complete, directed scene — not just one clip, but a sequence of shots with consistent characters, directed pacing, and a coherent audio landscape.

Use this for:
- Timestamp prompting (Veo 3.1 native format)
- Shot lists for Kling, Runway, Hailuo scene planning
- Director's packages to guide manual generation across multiple clips
- Storyboards for AI video ads, brand films, short films

---

## Output: Four sections

Always produce all four sections. Never skip one.

---

## Section 1: Scene Header

Before any shots, establish the scene context. This is the brief a director would hand to their DP.

```
SCENE: [Name or short description]
TONE: [2–3 words: cinematic / melancholic / kinetic / tense / playful / etc.]
DURATION TARGET: [total seconds or minutes]
PLATFORM: [Veo 3.1 / Kling / Runway / multi-platform / unknown]

CHARACTERS:
- [Character A]: [Physical description, clothing, key traits — 2 sentences max]
- [Character B]: [Same]

SETTING: [Location, time of day, weather, atmosphere]

AUDIO CONCEPT: [Music style or cue. Tone of dialogue if any. Key SFX moments.]
```

---

## Section 2: Shot Sequence (Timestamp Format)

This is the core of the output.

**Format for each shot:**
```
[START:END] SHOT TYPE — Brief label
Camera: [movement + framing]
Action: [precise physical description of what happens]
Subject: [who/what is on screen, and their state]
Context: [environment detail relevant to this shot]
Audio: [dialogue in quotes / SFX label / ambient note]
```

**Example:**
```
[00:00–00:02] WIDE ESTABLISHING — Temple entrance revealed
Camera: Static wide shot, slightly elevated
Action: Explorer pushes aside dense jungle vines to reveal a hidden stone path
Subject: Young female explorer, leather satchel, messy brown ponytail, cautious stance
Context: Dense tropical jungle, midday light filtered through canopy
Audio: SFX: Rustle of leaves, distant exotic bird calls, insects

[00:02–00:04] REVERSE MEDIUM CLOSE-UP — Awe on her face
Camera: Reverse shot, medium close-up, soft depth of field
Action: Explorer gazes at the ruins ahead, expression shifting from caution to wonder
Subject: Same explorer, freckled face, eyes wide
Context: Ancient moss-covered ruins visible soft-focus in background
Audio: SFX: The jungle quiets slightly. Wind.

[00:04–00:06] TRACKING SHOT — Moving into the ruins
Camera: Tracking shot, slightly low angle, follows from behind
Action: Explorer steps forward into the clearing, reaches out and touches stone carvings
Subject: Explorer from behind, hand trailing along carved stone surface
Context: Crumbling stone walls with intricate carvings, dappled light
Audio: Ambient: A low, resonant hum — almost musical. Reverb.

[00:06–00:08] WIDE CRANE SHOT — Scale revealed ★ HERO SHOT
Camera: High-angle crane shot, ascending from behind explorer
Action: Camera rises to reveal the vast temple complex around her
Subject: Explorer seen small in center of enormous overgrown temple courtyard
Context: Temple ruins half-reclaimed by jungle, golden light hitting stone
Audio: SFX: A swelling orchestral score begins, soft and reverent
```

**Rules for the shot sequence:**

1. **Vary shot types deliberately.** Don't repeat the same shot type consecutively unless it's for rhythmic effect. Use the full range: wide → medium → close → overhead.

2. **Mark the HERO SHOT.** Every sequence needs one. Mark it with ★ in the label. This is the most visually impactful moment — often the reveal, the peak emotion, or the signature visual.

3. **Transitions live between shots.** Describe the exit of each shot and the entry of the next when relevant. Cut, dissolve, whip pan, match cut, smash cut — state it if it matters.

4. **Audio continuity.** The soundscape should develop across the sequence. Music that starts in shot 4 should still be there in shot 6. Ambient layers should shift as the scene changes.

5. **Character state must be consistent.** Clothing, appearance, and emotional arc need to track. Note changes explicitly ("she has now removed her jacket").

6. **Ingredients language.** When using Veo's "ingredients to video" or any reference-based generation: flag which shots share characters and what reference images should anchor them.

---

## Section 3: Audio Map

A timeline view of the audio across the full sequence.

```
AUDIO MAP

[00:00–00:02] SFX: Jungle ambience — insects, birds, rustling
[00:02–00:04] SFX: Quiet settles. Wind. Distant echo.
[00:04–00:06] AMBIENT: Low resonant hum, mysterious, grows slightly
[00:06–00:08] MUSIC: Orchestral swell begins — strings, soft and building

DIALOGUE:
- None in this sequence (or list lines and timestamps)

KEY SFX MOMENTS:
- 00:03 — Sudden silence as explorer steps out of jungle. Disorienting.
- 00:07 — First music note drops as crane shot peaks.
```

**Audio map rules:**
- Every shot should have an audio line
- Note **music cue start points** — when does the score begin/end?
- **Dialogue lines** get their own block, clearly timestamped
- Flag **audio discontinuities** (a scene that goes silent, a cutaway with different ambient)

---

## Section 4: Director's Notes

Practical guidance for the person who will generate these clips.

```
DIRECTOR'S NOTES

GENERATION ORDER: [Which shots to generate first and why]
  → Generate Shot 1 (establishing wide) first — it defines the location aesthetic
    all other shots should match.
  → Shot 4 (hero crane shot) may require multiple generations — it's the most
    compositionally demanding.

INGREDIENT IMAGES NEEDED:
  → Character: Explorer — generate a reference still using Nano Banana /
    Gemini Image first. Use: brown hair in ponytail, leather satchel, khaki
    explorer outfit. Use this still as the "ingredient" for Shots 1, 2, 3.
  → Setting: Temple exterior — generate a reference still of moss-covered
    stone ruins, tropical jungle setting.

ITERATION TIPS:
  → If Shot 3 (tracking) loses character consistency, try image-to-video
    instead, using the Character reference still as the first frame.
  → For Shot 4, use "first frame" as Shot 3's final frame for continuity.

CONSISTENCY FLAGS:
  → Explorer's clothing must remain identical across all shots.
  → Time of day is continuous (midday) — light quality should match.

OPTIONAL EXTENSIONS:
  → After Shot 4, a close-up of the stone carving detail would extend to 10s.
  → A final audio sting (SFX: temple bell) would punctuate the crane shot.
```

---

## Timestamp formatting guide

### Veo 3.1 native format
Veo 3.1 supports timestamp prompting directly. Use this exact structure:

```
[00:00-00:02] Wide shot of the explorer pushing through jungle vines. SFX: Rustling leaves.
[00:02-00:04] Reverse shot. Her face fills the frame with awe. Ambient: Wind.
[00:04-00:06] Tracking shot behind her as she enters the clearing. Ambient: Low hum.
[00:06-00:08] Wide high-angle crane shot. The temple complex revealed. Music: Strings swell.
```

Each segment can be 2–4 seconds. Total sequence up to 8 seconds in a single generation.

### Manual multi-clip format (Kling / Runway / Seedance)
For platforms without native timestamp support, each shot becomes a separate prompt:

**Shot 1 of 4:**
```
Wide static shot. A young female explorer in khaki, leather satchel, brown
hair in ponytail, pushes aside jungle vines to reveal a hidden stone path.
Dense tropical jungle, midday light through canopy. SFX: Rustling, birds.
4 seconds.
```

Then repeat for each shot, noting "match color grade to Shot 1" for consistency.

---

## Sequence length guide

| Duration | Shots | Structure |
|----------|-------|-----------|
| 8–10s | 3–4 shots | One scene beat, single location |
| 15–20s | 5–7 shots | Mini arc: setup → development → peak |
| 30s | 8–12 shots | Full arc: establish → escalate → resolve |
| 60s+ | 14–20 shots | Multi-beat: acts with distinct emotional phases |

---

## Common multi-shot patterns

### The Reveal
Wide → Medium → Close-up → Wide (inverted)
Opens broad, pulls in for detail, then zooms back out to show scale.

### The Chase / Build
Static → Tracking → Handheld → Aerial
Energy escalates through camera movement, not editing.

### Dialogue scene (Veo 3.1 "Ingredients to Video")
Step 1: Generate character reference stills for each person + setting.
Step 2: Shot A — Medium shot of Character A speaking.
Step 3: Shot B — Reverse shot of Character B responding.
Step 4: Return shot — Back to Character A with reaction.

### The Music Video arc
Hook visual → Verse build → Pre-chorus ramp → Chorus hero shot → Breakdown → Final hit
Each section has distinct camera language and density.

---

## Example: Dialogue scene (Veo 3.1 Ingredients to Video)

```
SCENE: Detective office — noir dialogue
TONE: Tense, world-weary, mysterious
DURATION TARGET: 15 seconds
PLATFORM: Veo 3.1

CHARACTERS:
- Detective: Male, 50s, rumpled grey suit, loosened tie, hollow eyes
- The Woman: Female, 30s, dark coat, poised, expression controlled

SETTING: Cluttered detective's office, evening, venetian blind shadows, desk lamp

AUDIO CONCEPT: Near silence. Room tone. Subtle jazz from a distant radio.

---

[00:00–00:03] MEDIUM SHOT — Detective at desk
Camera: Medium shot, slightly low angle, static
Action: Detective looks up slowly from a manila folder
Subject: Detective behind oak desk, practical lamp lighting one side of his face
Audio: SFX: The scratch of paper. A clock ticking. He says, "Of all the offices
in this town, you had to walk into mine."

[00:03–00:07] MEDIUM CLOSE-UP — Woman's response
Camera: Reverse medium close-up, slightly high angle
Action: A slight, controlled smile crosses her face
Subject: The Woman, standing, coat still on, composure unbroken
Audio: She says, quietly, "You were highly recommended." Beat. She doesn't move.

[00:07–00:11] TWO-SHOT — Standoff
Camera: Wide two-shot from side, both in frame
Action: Neither moves. The detective leans back slightly. She watches him.
Audio: SFX: Distant jazz radio, muffled. Clock. Silence between them is loaded.

[00:11–00:15] CLOSE-UP — Detective's eyes ★ HERO SHOT
Camera: Extreme close-up on the detective's eyes, slightly handheld
Action: He holds her gaze, something shifts — decision made
Audio: SFX: He says, slowly, "Sit down." The jazz cuts out.
```
