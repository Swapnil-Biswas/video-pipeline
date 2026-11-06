# reelforge: the HireCrew showreel pipeline, made reusable

`reelforge` rebuilds the workflow that produced `video-showreel/renders/hirecrew_showreel_4k60.mp4` as a modular, resumable pipeline. You describe a video in one `project.yaml`: the canvas, the scenes, the music, the voice and the render settings. The pipeline then:

1. Ingests and analyses the references and footage.
2. Generates, scores and arranges the music.
3. Builds the voice track.
4. Composes a HyperFrames project from scene templates.
5. Lays in the sound effects.
6. Checks the project and stops at a **preview checkpoint** for your approval.
7. Renders on the GPU, masters the loudness and audits the final file.

The full reverse-engineering report is [`docs/REPORT.md`](docs/REPORT.md). The verbatim prompt library is [`docs/PROMPTS.md`](docs/PROMPTS.md), with the machine-readable copy in `config/prompts.yaml`.

## Test results (2026-11-05, RTX 4050 laptop)

| Test | Result |
|---|---|
| `projects/showreel`: the original film rebuilt from source assets | Scenes byte-identical to `video-showreel/compositions`. Audio mix (79 cues, 8 lanes, 3 click ducks) identical. Music bed **bit-identical**. Final render 3840×2160, 60 fps, 28.000 s, −14.0 LUFS, −1.5 dBFS, captured on the RTX 4050 in 2 min 18 s. Against the original delivered file: **SSIM 0.99992, PSNR 70 dB** (encoder noise only). |
| `projects/demo-portrait`: new content, 9:16, built only from templates | Footage ingest/trim, take scoring, arrangement, voice + captions, 37 auto SFX cues, click ducks and every template. `hyperframes check`: 0 errors. Render 1080×1920, 30 fps, 17.1 s, −13.6 LUFS, in 35 s on the GPU. |
| Reference analysis | Reproduced the original numbers: 123 BPM, 26 strong onsets, drop found at 9.00 s |
| Take scorer | Independently picked `404_p1`, the take chosen by hand in the original session |
| MusicGen generation (live, GPU) | Take generated, then stretched and beat-aligned |
| HeyGen voice assembly | Ran from cached HeyGen lines. Timings match the original reel; no API credits spent |
| Unit tests | `python -m unittest discover -s tests -v`: 17/17 pass |

Outputs:

- `build/showreel/final/showreel_landscape-4k_60fps.mp4`
- `build/demo-portrait/final/demo-portrait_portrait_30fps.mp4`

## Install (Windows; macOS/Linux work the same with their own package managers)

1. **Node.js 22+**: https://nodejs.org. HyperFrames runs through `npx`, so nothing to install globally.
   With nvm-for-Windows shims, a plain `node` may only work inside the shell that ran `nvm use`. reelforge finds the real install itself. If it can't, set `REELFORGE_NODE=C:\path\to\node.exe`.
2. **FFmpeg**:
   ```bash
   winget install --id Gyan.FFmpeg -e
   ```
3. **Python 3.11+**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Optional, for `music.mode: generate` and for `transcribe` (Whisper).** Install CUDA PyTorch and transformers (about 3 GB of downloads; uses the GPU):
   ```bash
   pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
   ```
   ```bash
   pip install transformers
   ```
5. **Optional, for `voice.mode: heygen`.** You need the HyperFrames `media-use` skill (it provides `heygen-tts.mjs`) and a HeyGen sign-in:
   ```bash
   npx hyperframes auth login
   ```
6. **Check everything:**
   ```bash
   python -m reelforge doctor
   ```

## Run

Run these from `video-pipeline/`.

Start a new project (`--aspect` takes `landscape`, `portrait` or `square`):
```bash
python -m reelforge new my-video --aspect portrait
```

Run everything up to the preview checkpoint:
```bash
python -m reelforge run projects/my-video
```

Approve the preview after looking at `build/my-video/preview/`:
```bash
python -m reelforge approve projects/my-video preview
```

Render, master and audit:
```bash
python -m reelforge run projects/my-video --from render
```

Other useful commands:

