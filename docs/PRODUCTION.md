# reelforge in production: "edit my video like this one"

A user uploads **their footage** and **a reference video they like**. reelforge learns the reference's editing style,
and edits the footage that way. The style covers pacing, transitions, colours, fonts, caption look, colour grade and music tempo. A person approves the preview, and reelforge renders on the GPU.

## How the style is learned (`style` stage)

| Learned from the reference | How | Applied to |
|---|---|---|
| Pacing | Scene cuts (ffmpeg scene score) give shot lengths | Jump-cut rhythm (`autoedit.min_shot/max_shot`), punch cadence, montage shot lengths |
| Transitions | At each cut: luma spike that falls back = flash, sharpness dip = blur/whip, same scene re-framed = punch, else hard cut | The transition mix the auto-edit draws from |
| Energy | Frame-to-frame motion | Punch-in strength, keyword pop-up density |
| Palette | k-means in Lab, plus a separate search of saturated pixels for small accents | Theme: dark world, light world, accent pill, text colours (contrast-checked) |
| Typography | EasyOCR boxes: letter width/height, stroke fill, case | Display font from HyperFrames' bundled families (League Gothic, Oswald, Montserrat, Archivo Black, Poppins or the brand font), uppercase |
| Captions | OCR: presence, position, size, words per line, highlight colour | Caption style (`pill`, `highlight`, `color`, `slam`, `clean`), size, case, position |
| Colour grade | Luma, contrast, saturation, warmth, shadow/highlight tints, vignette, compared with the user's footage | HyperFrames realtime grading on the footage (`data-color-grading`), bounded, and weighted down when the reference is flat motion graphics |
| Music | Tempo, drop, brightness | Library track scored against the reference, stretched to its BPM and looped by bars. Or a MusicGen prompt |

**What always wins over the reference:**
- **Safety rules:** captions and graphics are kept off the speaker's face (YuNet face detection, punch-ins included). Text must pass a contrast check.
- **The user's options:** anything set in `project.yaml` / the API options overrides the learned style.
- **What is reported:** everything learned is written to `build/style/style.json`.

The footage decides the structure:
- **Talking head** (speech found): transcript-driven cut, captions and motion graphics.
- **Anything else:** montage on the beat grid at the reference's shot lengths.

## Run it

```bash
python -m reelforge edit --reference ref.mp4 --footage raw.mp4 --options '{"outro_text": "Follow for [more]"}'
```

```bash
python -m reelforge job-approve <job-id>
```

The first command stops at the preview checkpoint, under `jobs/<id>/build/preview`. Add `--yes` to skip it. The second approves the preview and renders.

```bash
python -m reelforge serve --host 0.0.0.0 --port 8088
```

That runs the API. Interactive docs are at http://host:8088/docs.

### API

All `/v1` calls except `/v1/health` need the header `X-API-Key: $REELFORGE_API_KEY`.

| Call | Body / result |
|---|---|
| `POST /v1/jobs` | multipart `reference` (file), `footage` (file, repeatable, up to 10), `options` (JSON). Returns the job (201) |
| `GET /v1/jobs/{id}` | `state` (`queued` → `running` → `awaiting_approval` → `rendering` → `done`, or `failed`/`cancelled`), `progress`, `queue_position`, `preview` image URLs, `result` (video URL, thumbnail, audit), `error` |
| `GET /v1/jobs/{id}/files/{path}` | Preview images, thumbnail and final video of that job only |
| `POST /v1/jobs/{id}/approve` | Approve the preview, then render |
| `POST /v1/jobs/{id}/cancel` | Cancel; kills the running process |
| `GET /v1/health` | Tools, GPU, queue length, limits |

Options (all optional):

