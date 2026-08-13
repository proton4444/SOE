---
name: ai-prompt-builder
description: Generate high-quality AI prompts for image generation, single-shot video, and multi-shot video sequences. Use this skill whenever the user wants to write a prompt for any AI image or video tool — Midjourney, Flux, Stable Diffusion, Firefly, Veo, Kling, Runway, Seedance, Sora, Hailuo, or any other generator. Trigger on phrases like "write me a prompt", "image prompt", "video prompt", "multi-shot sequence", "shot list", "scene breakdown", "timestamp prompting", "storyboard prompts", "ingredients to video", "first and last frame", or any time the user describes what they want to see and needs it translated into generation-ready instructions. Also trigger when the user describes a vibe, visual style, character, or scenario and seems to want an image or video — even if they haven't said "write a prompt" explicitly.
---

# AI Prompt Builder

Three prompt types. One skill. Choose based on what the user needs:

| Mode | When to use |
|------|-------------|
| **IMAGE** | Still image generation — Midjourney, Flux, Nano Banana, Firefly, DALL·E, etc. |
| **VIDEO (single shot)** | One continuous clip — Veo, Kling, Runway, Seedance, Hailuo, Sora, etc. |
| **MULTI-SHOT VIDEO** | Timestamp-structured sequence / scene breakdown / storyboard for video |

If the user hasn't specified a mode, infer from context. If still unclear, ask one focused question.

---

## MODE 1: IMAGE PROMPTS

Read `references/image-prompting.md` before writing image prompts.

**Core formula:**
`[Subject + Action] + [Location / Context] + [Composition] + [Lighting] + [Style / Aesthetic] + [Camera / Lens] + [Color grading]`

**Key principles:**
- Lead with the subject. Make the first sentence count.
- Use positive framing. Describe what IS there, not what isn't.
- Specify lighting explicitly — it sets the emotional tone.
- Use camera and lens language to control depth and framing.
- Define materiality and texture for objects, clothing, environments.
- Enclose desired text in quotes and specify font style if needed.
- End with a style signature: film stock, art movement, render style, or medium.

**Output format:**
- One clean prompt block, ready to paste
- Optional: brief note on what can be iterated (aspect ratio, lighting, style variant)
- If the request has multiple interpretations, offer 2 versions

---

## MODE 2: SINGLE-SHOT VIDEO PROMPTS

Read `references/video-prompting.md` before writing video prompts.

**Core formula:**
`[Cinematography] + [Subject] + [Action] + [Context] + [Style & Ambiance] + [Audio]`

**Key principles:**
- Open with the shot type and camera move — this is the most powerful lever.
- Be specific about camera movement: dolly, tracking, crane, aerial, pan, POV.
- Describe action with clear physical specificity — not "moves dynamically" but "runs at full sprint, arms pumping."
- Use lens language: shallow depth of field (f/1.8), wide-angle, macro, soft focus.
- Include audio direction for models that support it (Veo 3.1, Kling 2.1): dialogue in quotes, SFX with label, ambient noise description.
- Define color grade and film aesthetic.
- Keep clips to 4–8 seconds for best results; state target duration.

**Output format:**
- One clean prompt block
- Suggested duration (4s / 6s / 8s)
- Note on which platform it's optimized for (if user specified)

---

## MODE 3: MULTI-SHOT VIDEO PROMPTS

Read `references/multishot-prompting.md` before writing multi-shot sequences.

This mode builds a complete, timestamped video sequence — multiple shots, consistent characters, directed pacing — for use with Veo 3.1 timestamp prompting, Kling scene planning, Runway multi-shot, or as a director's shot list for any AI video tool.

**Core structure — timestamp format:**
```
[00:00–00:02] Shot description. Camera: ___. Action: ___. Audio: ___.
[00:02–00:05] Shot description. Camera: ___. Action: ___. Audio: ___.
...
```

**Key principles:**
- Each timestamp block = one distinct shot
- Vary shot types: establish → medium → close-up → wide → etc.
- Plan audio across the sequence: dialogue, SFX, ambient, music cues
- Flag the HERO SHOT (the most visually impactful moment in the sequence)
- Include a brief scene header with: character descriptions, setting, tone, target duration
- Use "ingredients" language when referencing consistent characters across shots

**Output format:**
Four sections (see `references/multishot-prompting.md` for full detail):
1. **Scene Header** — context, characters, tone, duration target
2. **Shot Sequence** — timestamped shot-by-shot blocks
3. **Audio Map** — music cues, SFX moments, dialogue lines across timeline
4. **Director's Notes** — which shots to generate first, dependency order, iteration tips

---

## Platform Reference

| Platform | Shot duration | Audio | Multi-shot native | Notes |
|----------|--------------|-------|-------------------|-------|
| Veo 3.1 | 4–8s | ✅ Full | Timestamp format | Strongest audio. Use ingredients-to-video for consistency. |
| Kling 2.1 | 5–10s | ✅ Partial | Scene planning | Strong character consistency |
| Runway Gen-4 | 5–10s | ❌ | Manual | Excellent motion quality |
| Seedance 2.0 | 4–8s | ❌ | Manual | Use video-prompt-builder skill for effects-heavy work |
| Hailuo | 6s | ❌ | Manual | Great for stylized/cinematic |
| Sora | Up to 20s | ❌ | Storyboard mode | Good for longer single shots |

---

## Quick decision guide

```
User says "write me a prompt for [IMAGE TOOL]"  →  Mode 1
User says "write me a video prompt" (one scene)  →  Mode 2
User says "multi-shot", "scene breakdown", "storyboard", "sequence"  →  Mode 3
User describes a story or narrative arc  →  Mode 3
User describes a single moment or visual  →  Mode 1 or 2 (ask if unclear)
```

If the request is vague, ask ONE question: "Is this for an image or a video — and roughly how long should it be?"
