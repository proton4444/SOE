---
name: ai-video-from-brief
description: >-
  Produce an entire finished talking-head video — script, voiceover, on-camera
  avatar, B-roll, motion-graphic cards, and final edit — from a single brief, with
  no camera, studio, or human editor. Use this whenever someone wants to generate a
  full long-form or explainer video with an AI avatar (HeyGen), a cloned voice
  (ElevenLabs), and generative B-roll (Higgsfield); asks to "make a video from a
  prompt/brief", reproduce an AI-made video, turn a script into an on-camera
  performance, drive a HeyGen avatar without it re-voicing with TTS, or assemble
  narrated avatar footage with B-roll and on-screen text using ffmpeg. Trigger even
  when the tools aren't named — any request to turn a brief into a finished,
  narrated, on-camera video belongs here.
---

# AI video from a brief

This skill turns a short brief into a finished, edited, on-camera video. Claude
plays the whole production team: it frames the video from the channel's own data,
writes the script, generates the voice, drives an avatar that looks like the
creator, produces the B-roll, and assembles the final cut with code. The only human
job left is taste — watching it back and asking for changes.

The mental model that makes this work: **you are handed a brief, not a script.** A
brief is the kind of thing you'd give a producer ("long-form, 16:9, ~5 minutes, work
out the framing from the audit, write the hook, walk through the process, invite
discussion, add B-roll and subtle animations"). Everything downstream is yours to
decide and execute.

## What you need

- **ElevenLabs** professional voice clone (a "pvc" — professional voice clone) of the
  narrator. This is the source of truth for the voice.
- **HeyGen** avatar (the creator's "digital twin"). It has a default look — for this
  creator, a red podcast studio. Learn the default and keep it.
- **Higgsfield** for generative B-roll, images, and motion (credits required).
- **ffmpeg** for all assembly.
- A **browser** (Claude in Chrome) to drive HeyGen and to download renders, and — in
  a cloud sandbox — the **device bridge** to move finished renders onto disk, because
  the sandbox cannot reach the vendors' CDNs directly.

Costs are real and mostly land on the avatar renders and the model's thinking. A
first full build runs roughly a hundred units of currency; once the workflow exists
and you're only re-rendering changed pieces, a rebuild is a fraction of that. Renders
**silently fail at zero credits** ("quota/credit limit"), so check the balance before
a batch.

## The pipeline

Break the job into stages, like a small production team would. Do them in order, but
keep everything **segmented** — one script segment, one voiceover file, one avatar
render per beat — because that is what makes the review loop cheap. When a note comes
back, you re-render one segment, not the whole video.

1. Frame it from the audit
2. Write the script, hook first
3. Voice each segment with the clone
4. Drive the avatar — without letting it re-voice
5. Generate the B-roll and images
6. Assemble with ffmpeg
7. Review, take notes, re-render only what changed

### 1. Frame it from the audit

Pull the channel audit and audience profile first so the framing isn't generic — how
this creator structures videos, who's watching, what their hooks look like. Settle the
format from the brief: length, aspect ratio (16:9 for long-form), and any required
beats (e.g. a sponsor read, an affiliate link in the description). Framing decisions
made here ripple through every later stage, so it's worth doing before a word is
written.

### 2. Write the script, hook first

Write the hook first, because that's how retention-driven videos are built, then the
body. A dependable long-form spine: **hook → setup → the actual prompt → behind the
scenes → what it cost → the honest/human part → what it means → over to you → sponsor →
watch-next CTA.** Write for the ear, in the narrator's voice, not for the page.

Two things to protect:

- **Continuity.** Don't let later lines contradict earlier ones (e.g. the hook saying
  "one review" while a later beat says "four rounds of reviews"). Read the whole script
  back for contradictions before generating any audio — fixing a line after it's voiced
  and rendered is expensive.
- **Segmentation.** Split the script into labelled segments (`01_hook`, `02_setup`,
  `03_prompt`, …). Every downstream artifact inherits these names. This is the single
  most important structural decision in the whole pipeline.

### 3. Voice each segment with the clone

Generate one mp3 per segment with the ElevenLabs professional clone, named to match
(`01_hook.mp3`, …). These files are the source of truth for both timing and voice —
the avatar will be lip-synced to them, and you'll later verify renders against them.
Keep them; you'll re-voice only the segments whose script changed.

### 4. Drive the avatar — without letting it re-voice (the crux)

This is where the pipeline most often silently breaks. **HeyGen re-voices the avatar
with its own TTS unless you force it to lip-sync to your uploaded clone audio.** There
is no single toggle. The procedure that works:

1. Get the mp3 into HeyGen's **Assets library first** (the Video Agent's attach menu
   pulls from Assets; it isn't a direct file upload). In a sandbox the Assets "Upload"
   button opens a native OS file dialog the browser tools can't drive — so have the user
   drag the file in, or upload it once manually. Programmatic file-input tricks report
   success but HeyGen ignores them.
2. In the **Video Agent**, open the "+" attach menu → Choose Assets → pick the mp3.
3. Submit a prompt that **names the file and forbids TTS**, e.g.:

   > "Create ONE 16:9 avatar video with my [Name] avatar, keeping my usual studio
   > background. Use the attached audio file `NN_segment.mp3` as the EXACT and ONLY
   > voice track — lip-sync the avatar precisely to this audio. Do NOT generate any
   > voice, do NOT use text-to-speech, do NOT rewrite anything: the attached audio IS
   > the narration."

4. **Confirm the success signal.** The agent should reply that it will use the provided
   audio "for the narration" / "lip-synced to your provided audio track." If it doesn't
   say something like that, it's about to TTS — stop and re-prompt.

