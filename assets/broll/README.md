# B-roll library

Categorised B-roll clips the autoeditor can cut away to (see `autoedit.broll` in `config/defaults.yaml`).
Point a project's `footage:` at clips here and they join the B-roll pool automatically.

The `.mp4` files are **git-ignored** (large / third-party). Regenerate the local ones, or drop your own in.

## Categories

| folder | content | source |
|---|---|---|
| `abstract/` | soft moving textures | local (ffmpeg) |
| `gradient/` | animated colour-gradient backgrounds | local (ffmpeg) |
| `fractal/` | zooming fractal | local (ffmpeg) |
| `particles/` | drifting particle fields (red tint matches the accent) | local (ffmpeg) |
| `city/` | streets, skylines, traffic time-lapse | **download** (stock) |
| `nature/` | landscapes, water, sky | **download** (stock) |
| `interior/` | rooms, architecture, decor | **download** (stock) |
| `tech/` | screens, devices, code | **download** (stock) |
| `finance/` | charts, money, markets | **download** (stock) |
| `people/` | hands, faces, lifestyle | **download** (stock) |

## Generate the local clips

```bash
bash scripts/generate-broll.sh
```

Produces full-HD (1920×1080) abstract/gradient/fractal/particle clips — no downloads, no licensing. Best as
background / transition B-roll under kinetic type, not as literal scene cutaways.

## Fetch media into the library (`reelforge fetch`)

```bash
# B-roll video (needs a free key: PEXELS_API_KEY or PIXABAY_API_KEY)
python -m reelforge fetch broll "modern kitchen interior" --category interior -n 5 --source pexels --orientation portrait

# Sound effects / music — Openverse, Creative-Commons, NO key needed
python -m reelforge fetch sfx "whoosh transition" -n 8        # -> assets/sfx/fetched/

# CC images — Openverse, no key needed
python -m reelforge fetch image "city skyline" --category city -n 5
```

Pexels/Pixabay are licence-free. Every Openverse download writes a `<file>.attrib.txt` with the required
Creative-Commons attribution — read it before publishing. Fetched B-roll joins the B-roll pool automatically
when a project's `footage:` points at the folder.

## Real-footage categories (city, nature, interior, tech, finance, people)

These need real stock, which must be sourced legally. The reliable route is a **free Pexels or Pixabay API key**
(anonymous access to both is blocked). With a key, clips can be fetched by category into the folders above. Public
-domain archives (archive.org) carry mostly vintage/archival footage, not modern short-form B-roll.

Whatever the source, keep each clip's licence terms in mind before publishing a video that uses it.
