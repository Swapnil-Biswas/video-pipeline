"""Stage 1 · ingest: bring reference videos and raw footage into build/<name>/ingest and probe them.

References come from a URL (yt-dlp, as in the original session) or a local file.
Footage is copied, optionally trimmed and normalised to H.264 so the HTML renderer can seek it."""
from __future__ import annotations

import sys
from pathlib import Path

from ..util import PipelineError, ffprobe_json, log, run, write_json

YTDLP_FMT = "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]/b"   # original used <=720 for YouTube


def _fetch(url: str, out_stem: Path, item: int | None = None) -> Path:
    existing = sorted(out_stem.parent.glob(out_stem.name + ".*"))
    vids = [p for p in existing if p.suffix in (".mp4", ".mkv", ".webm", ".mov")]
    if vids:
        log.info("  cached %s", vids[0].name)
        return vids[0]
    log.info("  downloading %s%s", url, f" (item {item})" if item else "")
    sel = ["--playlist-items", str(int(item))] if item else ["--no-playlist"]   # multi-video posts: pick one item
    run([sys.executable, "-m", "yt_dlp", "-q", *sel, "-f", YTDLP_FMT, "--merge-output-format", "mp4",
         "-o", str(out_stem) + ".%(ext)s", "--write-info-json", url], timeout=900)
    vids = [p for p in out_stem.parent.glob(out_stem.name + ".*") if p.suffix in (".mp4", ".mkv", ".webm", ".mov")]
    if not vids:
        raise PipelineError(f"yt-dlp produced no video for {url}")
    return vids[0]


def _normalise(src: Path, dst: Path, trim: list | None, fps: int) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if trim:
        args += ["-ss", str(trim[0])]
    args += ["-i", str(src)]
    if trim and len(trim) > 1 and trim[1] is not None:
        args += ["-t", str(float(trim[1]) - float(trim[0]))]
    # first video + first audio stream only; phone rotation is applied (ffmpeg autorotate); even dimensions, at most 4K;
    # constant frame rate (variable-frame-rate phone clips would drift against the timeline)
    args += ["-map", "0:v:0", "-map", "0:a:0?", "-vf", "scale='trunc(min(iw,3840)/2)*2':-2,setsar=1",
             "-c:v", "libx264", "-preset", "medium", "-crf", "14", "-pix_fmt", "yuv420p", "-r", str(fps),
             "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", str(dst)]
    run(args, timeout=1800)
    return dst


def run_stage(p) -> dict:
    out = p.build / "ingest"
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"references": [], "footage": []}
    for i, r in enumerate(p.cfg.get("references") or []):
        stem = out / "refs" / f"ref{i + 1}"
        stem.parent.mkdir(parents=True, exist_ok=True)
        if r.get("url"):
            path = _fetch(r["url"], stem, r.get("item"))
        else:
            src = p.path(r["src"])
            if not src.exists():
                raise PipelineError(f"reference not found: {src}")
            path = stem.with_suffix(src.suffix)
            if not path.exists() or path.stat().st_size != src.stat().st_size:
                run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-c", "copy", str(path)])
        if r.get("trim") or r.get("crop"):
            # only part of the reference is the style to learn (e.g. one side of a before/after split screen)
            cut = stem.parent / f"{stem.name}_part.mp4"
            vf = []
            if r.get("crop"):
                x, y, w, h = (float(v) for v in r["crop"])
                if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 - x + 1e-6 and 0 < h <= 1 - y + 1e-6):
                    raise PipelineError(f"reference {i + 1}: crop must be [x, y, w, h] fractions inside the frame")
                vf.append(f"crop=trunc(iw*{w}/2)*2:trunc(ih*{h}/2)*2:trunc(iw*{x}):trunc(ih*{y})")
            args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
            if r.get("trim"):
                args += ["-ss", str(float(r["trim"][0])), "-to", str(float(r["trim"][1]))]
            args += ["-i", str(path)] + (["-vf", ",".join(vf)] if vf else []) + \
                    ["-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(cut)]
            run(args, timeout=900)
            log.info("  reference %d: using %s%s", i + 1, f"{r['trim'][0]}-{r['trim'][1]}s" if r.get("trim") else "the full length",
                     f", crop {r['crop']}" if r.get("crop") else "")
            path = cut
        info = ffprobe_json(path)
        manifest["references"].append({"path": str(path), "source": r.get("url") or r.get("src"), "probe": info})
        log.info("  reference %d: %s (%.1fs)", i + 1, path.name, float(info["format"]["duration"]))
    for i, f in enumerate(p.cfg.get("footage") or []):
        fid = f.get("id") or f"clip{i + 1}"
        if f.get("url"):
            src = _fetch(f["url"], out / "footage_src" / fid)
        else:
            src = p.path(f["src"])
            if not src.exists():
                raise PipelineError(f"footage not found: {src}")
        dst = out / "footage" / f"{fid}.mp4"
        if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
            log.info("  footage %s <- %s %s", fid, src.name, f.get("trim") or "")
            _normalise(src, dst, f.get("trim"), p.fps)
        info = ffprobe_json(dst)
        manifest["footage"].append({"id": fid, "path": str(dst), "source": str(src), "probe": info,
                                    "has_audio": any(s["codec_type"] == "audio" for s in info["streams"])})
    write_json(out / "manifest.json", manifest)
    return {"manifest": str(out / "manifest.json")}
