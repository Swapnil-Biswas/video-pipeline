# HireCrew video production: reverse-engineering report

This report covers the video work in Claude Code session `01cacffb-eeb3-4040-86f8-c5a0f386f346`, held in `C:\Users\swapn\OneDrive\Desktop\HireCrew` from 2026-10-29 to 2026-11-05. The main subject is the **final video**: `video-showreel/renders/hirecrew_showreel_4k60.mp4`. The earlier videos from the same session are listed too, because the showreel reuses their tools, assets and lessons.

**Sources.** Everything here comes from three places:

1. The session transcript, `C:\Users\swapn\.claude\projects\C--Users-swapn-OneDrive-Desktop-HireCrew\01cacffb-….jsonl`. It holds 3,921 records, 254 Bash calls, 24 PowerShell calls and 81 file writes. I extracted every user message and every shell command from it.
2. The files on disk: project folders, scripts and renders.
3. The `ffprobe` / `ebur128` measurements of the renders.

Two other transcripts in the same folder belong to unrelated work: `470b2c36…` is the website build and `752b4ebf…` is the "laya" model setup. They are left out except where noted.

**Markers used below.**

- **[C] Confirmed:** seen in the transcript or on disk.
- **[I] Inferred:** a reasonable reading of the evidence, not shown directly.
- **[U] Unknown:** not recoverable.

---

## 1. Executive summary