| Command | What it does |
|---|---|
| `python -m reelforge status projects/my-video` | Shows which stages are done and the checkpoint state |
| `python -m reelforge run projects/my-video --only compose` | Re-runs a single stage |
| `python -m reelforge run projects/showreel --set render.resolution=landscape --set canvas.fps=30` | Overrides any config value for one run (here a quick 1080p30 version) |
| `python -m reelforge run projects/my-video --yes` | Skips the checkpoint (CI / batch use) |
| `python -m unittest discover -s tests -v` | Runs the unit tests |

Stages: `ingest → analyze → transcribe → autoedit → music → voice → compose → sfx → check → preview → [approve] → render → master → audit`.

- A stage is **skipped when nothing it depends on changed**. That covers its config keys, the previous stage, and its own code.
- `--force` re-runs a stage anyway.
- On failure, the stage and every later stage are invalidated. The error and the full command output go to `build/<name>/logs/run_*.log`.

## Writing a project

```yaml
name: my-video
canvas: {width: 1080, height: 1920, fps: 60}
references: [{url: "https://www.instagram.com/reel/…"}]    # → build/<name>/analyze: contact sheets, cuts, tempo, drop
footage:   [{id: clip1, src: assets/footage/raw.mp4, trim: [2, 6]}]
scenes:
  - {id: hook, type: chat, duration: 4, groups: [{who: AI agent, messages: [{side: out, text: "…"}, {side: in, text: "Done!"}, {side: out, text: "IT WORKED", big: true}]}]}
  - {id: meet, type: footage, video: clip1, duration: 2, entry: flash, caption_pos: center, lines: [{text: "Meet [Brand.]"}]}
  - {id: title, type: kinetic, world: light, duration: 1.6, tiles: [mail, grid, doc, chat], lines: [{text: "One [big promise.]", size: 150}]}
  - {id: proof, type: card, world: dark, duration: 2, heading: "You [verify.]", card: {title: "Delivered", buttons: [Dispute, "Accept · pay"], hover: 0, click: 1, result: Released}}
  - {id: end, type: endcard, duration: 4.5, type_text: "This is", logo: assets/brand/hirecrew-logo-trim.png, tagline: "Pay only for [finished work.]", cta: "Join →"}
  - {id: custom, type: file, src: scenes/custom.html, duration: 2}           # any hand-written HyperFrames scene
music:   {mode: generate, arrange: {bpm: 124, drop: 4.0}}                    # or take / file / none
voice:   {mode: file, file: assets/voice/vo.wav, words: assets/voice/words.json}   # or heygen with lines / none
captions: {enabled: true}
render:  {resolution: portrait-4k, quality: delivery, gpu: true}           # landscape | portrait | square | *-4k
```

How the templates behave:

