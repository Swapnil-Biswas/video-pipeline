# Reference editing grammar — decoded from 9 creator reels

Nine short-form reels (5 YouTube Shorts `yt01–05`, 4 Instagram reels `ig01–04`) were downloaded to this folder
and analysed (ffmpeg scene-cut detection + contact sheets in `_sheets/`). This file records the **editing grammar**
they share, and maps each pattern to how reelforge builds it (done / partial / to build).

## Measured pacing (scene-cuts per minute)

| clip | dur | cuts/min | mode |
|---|---|---|---|
| ig03 | 57s | 6 | talking-head, slow |
| yt03 | 48s | 11 | talking-head |
| ig01 | 61s | 11 | talking-head |
| yt02 | 55s | 15 | talking-head |
| yt05 | 39s | 17 | talking-head |
| yt01 | 37s | 25 | talking-head + heavy graphics |
| ig02 | 41s | 42 | talking-head + screen-rec B-roll |
| yt04 | 58s | 48 | **montage** (no talking head) |
| ig04 | 32s | 52 | talking-head, fast kinetic |

Takeaway: two families — **talking-head** (speaker on camera, graphics float in) and **montage** (no speaker, pure
kinetic type + B-roll). reelforge already distinguishes these (`autoedit.mode: talk | montage | auto`).

## The shared grammar

1. **Word-by-word captions** — every clip. Bold, 1–3 words at a time, the **keyword in a brand accent** (blue `yt01`,
   orange `ig02`, teal `yt04`, red `ig04`), as a pill or coloured text. Casing varies (UPPER common). Position:
   over the speaker (~0.66 height) or bottom. → reelforge `captions.style: reel` + `style.from_reference` (learns
   accent + casing via OCR). **Done.**
2. **Hook title card** — opening title, often on black (`yt01` "THE DEVIN JATHO"). → `autoedit.hook`. **Done.**
3. **Floating cards beside the speaker**, synced to words: tier-lists (`yt01`), app-icon tiles, photo thumbnails
   (`ig04`), chat/quote bubbles (`yt01`, `yt04`), stat callouts ("$197K" `yt01`, "$1.23M" `yt04`). → `kinetic` tiles,
   `card`, `chat`, and `overlay` keyword/stat/lowerthird types. **Done / partial** (photo-thumbnail tiles = to build).
4. **Keyword & stat pops** timed to emphasis words. → `autoedit` keyword overlays. **Done.**
5. **Build-up checklists** ("Better / Healthier / Cheaper" `yt04`; "See the technique / Understand…" `ig02`). →
   `list` scene. **Done.**
6. **Lower-third role labels on B-roll** ("Designer / Editor / Creator" `ig02`). → `overlay: lowerthird`. **Done.**
7. **B-roll cutaways** — screen recordings (`ig02`), stock, product shots (`yt04`), property interiors, synced to the
   narration. → `autoedit` cutaways (currently list-triggered only). **Partial — to build:** learn B-roll *cadence*
   from the reference and place supplied B-roll clips on it.
8. **Inline emoji in captions** ("how 🦊 🐎 🐅" `ig02`) and **mascot stickers** (`yt04`). Emoji already render in any
   `lines`/caption text (they are Unicode). **To build:** auto-placing emoji on keywords.
9. **Persistent brand watermark / @handle** and **outro logo+contact card** ("BARSOL MEDIA · info@… · www.…" `ig04`). →
   **Watermark overlay implemented** (`brand.watermark`, see below). Outro card = `endcard` scene. **Done.**
10. **Technical HUD chrome** — corner brackets, timecodes, "SCENE 01/04" labels (`ig02`). A distinctive skin. **To build.**
11. **Hand-drawn annotation** — a red marker circle/scribble on the subject (`ig04`). **To build.**

## Implemented this pass — brand watermark

`brand.watermark` in `config/defaults.yaml` (off by default). Drawn over every frame via `templates/index.html.j2`:

```yaml
brand:
  watermark: {text: "@yourhandle", logo: assets/brand/your-logo.png, position: bottom-right, opacity: 0.8, size: 30}
```

`position`: `top-left | top | top-right | left | right | bottom-left | bottom | bottom-right`. `text` and/or `logo`.
Colour follows the theme (`cap_fg`) with a soft shadow so it reads on any footage.

## Roadmap (proposed next increments)

- **A. Multi-reference learning** — let `style.from_reference` aggregate several references (median pacing, most-common
  transitions, dominant accent) instead of only `references[0]`.
- **B. B-roll auto-placement** — a `broll:` pool + learn cutaway cadence from the reference; drop B-roll over narration
  gaps / keyword spans.
- **C. Emoji auto-pops** — a keyword→emoji map, placed like keyword overlays.
- **D. HUD-chrome and marker-annotation skins** — optional overlay styles toggled by the reference's look.