| Option | Values | Default |
|---|---|---|
| `aspect` | footage, reference, 9:16, 16:9, 1:1 | footage |
| `resolution` | 1080, 4k | 1080 |
| `fps` | auto (follows the reference), 24, 25, 30, 60 | auto |
| `mode` | auto, talk, montage | auto |
| `captions` | true, false | true |
| `caption_language` | english, original | english |
| `hook_text` | string; `[brackets]` make the accent pill | none (talk mode derives one) |
| `outro_text` | string | none |
| `music` | library, generate, none | library |
| `music_volume` | number | 0.5 |
| `max_duration` | seconds | 60 |
| `grade` | true, false | true |
| `auto_approve` | true, false | false |
| `transcript_fixes` | list of `[regex, replacement]` pairs | [] |

## Operations

- **One GPU worker.** Jobs run in order. Every pipeline run is a separate process, killed after `REELFORGE_JOB_TIMEOUT_S` (default 3 h).
- **Restart-safe.** On start the server re-queues `queued`/`running`/`rendering` jobs. Each resumes from its last finished stage, because stages are fingerprinted.
- **Files per job:**
  - `jobs/<id>/job.json`: state
  - `pipeline.log`: full log
  - `build/logs/`: per-run logs
  - `build/state.json`: stage state
  - `build/style/style.json`: what was learned
  - `build/preview/`: checkpoint images
  - `build/final/`: the video
  - `build/audit/audit.json`: format and loudness verification
- **Clean-up:** remove `jobs/<id>` when the result has been delivered. Nothing outside it is written per job.
- **Limits** (environment variables):

  | Variable | Default |
  |---|---|
  | `REELFORGE_MAX_UPLOAD_MB` | 1024 |
  | `REELFORGE_MAX_FOOTAGE_S` | 600 |
  | `REELFORGE_MAX_REFERENCE_S` | 300 |
  | `REELFORGE_MAX_FOOTAGE_FILES` | 10 |
  | `REELFORGE_JOB_TIMEOUT_S` | 3 h |
  | `REELFORGE_JOBS_DIR` | `jobs/` |

- **GPU:**
  - HyperFrames captures with hardware Chrome and encodes with NVENC (`--gpu`).
  - Whisper, EasyOCR and MusicGen use CUDA.
  - On Windows hybrid-GPU laptops the render stage pins headless Chrome to the discrete GPU.

## Security

- **API key:** required, compared in constant time. The server refuses to start serving jobs without one, unless `REELFORGE_DEV=1`.
- **Uploads:**
  - Streamed to disk with a size cap.
  - Extension allow-list.
  - Must be readable by `ffprobe`, with a video stream, sane duration and resolution.
  - Stored under generated names. The user's file names are never used as paths.
- **File serving:** jobs are addressed by a strict id pattern. Files are served only from that job's preview/final/audit folders (path traversal blocked).
- **No URL fetching:** the API takes files only, which avoids server-side request forgery. yt-dlp URL references are CLI-only.
- **Untrusted media and text:** uploaded videos are only ever decoded by ffmpeg/OpenCV. Every user-typed or transcribed string (hook, outro, captions, list items, keywords) is HTML-escaped before it reaches the render page, so it can't inject markup or script into the headless browser. User text is also length-limited.

## Licensing — check before launch

- **MusicGen weights are CC-BY-NC 4.0 (non-commercial).** The placeholder library in `assets/music/library` and `music: generate` use them. Put commercially licensed tracks in the library before launch.
- **Reference videos belong to their owners.** They are only analysed, never copied into the output, and their audio is never used.
- **Third-party components:** Whisper (MIT), EasyOCR (Apache-2.0), YuNet face model (MIT, OpenCV zoo), GSAP 3.14 (free "no-charge" licence since GSAP 3.13), FFmpeg (LGPL/GPL build from gyan.dev), HyperFrames CLI (check its licence for your use).

## Known limits

- **Fonts are matched by shape** to HyperFrames' bundled families, not identified exactly.
- **Transition detection** recognises flash, blur/whip, punch and cut. Exotic shader transitions in a reference are approximated by the nearest of these.
- **Montage mode** cuts clips in order at the reference's rhythm. It does not pick "best moments".
- **Speech:** talking-head editing needs clear speech. Non-English speech gets English captions by default (sentence-window translation, timed on the real speech).
- **Docker:** `deploy/Dockerfile` is written for Linux GPU hosts but was not built here (no Docker on the development machine).
