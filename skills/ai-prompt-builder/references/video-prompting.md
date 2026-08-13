# Single-Shot Video Prompting Reference

## The formula

`[Cinematography] + [Subject] + [Action] + [Context] + [Style & Ambiance] + [Audio]`

Order matters. Put cinematography first — it tells the model how to look at the scene before it knows what's in it.

---

## Cinematography (put this first)

This is the most powerful lever in video prompting. The camera framing tells the model the emotional relationship between viewer and subject.

### Shot types
| Shot | Use case |
|------|----------|
| Extreme wide shot | Establish scale, location, isolation |
| Wide shot | Full body in environment, context dominant |
| Medium shot | Waist up, conversational, balanced |
| Medium close-up | Chest up, emotional weight |
| Close-up | Face only, intimacy and intensity |
| Extreme close-up | Eyes, hands, texture — raw detail |
| Two-shot | Two characters in frame together |
| Over-the-shoulder | POV-adjacent, conversational |
| Low angle | Subject feels powerful, dominant |
| High angle | Subject feels small, vulnerable |
| Bird's eye | Abstract, architectural, detached |
| POV shot | First-person, immersive |

### Camera movements
| Movement | What it does |
|----------|-------------|
| Dolly in | Slowly approaches subject — builds intimacy or tension |
| Dolly out | Pulls away — reveals scale, creates distance |
| Tracking shot | Follows subject laterally — energy, momentum |
| Crane shot | Rises up or sweeps — reveals scale, epic feel |
| Aerial / drone | Overhead or descending — establishes location |
| Slow pan | Camera rotates slowly — scanning a scene |
| Whip pan | Fast rotation — disorient, transition, energy |
| Handheld | Organic, naturalistic, documentary feel |
| Steadicam / gimbal | Smooth follow — cinematic, controlled |
| Static / locked off | No movement — tension, focus, stillness |
| Dutch angle | Camera tilted — unease, instability |

### Lens language
- Shallow depth of field (f/1.4–f/2.8) — blurred background, subject isolated
- Deep focus (f/8–f/16) — front to back sharp, environment matters
- Wide-angle lens — environmental context, slight distortion at edges
- Telephoto / 200mm — compressed depth, subject feels close to background
- Macro — extreme detail, textures revealed
- Anamorphic — cinematic horizontal bokeh, lens flares

---

## Subject

Be specific. Name appearance, clothing, expression, age range, physique if relevant.

- Weak: "a man in a suit"
- Strong: "a tired corporate executive in his 50s, loosened tie, reading glasses pushed up on his forehead"

Describe **physical state**: posture, energy level, emotional register.

---

## Action

Describe what is physically happening. Be precise about:
- Movement speed: "walks briskly," "sprints at full pace," "moves in slow, deliberate steps"
- Direction: "moves toward camera," "turns away," "looks up"
- Physical detail: "rubs her temples," "slams the door," "reaches for the glass without looking"

Avoid vague verbs: "moves dynamically," "performs," "interacts with." These mean nothing to the model.

---

## Context

The environment, time of day, weather, and background.

- Set the scene before the action: "A cluttered 1980s office late at night"
- Layer atmosphere: "rain streaks the window behind him," "cigarette smoke drifts through harsh fluorescent light"
- Use real-world reference anchors: "a neon-lit Tokyo alleyway, 2 AM," "the floor of a packed NBA arena"

---

## Style & Ambiance

The visual DNA of the shot.

**Film stocks & cameras:**
- Shot on 16mm film, slightly underexposed, grain visible
- Fujifilm color science, warm and slightly faded
- Arri Alexa cinema quality, clinical and clean
- GoPro, immersive wide, slight fisheye

**Cinematic grades:**
- Muted teal and orange color grade
- High contrast, crushed blacks, cold highlights
- Golden hour warmth, amber glow
- Desaturated, bleak, flat tones

**Genre aesthetics:**
- Slow cinema, static, deliberate pace
- Music video aesthetic, stylized, lit for beauty
- Handheld documentary, available light, naturalistic
- 1970s thriller aesthetic, paranoid, dirty, grainy

---

## Audio (for models that support it: Veo 3.1, Kling 2.1)

Three types of audio to direct:

### Dialogue
Use quotation marks and attribution:
- `A woman says, "We have to leave now."`
- `The detective mutters, "Something doesn't add up."`
- `Voiceover: "This is where it all began."`

### Sound effects
Label explicitly with `SFX:`:
- `SFX: Thunder cracks in the distance, then rain begins.`
- `SFX: The door slams. A beat of silence. Then footsteps.`
- `SFX: The engine turns over once, twice, then catches.`

### Ambient / atmosphere
- `Ambient: The hum of a near-empty airport terminal.`
- `Ambient: Crowd noise muffled through thick glass.`
- `Ambient: Birdsong. Wind through tall grass. No other sound.`

**Tip:** If the model doesn't support audio natively, describe the ambient soundscape anyway — it shapes the model's sense of scene and can influence motion choices.

---

## Prompt examples

### Cinematic drama
```
Medium close-up with shallow depth of field, dolly slowly in. A tired corporate
worker in his late 40s, rubbing his temples in exhaustion, staring at the screen.
In front of a bulky 1980s computer in a cluttered office late at night. The scene
is lit by harsh fluorescent overhead lights and the green glow of the monochrome
monitor. Retro aesthetic, shot as if on 1980s color film, slightly grainy.
SFX: The hum of the fluorescent light. The quiet clatter of a keyboard in the
distance. He exhales slowly.
```

### Nature / epic
```
Crane shot starting low on a lone hiker and ascending high above, revealing they
are standing on the edge of a colossal, mist-filled canyon at sunrise. Epic
fantasy style. Awe-inspiring. Soft morning light, golden and diffused.
Shot on ARRI Alexa, cinematic grade. Amber and teal. Deep focus.
Ambient: Wind. The distant cry of a hawk. No music.
```

### Fashion / beauty
```
Tracking shot following the subject from behind. A young woman in a white linen
dress, moving through a crowded sunlit market. She moves at an easy, unhurried
pace. Mediterranean location, late morning. Handheld feel, naturalistic.
Shot on Fujifilm, warm color science, slightly overexposed highlights.
Ambient: Market noise, indistinct voices, the clang of metal.
```

### Dialogue scene
```
Medium two-shot. A detective and a woman face each other across a cluttered oak
desk, evening light slanting through venetian blinds. The detective looks up
slowly and says, "Of all the offices in this town, you had to walk into mine."
Film noir aesthetic. High contrast, deep shadows, warm practical light from a
single desk lamp. 35mm film look.
SFX: The creak of the chair. Street noise from below. A clock ticking.
```

---

## Platform-specific notes

### Veo 3.1
- Supports 4s, 6s, 8s clips
- Full audio: dialogue, SFX, ambient
- Use "ingredients to video" for character consistency across shots
- "First and last frame" for controlled transitions
- State target duration in prompt

### Kling 2.1
- 5–10s clips, strong physical simulation
- Use detailed action descriptions — it handles physics well
- Good character consistency on close-up faces

### Runway Gen-4
- Excellent motion quality, no native audio
- Works well with reference images for character anchoring

### Seedance 2.0
- Use the video-prompt-builder skill for effects-heavy Seedance work
- For simple single shots, this formula works fine

### Hailuo / MiniMax
- Strong stylized / cinematic aesthetic
- Good for art-directed beauty shots

---

## Duration guide

| Duration | Approach |
|----------|----------|
| 4s | One action, one reveal, or one held moment |
| 6s | Setup + action, or action + reaction |
| 8s | Mini arc: establish → action → resolution |