- **What was made.** The final video is a 28-second, 3840×2160, 60 fps motion-graphics showreel for HireCrew [C]. HireCrew is a marketplace where you hire AI agents and pay only when the work is accepted.
- **No camera footage.** The video has no filmed or AI-generated footage [C]. Every pixel is HTML/CSS drawn by Claude, animated with GSAP and rendered frame by frame with **HyperFrames**, HeyGen's open-source HTML-to-video renderer.
- **Music.** The bed is an original track generated locally with **Meta MusicGen** (`facebook/musicgen-stereo-medium`, via Hugging Face `transformers` on the RTX 4050). It was then tempo-stretched, arranged and mastered with `librosa`, `numpy`, `soundfile` and **FFmpeg** [C].
- **Sound effects.** They come from the SFX library bundled with the HyperFrames `media-use` skill, placed by a cue script [C].
- **Editing style.** It was copied from a reference Instagram reel by "Aiden | Motion Designer" (https://www.instagram.com/reel/Dd7LoTKSsbT/). The reel was downloaded with **yt-dlp**, then studied through contact sheets, scene-cut detection and a librosa tempo/onset/spectrum analysis [C]. The content and script are original to HireCrew [C].
- **Who did what.** Claude did all the creative and technical work through shell commands. The user gave direction, gave approvals and pointed out glitches, in four rounds [C].
- **Delivery format.** The render used the NVIDIA GPU: Chrome capture ran on the RTX 4050 through a per-app Windows GPU preference, and encoding used `--gpu`. Audio was mastered to −14 LUFS / −1.5 dBTP with two-pass `loudnorm` [C].
- **The pipeline.** The production method has been rebuilt as an executable pipeline, `reelforge`, in `video-pipeline/`. Section 10 and the README explain it.

---

## 2. Chronological production workflow

### 2.0 Context: everything made in this session [C]

| # | Date | User request (short) | Output |
|---|---|---|---|
| 1 | 10-29 | "setup hyperframes so we can use to edit videos" | HyperFrames working; FFmpeg installed via winget |
| 2 | 10-29 | Edit a HireCrew video in the style of two YouTube videos | `video/` 76 s landscape launch film, MusicGen music |
| 3 | 10-29 | Small subtitles, human female voice, eye-catching first 5 s | `video/` v2 with HeyGen voice "Joelle" and word-synced captions |
| 4 | 10-29 | "use nvidia gpu for rendering no ..... why use igpu?" | GPU preference registry fix and `--gpu` |
| 5 | 10-29 | Portrait version for the website | `video-portrait/` |
| 6 | 10-29 | 15 s Instagram reel | `video-reel/` `hirecrew_reel_15s.mp4` |
| 7 | 10-29 | Hindi voice-over with English subtitles, 17 s, vibe-coder hook | `video-reel-hi/` `hirecrew_reel_hindi.mp4` |
| 8 | 10-30 | Sponsor/creator pitch ad (10% lifetime commission, 60% off) | `video-sponsor/` (last render interrupted by the user) |
| 9 | 10-30/31 | Instagram caption (no emojis), X description | Text only |
| 10 | 11-04 | **Showreel in the style of the Instagram reel** | `video-showreel/` v1 |
| 11 | 11-04 | "alignment out of place" (logo tile) | Logo trimmed and centred |
| 12 | 11-05 | "multiple glitches … closely copy the editing style … production level" | **Final v2 render** |

### Stage 1: Initial input and requirements [C]

- **Prompt.** The full text is in the prompt library, P10.
- **Inputs.**
  - The reference reel URL.
  - Brand source: `C:\Users\swapn\OneDrive\Desktop\HireCrew B&W\frontend`, the black-and-white claymorphism website, already mined for the first video.
  - Assets carried over from `video/`: Instrument Sans fonts, HireCrew logo/icon PNGs, and SFX files.
- **Constraints from earlier turns.**
  - Use the NVIDIA GPU.
  - No emojis (this was about captions).
  - Keep the content original and copy only the editing style.
  - "take as much time as u need … make it studio grade".

### Stage 2: Reference analysis [C]

Inputs: the reel URL. Outputs: `scratchpad/ref2/ref.mp4`, `ref.info.json`, `sheet1.jpg`, `s1.jpg`, `s2.jpg`, `ref.wav`.

1. **Download the reel:**
   ```bash
   python -m yt_dlp -q -o "ref.%(ext)s" --write-info-json "https://www.instagram.com/reel/Dd7LoTKSsbT/"
   ```
2. **Probe it.** `ffprobe` reported 1916×1078 at 60 fps, about 27 s long.
3. **Detect scene cuts:**
   ```bash
   ffmpeg -i ref.mp4 -vf "select='gt(scene,0.25)',showinfo" -an -f null -
   ```
4. **Build contact sheets.** One at 2 fps (`fps=2,scale=400:-1,tile=6x10`), then two at 4 fps (`fps=4,scale=320:-1,tile=6x9`, split at 13.5 s).
5. **Analyse the music.** The audio was extracted with `ffmpeg -vn -ac 1 -ar 22050 ref.wav`, then analysed with librosa:
   - `beat_track` gave the tempo (about 123 BPM).
   - RMS was taken per 0.5 s.
   - `onset_detect(delta=0.3)` found 26 strong onsets.
   - Energy was measured in four bands: 20–150, 150–1k, 1k–4k and 4k–11k Hz.
6. **Read the frames.** Claude viewed the sheets and wrote down the grammar:
   - A dark chat with depth-of-field bubbles, typing dots and a funny payoff reply.
   - Then a montage that changes world every 1–2 s: a white kinetic title with floating icons, a dark AI prompt box clicked by a cursor, choice cards with buttons, a UI zoom, a giant word behind a stat donut, kinetic two-tone lines, and a closing name reveal typed out.
   - Mix: bright mids and highs, a quieter intro, the drop at about 9–10 s.
7. **Second pass on 11-05.** For the glitch-fix round, 4 fps contact sheets were rebuilt in four 7 s chunks (`fps=4,scale=480:-1,tile=4x7`). This pass found what v1 had missed:
   - The reference opens with an **extreme close-up camera that tracks each message**.
   - It pulls **out wide** for the punchline.
   - It **punches in** on the payoff.
   - It ends on black.

### Stage 3: Creative direction [C]

- **Story.** "Old AI agent says *Done!* but the sheet is empty → bro." Then "HireCrew agent delivers, proves it, payment is held → BRO IT ACTUALLY WORKED." Then a montage of the product mechanics, ending on "This is [HireCrew logo]".
- **Look.** The HireCrew black-and-white claymorphism. Each scene alternates between a dark world and a light world, with Instrument Sans 400–700.
- **Format.** 16:9 at 1920×1080 CSS pixels, rendered at 4K. 60 fps because the reference is 60 fps. Motion blur on.

### Stage 4: Script and storyboard [C]

These are the final values from `video-showreel/index.html`.

| # | Scene (composition) | Start s | Length s | World | Content |
|---|---|---|---|---|---|
| 1 | `chat` | 0.0 | 9.0 | dark | Old agent: "Can you put my invoice emails in a Sheet?" / "Done!" / "the sheet is empty..." / "Done!" / "bro." Then HireCrew agent: "Job delivered: 3 rows added to your Sheet.", an evidence mini-sheet, "Payment is held until you accept.", "BRO IT ACTUALLY WORKED" |
| 2 | `title` | 9.0 | 1.6 | light | "Hire AI agents." / "Pay only for" / pill "finished work." with floating icon tiles |
| 3 | `order` | 10.6 | 1.8 | dark | HC icon, "What should your crew do?", typed "Every invoice email → a row in my Sheet", chips, cursor clicks send, camera dives into the button |
| 4 | `held` | 12.4 | 1.4 | light | "Your money waits.", $5.00 checkout card, coin drops in, "Held" chip |
| 5 | `gate` | 13.8 | 1.4 | dark | "Every step checked.", gmail.search / sheets.append allowed, gmail.send stamped BLOCKED |
| 6 | `sheet` | 15.2 | 1.6 | light | "Verified in your apps.", 3-row sheet, "Read back" chip |
| 7 | `choice` | 16.8 | 1.6 | light | "Inbox-to-Sheet · delivered", Dispute · refund / Accept · pay, cursor hovers then accepts, "Released" |
| 8 | `paid` | 18.4 | 2.0 | light | Giant grey PAID behind a card, ring 0→100% "Job accepted", "You pay for results." |
| 9 | `crew` | 20.4 | 2.0 | dark | "Or hire a crew.", $20 hard cap meter, Research $4 Released / Copy $3 Held / Test pack failed $2.50 Refunded |
| 10 | `end` | 22.4 | 5.6 | light | "This is" typed with a caret, logo tile lands, "Pay only for finished work.", "Join HireCrew →" clicked, fade to black |

### Stage 5: AI image/video generation [C]

**None.** No image or video model was used. No stock footage was used.

### Stage 6: Voice-over and audio production

**Voice-over: none for the showreel [C].**

The earlier videos used HeyGen TTS through the `media-use` skill script. These details are kept for reuse:

- **Command:**
  ```bash
  node ~/.claude/skills/media-use/audio/scripts/heygen-tts.mjs "<text>" --voice <id> [--lang hi] [--speed 1.1] -o line.wav --words line.words.json
  ```
- **Sign-in:** `npx hyperframes auth login`.
- **Voices:** English "Joelle" `dff185982cf84b91a246dace28badb71`; Hindi voice `1bd41839492f4f22b97f1a6678aded7b`. The transcript names this voice "Aahana Verma" [C].
- **Assembly.** The reel voice track was put together by `video-reel/tools/vo_reel.py`:
  - Each line is sped up with `atempo` 1.15 and trimmed to its words, with 10 ms edge fades.
  - The chain is `highpass 85, eq 250 −2, eq 3200 +2.5, highshelf 9k +1.5, acompressor 3:1, loudnorm I=−16 TP=−2`.
  - Word timings are written to `words.json`.

**Music [C].**

- **Earlier film.** `scratchpad/music/gen.py` generated one 90 s track with `facebook/musicgen-medium`, using 30 s windows and 10 s audio continuation.
- **Showreel generation.** `batch_reel2.py` made six independent 30 s takes:
  - Model `facebook/musicgen-stereo-medium`, fp16 on CUDA.
  - `guidance_scale=3.5`, `max_new_tokens=1500`.
  - Seeds 101, 202, 303, 404, 505, 606, alternating between two prompts (P-M3 and P-M4).
- **Choosing a take.** Takes were scored objectively with `score.py`: tempo stability, beat regularity, dropout share, 5 s energy spread, band share against the reference, onsets per minute and peak.
  - Take 303 was used first and rejected: it had a near-silent hole at 9–15 s.
  - **Take `clip_musicgen-stereo-medium_404_p1.wav` was used.**
- **Arranging.** `video-showreel/tools/music.py`:
  - Stretches the take to 124 BPM with `atempo` (pitch kept).
  - Picks the start offset so that a strong beat lands exactly on the 9.0 s drop.
  - Low-passes the intro: 700 Hz, ×0.62, opening to 3 kHz over the last bar.
  - Plays full-band from 9.0 s and pads to 28 s.
  - Masters with: `highpass 45, lowshelf 140 −7, eq 380 +2, eq 2600 +4, highshelf 8000 +3.5, acompressor 2.2:1, alimiter 0.9, fade in 0.08 / out 2 s, loudnorm I=−14 TP=−1.5 LRA=8`.
  - Output: `assets/music/bed.wav`.

### Stage 7: Editing and compositing [C]

- **Project layout.** `video-showreel/` was created by copying fonts, brand files and SFX from `video/`.
- **Root file.** `index.html` holds:
  - The shared head CSS: brand tokens and the `.clay`, `.chip`, `.state`, `.btn`, `.tick`, `.cursor` and `.sheet` classes, plus the showreel world classes.
  - Ten scene hosts (`data-composition-src`, `data-start`, `data-duration`, `data-track-index="1"`).
  - The root: `data-duration="28" data-width="1920" data-height="1080" data-fps="60" data-motion-blur="on"`.
- **Scenes.** Each scene is `compositions/<id>.html`: a `<template>` with scoped CSS, DOM, and a paused GSAP timeline registered as `window.__timelines[id]`.
- **Checking frames.** `npx hyperframes snapshot --at t1,t2,… [--no-end] -o dir` produced the stills and contact sheets that Claude reviewed. `npx hyperframes check` ran lint and layout checks.

### Stage 8: Transitions, effects and animation [C]

- **Scene entries.** Blur-whip and push entries: `x` ±1000–1800 px or `y` 1200 with `filter: blur(22px)` easing to 0 over 0.3 s, `expo.out`.
- **Scene exits.** Whip with blur, `power3.in`, 0.2–0.24 s, or scale-and-blur dissolve.
- **Chat camera (v2).** A camera rig with `transform-origin 0 0`. `at(px,py,s) = {x: 960 − s·px, y: 540 − s·py, scale: s}` puts any point at the centre of the frame.
  - Close-ups at 1.6–1.85×.
  - A wide shot at 1.0× for "bro.".
  - A `power4.inOut` swipe to the second chat.
  - A punch-in to 1.5× with screen shake on the payoff.
  - A zoom-through to 10× with a white flash into the title.
- **Zoom-through into a button.** `order`: scale 26 around the send button, then a flash.
- **Kinetic type.** Words fade in from `blur(10–14px)` with a 0.06–0.1 s stagger. The accent word sits in a clay pill (`.acc`) and pops with `back.out(2.2–2.4)`.
- **Micro-interactions.**
  - The cursor moves with `power3.out` and clicks with a 0.07 s yoyo press.
  - Button fill uses `scaleX`.
  - The stamp slams in from scale 2.6 with `power4.in`, followed by screen shake.
  - The coin drops with `bounce.out`.
  - Counters (ring percentage, budget used) are tweened values written into text.
- **Depth.** Out-of-focus foreground blobs (radial gradients) drift across the frame. The dot grid shows parallax. Vignette and glow add light.
- **Motion blur.** HyperFrames page motion blur is on (`data-motion-blur="on"`; the render log says "movers=65").

### Stage 9: Sound design and synchronisation [C]

`video-showreel/tools/audio.py` writes the `<!-- AUDIO -->` block.

- **Music track.** `bed.wav` at `data-volume 0.85`, with a volume automation lane. It ducks to 0.4 for 0.1 s at each cursor click: 11.9, 17.94 and 25.72 s.
- **79 SFX cues** (file, picture time, volume). Each cue starts at `picture_time + 1/60 − PEAK[file]`, so the sound's peak lands one frame after the picture event. PEAK values were measured with `npx hyperframes audio <file> --json`.
- **Lanes.** Cues are packed greedily into non-overlapping lanes (track index 11+).
- **Files.** The SFX are copies of the `media-use` bundled library: click, click-soft, click-lo, pop, pop-hi, pop-lo, whoosh, whoosh-short, whoosh-hi, whoosh-lo, whoosh-cinematic, impact-bass-1/2, stamp, key-press, typing, ping, glitch-3. The `-hi/-lo` variants and `stamp` were derived in an earlier stage, outside this showreel [I].

### Stage 10: Rendering and export [C]

1. **GPU preference** (once, and again whenever HyperFrames downloads a new Chrome). Set `HKCU\Software\Microsoft\DirectX\UserGpuPreferences` → `<chrome-headless-shell.exe path>` = `GpuPreference=2;`.
2. **Render:**
   ```bash
   npx hyperframes render --quality delivery --resolution landscape-4k --fps 60 --gpu -o renders/showreel_raw.mp4 --quiet
   ```
   The log confirmed `ANGLE (NVIDIA, NVIDIA GeForce RTX 4050 Laptop GPU …)`.
3. **Master, pass 1:** `loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json` to measure.
4. **Master, pass 2:** `loudnorm` with the measured values and `linear=true`, then `alimiter=limit=0.84:level=false`, AAC 320k at 48 kHz, `-c:v copy -movflags +faststart`.
5. **Verify.** `ebur128=peak=true` gave I = −14.0 LUFS and peak −1.5 dBFS. `ffprobe` gave h264 3840×2160 at 60/1, 28.000 s. Claude then re-read the render as 4 fps contact sheets.
6. **Thumbnail:** `ffmpeg -ss 7.9 -frames:v 1 -vf scale=1280:-1 hirecrew_showreel_thumb.jpg`.

---

## 3. Tool and technology inventory

| Tool | Website | Purpose / how used | Input → output | Settings | Status |
|---|---|---|---|---|---|
| Claude Code (desktop app), Claude Opus | https://claude.com/claude-code | Planned, wrote all HTML/CSS/JS/Python, ran every command, reviewed frames visually | Prompts → files and commands | Model per session | [C] used |
| HyperFrames CLI (`hyperframes` npm, 0.8.21x → 0.9.10 → 0.9.15) | https://github.com/heygen-com/hyperframes | HTML→video: `check`, `snapshot`, `render`, `audio --json` (SFX peak/LUFS), `auth login` | HTML project → PNG/MP4 | `--quality delivery --resolution landscape-4k --fps 60 --gpu` | [C] used |
| HyperFrames skills (`hyperframes`, `hyperframes-cli`, `media-use`) | Installed under `~/.claude/skills` | Authoring rules, bundled SFX library, `heygen-tts.mjs` | — | — | [C] used |
| GSAP 3.14.2 (CDN) | https://gsap.com | Every animation timeline | — | Paused timelines | [C] used |
| Headless Chrome (chrome-headless-shell 152) | https://developer.chrome.com | Frame capture, run by HyperFrames | — | GpuPreference=2 | [C] used |
| FFmpeg 9.0.2 (Gyan build via winget) | https://ffmpeg.org, https://www.gyan.dev/ffmpeg/builds | Contact sheets, scene detection, audio extraction, EQ/arrangement, loudnorm mastering, probing | Media → media/reports | See stages | [C] used |
| yt-dlp | https://github.com/yt-dlp/yt-dlp | Downloaded the YouTube references and the Instagram reel | URL → mp4 + info.json | `-f "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720]"` (YouTube) | [C] used |
| Python 3.14 + numpy / librosa / soundfile / scipy | https://librosa.org | Reference tempo/onset/band analysis, take scoring, music arrangement | wav → numbers/wav | — | [C] used |
| PyTorch 2.11 cu128 + transformers | https://pytorch.org, https://huggingface.co/docs/transformers | Ran MusicGen on CUDA | Prompt → wav | fp16 | [C] used |
| MusicGen (`facebook/musicgen-medium`, `facebook/musicgen-stereo-medium`) | https://huggingface.co/facebook/musicgen-stereo-medium | Original music | Text prompt + seed → 30 s wav at 32 kHz | `guidance_scale=3.5, max_new_tokens=1500, do_sample` | [C] used |
| HeyGen TTS (voices Joelle, Hindi voice) | https://www.heygen.com | Voice-over for the earlier videos (not the showreel) | Text → wav + word timings | `--voice --lang --speed` | [C] used (earlier videos) |
| NVIDIA RTX 4050 Laptop GPU (driver 617.42) / NVENC | — | MusicGen, Chrome capture, encoding | — | — | [C] used |
| nvm (Author Software nvm for Windows) + Node 22.23.4 | https://nodejs.org | Runs npx/HyperFrames | — | Official zip, SHA256 verified | [C] used |
| winget | — | Installed FFmpeg | — | `--id Gyan.FFmpeg` | [C] used |
| Openverse API | https://openverse.org | Tried as an SFX source; unreachable | — | — | [C] attempted, failed |
| Kokoro TTS, HeyGen music catalog | — | Offered as options, not chosen | — | — | [C] mentioned only |
| pnpm | https://pnpm.io | Tried `pnpm dlx hyperframes` while npx was broken | — | — | [C] attempted |
| Instrument Sans font | https://fonts.google.com/specimen/Instrument+Sans | Brand typeface (woff2 in `assets/fonts`) | — | 400–700 | [C] used |
| Gemini (vision `--describe`) | — | Offered by `snapshot`; no key set, not used | — | — | [C] not used |

---

## 4. Prompt library

See [`PROMPTS.md`](PROMPTS.md). It holds the user's prompts verbatim, the MusicGen prompts verbatim, the voice-over texts and the derived reusable prompts. Each one has its purpose, input, output and how reusable it is.

---

## 5. Editing and production specifications (final showreel)

| Property | Value | Source |
|---|---|---|
| Aspect / canvas | 16:9, 1920×1080 CSS px | [C] index.html |
| Output resolution | 3840×2160 | [C] ffprobe |
| Frame rate | 60 fps | [C] |
| Duration | 28.000 s | [C] |
| Video codec | H.264 (HyperFrames `delivery`, NVENC via `--gpu`) | [C] ffprobe; exact CRF/bitrate [U] |
| Audio | AAC 320k, 48 kHz, −14.0 LUFS integrated, −1.5 dBFS peak | [C] |
| Clip order and durations | Stage 4 table | [C] |
| Transitions | Flash cut (chat→title, order→held), whip left/right with blur (held→gate, paid→crew), push up (sheet→choice), scale-blur dissolve (gate→sheet, title→order, crew→end) | [C] composition code |
| Speed changes | None on picture; music time-stretched to 124 BPM | [C] |
| Camera | Chat tracking rig (1.0–1.85×, punch 1.5×, zoom-through 10×); slow pushes of 1.03–1.06× per scene; button dive 26× | [C] |
| Text animation | Blur-in word stagger, pill pop, typewriter (text steps), counters | [C] |
| Captions | None in the showreel (the earlier videos had word-synced captions) | [C] |
| Colour grading | None as a separate pass. Grayscale palette by design (`#0a0a0b`–`#fafafa`, ink `#151515`) | [C] |
| Music | MusicGen take 404_p1, 124 BPM, drop at 9.0 s, volume 0.85, ducked at clicks | [C] |
| SFX | 79 cues, peaks aligned to picture +1 frame | [C] audio.py |
| Loudness target | −14 LUFS / −1.5 dBTP | [C] |

---

## 6. Input/output file inventory (showreel)

| Kind | Path | Notes |
|---|---|---|
| Reference | `%TEMP%\claude\C--Users-swapn-OneDrive-Desktop-HireCrew\01cacffb…\scratchpad\ref2\ref.mp4` (+ `ref.info.json`, `ref.wav`, `s1.jpg`, `s2.jpg`, `sheet1.jpg`) | Temp folder; copied into the pipeline's sample project |
| Music takes | `…\scratchpad\music\reel2\clip_musicgen-stereo-medium_{101,202,303,404,505,606}_p{0,1}.wav` | Temp; take 404_p1 copied into the sample |
| Music scripts | `…\scratchpad\music\batch_reel2.py`, `score.py`, `gen.py`, `gen2.py`, `batch.py` | Temp |
| Brand | `video-showreel/assets/brand/hirecrew-icon.png`, `hirecrew-logo.png`, `hirecrew-logo-trim.png` | |
| Fonts | `video-showreel/assets/fonts/instrument-sans-{400..700}.woff2` | |
| SFX | `video-showreel/assets/sfx/*.mp3` (20 files) | |
| Project | `video-showreel/index.html`, `compositions/*.html` (10), `hyperframes.json`, `package.json`, `meta.json` | |
| Tools | `video-showreel/tools/music.py`, `tools/audio.py` | |
| Intermediate | `assets/music/bed*.wav`, `renders/showreel_raw.mp4`, `renders/render.log` | |
| Final | `video-showreel/renders/hirecrew_showreel_4k60.mp4` (76.6 MiB), `hirecrew_showreel_thumb.jpg` | |
| Audit stills | `.snap/*`, `…\971ceb85…\scratchpad\audit\*.jpg` | Review only |

---

## 7. Dependency and workflow architecture

```
reference URL ──yt-dlp──► ref.mp4 ──ffmpeg──► contact sheets, cuts ──► (Claude reads) style notes
                                └─ffmpeg/librosa──► tempo, onsets, band share ──┐
brand site (frontend/) ──► tokens/CSS/fonts/logos ──┐                          │
creative brief + script ─────────────────────────────┼─► storyboard (scenes, durations, drop time)
                                                     │                          │
MusicGen (prompts × seeds) ──► takes ──score.py──► best take ──music.py (BPM, drop)──► bed.wav
storyboard ──► compositions/*.html + index.html ──► check ──► snapshots (approval) ──┐
SFX library + cue sheet ──audio.py──► <audio> block in index.html ────────────────────┤
                                                                                     ▼
                     GPU preference ─► hyperframes render (4K60, --gpu) ─► raw.mp4 ─► loudnorm ×2 ─► final.mp4 ─► audit
```

---

## 8. Errors and corrections

| When | Problem | Fix | Status |
|---|---|---|---|
| 10-29 | FFmpeg missing | `winget install --id Gyan.FFmpeg` | [C] |
| 10-29 | Openverse API unreachable for SFX | Used the bundled media-use SFX | [C] |
| 10-29 | Render used the Intel iGPU; the user objected | Registry GpuPreference=2 for chrome-headless-shell; `--gpu` | [C] |
| 10-29 | Python printing failed on "→" (cp1252) | `PYTHONIOENCODING=utf-8` / `-X utf8` | [C] |
| 11-04 | NVM blocked npx (NVM4306, "delegated script changed since it was trusted") | Not bypassed (security). The user re-trusted it; npm then went missing; `nvm install` timed out; the official Node 22.23.4 zip was downloaded with curl, its SHA256 verified, and extracted into nvm installs | [C] |
| 11-04 | Music take 303 had a near-silent hole at 9–15 s | Switched to take 404 with stronger EQ; padded to 28 s | [C] |
| 11-04 | Zoom-through target wrong | x −270, y −756 | [C] |
| 11-04 | Header overlap, caps bubble clipped, empty first frame | Solid header z-index; `max-width:none`; m1 visible at frame 0 | [C] |
| 11-04 | Cursor clicks masked by hi-hats | Click layers and music duck at clicks | [C] partial; never listened to by a person |
| 11-04 | Logo tile misaligned (user screenshot) | Trimmed logo PNG, grid-centred | [C] |
| 11-04 | Overlapping GSAP tweens (title/crew) | Shortened camera pushes | [C] |
| 11-05 | Messages scrolled over the chat header; a white line swept the header | Header removed; per-sender labels; camera rig | [C] |
| 11-05 | "BROIT": word space collapsed by −0.03em tracking | `letter-spacing −0.01em; word-spacing .1em` | [C] |
| 11-05 | HC icon cropped to "H!" in the avatar; tile invisible on dark backgrounds, so it read as a stray font | Image fitted to the avatar; light ring/shadow | [C] |
| 11-05 | Accept button went blank: `#cc-accept span {position:relative}` also matched `#cc-fill` (higher specificity) | Selector narrowed to `#cc-acc-t` | [C] |
| 11-05 | Cursor clicked below the buttons | Cursor y 640 → 548, x to the button centres | [C] |
| 11-05 | Title chips tiny and blurred | Clay icon tiles (generic glyphs), depth blur on the far tiles only | [C] |
| 11-05 | Caret far from the typed letters (clip-path reveal) | Real typed text, fixed-width box | [C] |
| 11-05 | BLOCKED stamp half-covered a label | Label fades as the stamp lands | [C] |
| 11-05 | Blurred blob with a hard edge / seam | Radial-gradient blobs kept inside the frame | [C] |
| 11-05 | Gate scene empty for about 0.15 s after the cut | Entry offset 1600 → 1000 | [C] |
| 11-05 | HyperFrames auto-updated to 0.9.15 | Registry GPU path checked; unchanged | [C] |
| 11-05 | Render warned "Audio lowered 3.9 dB … peak passed the delivery ceiling" | Two-pass loudnorm mastering restores −14 LUFS | [C] |

---

## 9. Unknown information and limitations

- **[U] Encoder settings.** The exact CRF/bitrate HyperFrames used for `--quality delivery` is not printed. Use `--debug` or check the HyperFrames source.
- **[U] Render time.** The 4K60 render time was not recorded for the final pass (`time` was used in v1, but the output was not kept in the summary).
- **[U] Derived SFX.** How `pop-hi/pop-lo/click-lo/whoosh-hi/whoosh-lo/stamp` were derived from the bundled library: they appear in `video/assets/sfx` from the first film. The derivation commands are in the 10-29 part of the transcript and were not re-extracted for this report.
- **[U] Audio check.** No human listened to the final mix in-session. Loudness was measured, not judged by ear.
- **[I] Visual review.** Claude's frame reviews are judgment calls on contact sheets. No automated perceptual check exists beyond `hyperframes check`.
- **Outside this chat, not verifiable:**
  - The user's NVM re-trust actions.
  - The HeyGen sign-in (`npx hyperframes auth login`, done by the user).
  - What happened to the files after delivery (Instagram/X posting).
- **Licensing.** The reference reel is third-party content, used only for analysis and never included in the output. MusicGen weights are CC-BY-NC 4.0 per Meta's model card, so check the licence before commercial use of generated music [I: from the public model card, not this chat]. The bundled SFX come with a CREDITS.md in the skill.
- **Temporary storage.** Scratchpad folders under `%TEMP%` can be wiped. The pipeline's sample project copies what it needs.

---

## 10. Reusable end-to-end SOP

The SOP is implemented in `reelforge`; see `README.md` for the commands. Each stage reads the outputs of the stage before it and writes into `build/<project>/<stage>/`.

| # | Stage | Kind | Output | Checkpoint |
|---|---|---|---|---|
| 1 | `ingest` (copy/download refs, footage, brand assets) | Automated | `build/…/ingest/manifest.json` | — |
| 2 | `analyze` (probe, cuts, contact sheets, tempo/onsets/bands) | Automated | `analysis.json`, `sheet_*.jpg` | **Human/AI review of the sheets → style notes** |
| 3 | Script + storyboard (`project.yaml`) | AI-assisted / manual | `project.yaml` scenes | **Approve the script** |
| 4 | `music` (MusicGen takes → score → arrange to BPM and drop) | Automated (GPU) | `assets/music/bed.wav` | Optional listen |
| 5 | `voice` (provided wav or HeyGen lines → assembled VO + words) | Automated / manual credentials | `assets/voice/vo.wav`, `words.json` | Approve the voice |
| 6 | `compose` (templates + custom scenes → HyperFrames project) | Automated | `build/…/hf/` | — |
| 7 | `sfx` (auto cues + manual cues → audio block, ducking) | Automated | AUDIO block | — |
| 8 | `check` (`hyperframes check`) | Automated | Lint report | Fail on errors |
| 9 | `preview` (snapshots: beats + seams) | Automated | `preview/*.jpg` | **Approve the preview** (`reelforge approve`) |
| 10 | `render` (GPU pref + render) | Automated | `raw.mp4` | — |
| 11 | `master` (two-pass loudnorm) | Automated | `final.mp4` | — |
| 12 | `audit` (probe, loudness, contact sheets) | Automated | `audit.json`, `audit_*.jpg` | **Final sign-off** |

---

## 11. Automation opportunities

- **Vision review.** Automate frame review with a vision model, e.g. `hyperframes snapshot --describe` with a Gemini key, or the Claude API. It could flag clipped text and overlaps, where today Claude reads the sheets by eye.
- **Layout checks.** Measure real DOM boxes in a headless pass and flag elements crossing the frame or each other, beyond what `hyperframes check` covers.
- **Beat-snapped cuts.** Snap scene boundaries to the analysed music beats automatically.
- **Music.** Pick the take by listening tests or a learned score; generate stems with a stem-capable model.
- **Batch renders.** Render several aspect ratios from one storyboard with HyperFrames `--batch` and variables.
- **Delivery.** Generate the caption, thumbnail and social copy in the audit stage.

---

## 12. Recommended project folder structure

```
video-pipeline/
  reelforge/               engine (python -m reelforge …)
  config/defaults.yaml     tool, render, music, master settings
  config/prompts.yaml      MusicGen, analysis and review prompts
  style/                   brand head CSS (tokens, clay classes)
  templates/scenes/        generic parameterised scene templates
  assets/                  shared fonts, brand, sfx
  projects/<name>/
     project.yaml          brief, canvas, storyboard, music, voice, cues, render
     scenes/               custom scene HTML (optional)
     assets/               project-only assets (music takes, footage, voice)
     refs/                 reference videos
  build/<name>/            generated: ingest/ analyze/ music/ hf/ preview/ render/ audit/ state.json logs/
  docs/REPORT.md, docs/PROMPTS.md
```

---

## 13. Implementation status (Part 2)

The SOP in section 10 is implemented as `reelforge` (see `README.md` for setup and commands). End-to-end results on this machine, 2026-11-05:

- **Original film rebuilt** (`projects/showreel`, from source assets):
  - Scenes byte-identical.
  - 79-cue audio block identical.
  - Music bed bit-identical (the arrangement code reproduces `tools/music.py` exactly).
  - 4K60 render in 2 min 18 s on the RTX 4050.
  - Measured against the original delivered file: SSIM 0.99992, PSNR 70 dB.
- **New-content portrait reel** (`projects/demo-portrait`, every template plus footage, voice and captions): rendered at 1080×1920, 30 fps, with 0 check errors.
- **Reference analysis** reproduced the original measurements (123 BPM, 26 onsets) and found the 9.00 s drop by itself.
- **Take scorer** picked the same take the original session chose by hand (404_p1).
- **Two differences from the hand-made project, both harmless:**
  - The generated `index.html` sets the canvas size in a separate CSS rule.
  - The first scene host reads `data-start="0.0"` instead of `"0"`.

### 13.1 Upgrade (2026-11-05): talking-head editing

New stages:

- **`transcribe`:** Whisper large-v3-turbo for word timings, plus Whisper large-v3 for translating windows to English.
- **`autoedit`:** silence trim, jump cuts, punch-ins, motivated transitions, list/stat/keyword motion graphics, hook, outro and progress bar.

Other changes:

- Bar-aligned music looping.
- A dialogue track re-cut to match the picture.
- Ducking under speech.
- Reel-style captions.

Verified on `projects/creator-talk` (Urdu, 49.8 s → 49.9 s edit with outro). The original showreel still reproduces exactly: scenes byte-identical, audio block identical.
