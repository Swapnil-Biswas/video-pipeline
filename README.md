# reelforge

Turns raw footage into short-form reels. Give it a talking-head clip (and optionally a reference video whose style you like); it transcribes the speech, cuts it, frames it, captions it, adds graphics and music, and renders on the GPU with [HyperFrames](https://github.com/heygen-com/hyperframes).

## What an edit gets

- **Tight speech edit:** pauses and filler sounds removed, cuts placed where the speaker breathes.
- **Face-centred framing:** three framing levels, a visible change on every cut, tighter on emphasis, with a quick zoom on key moments.
- **Outlined captions:** bold 2–3 word groups, the spoken word in the accent colour, always below the face. Non-English speech gets English captions.
- **Sparing graphics:** a hook line at the start, a stat when a number is said, a checklist when a list is said, an occasional emoji. They never overlap.
- **Audio:** voice clean-up, music looped by whole bars and ducked under speech, small sound effects, mastered to −14 LUFS.
- **B-roll:** any extra footage clips are cut in while the dialogue keeps playing.
- **Reference styling (optional):** pacing, transition mix, accent colour, type and a bounded colour match learned from a reference video. Trim and crop a reference to learn from part of it.

Footage without speech gets a montage cut on the music's beat grid.

## Install

Needs Node.js 22+, FFmpeg and Python 3.11+. Install CUDA PyTorch first, then the rest with the constraints file:

```bash
pip install torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu128
```

```bash
pip install -r requirements.txt -c constraints.txt
```

```bash
python -m reelforge doctor
```

## Use

One command, using a reference video:

```bash
python -m reelforge edit --reference ref.mp4 --footage raw.mp4
```

Or start from a project file (`projects/reel-talk/project.yaml` is a working example):

```bash
python -m reelforge new my-reel --aspect portrait
```

```bash
python -m reelforge run projects/my-reel
```

```bash
python -m reelforge approve projects/my-reel preview
```

```bash
python -m reelforge run projects/my-reel --from render
```

The first run stops at a preview checkpoint (`build/<name>/preview/`). The final video is in `build/<name>/final/`.

Common settings in `project.yaml` (every default is in `config/defaults.yaml`):

```yaml
captions: {enabled: true, style: stroke}     # stroke | highlight | pill | color | clean | slam | subtle
theme: {accent: "#ff3b30"}                   # any colour or font token from reelforge/theme.py
autoedit: {hook_text: "Nobody tells you [this]", min_shot: 1.6, max_shot: 4.5, keyword_spacing: 4.5}
transcribe: {fixes: [['wrong phrase', 'right phrase']]}   # proofread captions
brand: {watermark: {text: "@yourhandle", position: bottom-right}}
references: [{src: ref.mp4, trim: [0, 8], crop: [0.1, 0.3, 0.4, 0.4]}]
style: {from_reference: true}
```

Extra clips listed under `footage:` are used as B-roll. `python -m reelforge fetch` downloads stock clips and sound effects (Pexels/Pixabay need a free API key).

Stages: `ingest → analyze → style → transcribe → autoedit → music → voice → compose → sfx → check → preview → [approve] → render → master → audit`. Unchanged stages are skipped on re-runs.

An HTTP job API is available with `python -m reelforge serve`; see [docs/PRODUCTION.md](docs/PRODUCTION.md).

## Tests

```bash
python -m unittest discover -s tests
```

## Licensing

The tracks in `assets/music/library` were generated with MusicGen (CC-BY-NC, non-commercial). Replace them with licensed music for commercial use. Reference videos belong to their creators and are never copied into the output.