Keep the avatar's **default look**. Asking for a different background ("clean dark
studio") makes HeyGen generate a *new* avatar appearance, which is slower and breaks
visual consistency with the rest of the video. To keep the default, just say "keep my
usual studio background" or say nothing about background at all.

**Downloading a HeyGen render:** use the Download button in the video header → Download
in the dialog (captions off) → it lands in the browser's Downloads. In a sandbox, then
stage that file into the workspace via the device bridge. (A fetch-blob-in-page download
is unreliable for HeyGen's player, which is often CORS-locked; use the native button.)

### 5. Generate the B-roll and images

Use Higgsfield for every B-roll shot, animation, and generated image. For anything that
should look like the creator, generate with a **face reference** for likeness
(`nano_banana_pro` or `soul_2` for one-off character refs; portrait aspect ratios crop
best into split-screens and vertical slots). Provide the reference through Higgsfield's
upload widget when a sandbox can't upload to it directly. Add motion either by
generating image→video, or — cheaper and reliable — with an ffmpeg slow push-in on a
still.

**Downloading Higgsfield results:** Higgsfield serves from CloudFront, which a sandbox
can't reach, but an in-page `fetch(url) → blob → anchor download` in the browser works
for it. Download to the device, then stage into the workspace.

### 6. Assemble with ffmpeg

Build one self-contained "part" per segment (avatar base + its overlays and cutaways),
then concatenate the parts. Working per-part keeps every edit local and every concat a
fast stream copy. Keep everything **1920×1080, 25fps, yuv420p** so parts concatenate
cleanly.

Normalize any source to the frame with:
`scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,fps=25`

Patterns that recur:

- **Title / lower-third cards:** a PNG overlaid with `enable='between(t,a,b)'` and
  alpha fades. A still PNG must be fed as a looped input (`-loop 1 -framerate 25 -t <dur>`)
  or it's a single frame and the overlay never shows — a classic silent failure.
- **Readable on-screen text over busy footage:** don't float thin text on the video.
  Lay a near-opaque full-frame scrim (`drawbox`/`rectangle` at ~0.8 alpha, colour near
  black) and centre serif text on it (white with one accent line). It reads cleanly
  where a bare overlay doesn't.
- **B-roll montage synced to the narration:** order the shots to match what's being
  said (say "the script" → show typing; "the voice" → a waveform; "the footage" →
  editing; "generated it" → code). Chain shots with `xfade` crossfades. A montage that
  merely looks busy feels disconnected; one whose shots track the words feels authored.
- **B-roll cutaways:** trim each cutaway to its **real motion length**. If you stretch a
  5-second clip to a 7-second slot it freezes on the last frame — a "hanging frame" that
  reads as a mistake. Add a gentle `zoompan` push-in so even a near-static shot has life.
- **Split-screen:** `zoompan` each half to 960×1080 with slightly different push rates,
  `hstack` them, and draw a thin divider line. Great for contrast beats (e.g. the AI
  working while the creator relaxes).
- **Concatenate** the finished parts with the concat demuxer and `-c copy`.

### 7. Review, take notes, re-render only what changed

This is the taste pass, and it's the part that's actually yours. Watch it back, and
expect it to take **about four rounds** — the pacing sags, a shot doesn't fit, a card is
hard to read. For each note, re-render or rebuild only the affected segment and re-concat;
because everything is segmented, a note costs one part, not the whole film. Keep going
until it earns a "great."

## Verify — because the failures are silent

The dangerous failures here don't error; they render something wrong. Guard against them:

- **Did the avatar actually use the right voice?** Cross-correlate the render's audio
  against the segment's source mp3. ~1.0 means it lip-synced to your clone; a near-zero
  score (≈0.03) means HeyGen re-voiced with TTS or used the wrong take — re-render. This
  one check catches the single most common and most invisible defect in the pipeline.
- **Look and lip-sync:** extract a few frames per render to confirm the right background
  and that the mouth is moving.
- **The joins:** after concatenating, re-check the intro and close audio against their
  sources so a bad segment can't hide inside the full file.
- **Durations:** confirm each part's length matches its voiceover.

A compact cross-correlation check (normalize both to 16 kHz mono first, then):

```python
import numpy as np, wave
def rd(p):
    w=wave.open(p,'rb'); a=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)
    a-=a.mean();  a/= (a.std() or 1);  return a
def corr(x,y):
    n=min(len(x),len(y)); x,y=x[:n],y[:n]
    d=(np.dot(x,x)*np.dot(y,y))**0.5
    return float(np.max(np.abs(np.correlate(x,y,'full')))/d) if d else 0
# corr(render_audio, source_mp3): ~1.0 good, ~0.03 = wrong voice / TTS
```

## Deliver

Deliver the finished **1080p master**. When pushing it onto the user's computer through
a size-limited bridge, split it into chunks, write the chunks over, reassemble on the
device (`cat part_* > final.mp4`), and verify by byte size **and** checksum against the
workspace copy so you know the reassembly is bit-for-bit correct. Also send a smaller
review copy into the chat for quick viewing, and short clips of any specific beat the
user asked about.

## Gotchas, in one place

- HeyGen re-voices with TTS unless you attach the mp3 from Assets *and* forbid TTS in the
  prompt; wait for the "using your audio" confirmation.
- Naming a new background regenerates the avatar's whole look — keep the default.
- Renders fail silently at zero credits — check the balance before a batch.
- Sandboxes can't reach vendor CDNs — download in the browser (native button for HeyGen,
  fetch-blob for Higgsfield's CloudFront), then stage to the workspace.
- A still PNG overlay needs a looped input with a duration, or it never appears.
- Stretching a short cutaway past its length freezes the frame — trim to real motion and
  add a slow push-in.
- Segment everything: it's what makes the four-round review loop affordable.