- **Accent pill.** `[brackets]` mark the accent pill, the showreel's signature.
- **Scene types.** Every template follows the original grammar: blur-in word staggers, back-out pill pops, clay cards, a cursor that lands *inside* its button (so it can't miss), the chat tracking camera with a punch-in and zoom-through, and a name reveal that fades to black.
- **Sound cues.** Templates emit their own SFX cues: pops on bubbles and accents, whooshes on whips, click plus duck on clicks, impacts on reveals. Extra or replacement cues go in `sfx.cues` as `[file, film_time, volume]`. Set `sfx.auto: false` to use manual cues only, as the showreel sample does.
- **Any canvas size.** All template sizes scale with `u = min(W, H) / 1080`. The same storyboard renders in 16:9, 9:16 or 1:1. Use `file` scenes for anything bespoke.

## Editing raw talking-head footage (`scenes: auto`)

Point the pipeline at a talking video and it makes an editor's first cut from what is said:

```yaml
footage: [{id: talk, src: "C:/path/raw.mp4"}]
aroll: {video: talk}                 # its sound is the dialogue track
transcribe: {enabled: true}          # Whisper on the GPU; non-English speech gets English captions
scenes: auto
autoedit: {list_heading: "What you [need]", outro: {type: kinetic, lines: [{text: "Still want to [start?]", size: 140}]}}
captions: {enabled: true, style: reel}
music: {mode: take, takes_dir: ../showreel/assets/music, arrange: {bpm: 124, drop: 0, intro_lowpass: false}, volume_under_voice: 0.11}
```

| Stage | What it does |
|---|---|
| `transcribe` | Whisper large-v3-turbo word timings in the spoken language (sequential decoding, no chunk seams). When the speech isn't English, sentence-sized windows are translated with Whisper large-v3 and the English words are laid back onto the real speech time, pauses skipped. `transcribe.fixes` (regex pairs) is the proofreading pass. |
| `autoedit` | Cuts out pauses, then makes jump cuts at word boundaries (1.3–4.2 s shots) with alternating punch-in framing. Adds motivated transitions: hard cuts, a zoom punch every few cuts, a flash on new sentences, zoom-blur in and out of graphics. Turns what is said into motion graphics: lists become a full-screen checklist cutaway with each item landing on its word, numbers become a counting stat card, keywords become pop-ups with clay icons, all in the headroom above the speaker. Also adds the hook title, lower third, outro and a progress bar. Writes `build/<name>/autoedit/plan.json`. |
| `music` | Takes shorter than the film are **looped by whole bars** with crossfades on the downbeat, so the grid never drifts. |
| `sfx` | The dialogue is re-cut to match the picture: one clip per kept span, with tiny edge fades. The music is ducked under the speech. Every transition and graphic has its own sound. |

Footage-shot transitions available to any project: `cut`, `punch`, `zoom-blur`, `flash`, `shake`, `whip-left`, `whip-right`, `push-up`, `blur`.

Footage overlays available to any project: `keyword`, `stat`, `lowerthird`, plus the `list` cutaway scene type.

Tested on a 49.8 s Urdu talking video (`projects/creator-talk`):
- 2.5 s of pauses were cut, leaving 14 shots with one checklist cutaway, a stat card and 5 keyword pop-ups.
- English reel captions, a looped music bed and the outro.
- `hyperframes check` passed with 0 errors.
- Rendered on the RTX 4050 in 103 s: 1080×1920, 30 fps, 49.9 s, −13.9 LUFS.
- No dialogue gaps or clicks at any of the 15 cuts.

## What is automated, AI-assisted, manual

| Stage | Kind | Human checkpoint |
|---|---|---|
| ingest, analyze, music (generate/score/arrange), voice assembly, compose, sfx, check, render, master, audit | Automated | — |
| Style notes from the reference sheets | AI-assisted: `build/<name>/analyze/STYLE_NOTES_PROMPT.md` + the sheets, for Claude or a person | Read the notes |
| Script and storyboard (`project.yaml`) | AI-assisted (prompt `review.storyboard` in `config/prompts.yaml`) or manual | Approve the script |
| Preview QA (`build/<name>/preview/`, prompt in `QA_PROMPT.md`) | Human or AI review | **`reelforge approve`** (enforced before render) |
| Final sign-off (`build/<name>/audit/`) | Human | Sign off on the contact sheets; `audit.json` flags format and loudness problems automatically |
| HeyGen sign-in, voice choice, music licensing | Manual | — |

## Layout

```
reelforge/            engine: cli.py, config.py, util.py, stages/{ingest,analyze,music,voice,compose,sfx,check,preview,render,master,audit}.py
config/               defaults.yaml (every setting, originals marked), prompts.yaml (MusicGen, briefs, review prompts)
style/                hirecrew-bw.css: brand tokens and clay classes from the original film
templates/            index.html.j2 + scenes/{_lib,kinetic,card,chat,endcard,footage,captions}.html.j2
assets/               fonts (Instrument Sans), brand logos, SFX library
projects/showreel/    the original film: 10 hand-authored scenes, six MusicGen takes, the reference reel, 79 cues
projects/demo-portrait/  new-content sample (9:16)
projects/_template/   used by `reelforge new`
tests/                unit tests
docs/                 REPORT.md, PROMPTS.md, _extract/ (verbatim prompts and voice texts as JSON)
build/<name>/         generated: ingest/ analyze/ music/ voice/ hf/ (the HyperFrames project) check/ preview/ render/ final/ audit/ logs/ state.json
```

## Notes and limits

- **GPU.** The render stage pins headless Chrome to the high-performance GPU on Windows (`HKCU\Software\Microsoft\DirectX\UserGpuPreferences`, as in the original session) and passes `--gpu` for NVENC encoding.
- **Reading time.** HyperFrames' reading-time warnings are expected in a fast montage cut like the reference. Errors still stop the pipeline.
- **Licensing.** MusicGen weights are CC-BY-NC 4.0 (check before commercial use). Reference videos are used only for analysis and never copied into the output.
- **Not exercised live.** The HeyGen network call was not run here, to avoid spending credits. The voice stage was tested from cached HeyGen lines.
