"""Stage 4 · voice: a voice-over track plus word timings (for captions and music ducking).

mode file   : use a supplied wav (+ optional words.json [{text,start,end}]).
mode heygen : synthesise each line with HeyGen TTS through the media-use skill script (as in films 1-3;
              needs `npx hyperframes auth login` once), speed it up, trim to its words, place lines with gaps
              and run the original voice chain (ported from video-reel/tools/vo_reel.py)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from ..util import PipelineError, log, media_duration, read_json, run, write_json


def _heygen_line(p, line: dict, dst: Path) -> Path:
    v = p.cfg["voice"]
    script = Path(os.path.expanduser(v["heygen_script"]))
    if not script.exists():
        raise PipelineError(f"HeyGen TTS script not found: {script} (install the HyperFrames media-use skill)")
    words = dst.with_suffix(".words.json")
    if dst.exists() and words.exists():
        return dst
    args = ["node", str(script), line["text"], "--voice", line.get("voice_id") or v["voice_id"], "-o", str(dst), "--words", str(words)]
    if v.get("lang"):
        args += ["--lang", v["lang"]]
    if v.get("speed") and float(v["speed"]) != 1.0:
        args += ["--speed", str(v["speed"])]
    log.info("  HeyGen: %s", line["text"][:60])
    run(args, timeout=300)
    return dst


def assemble(p, pieces: list[tuple[Path, list, float]], out_dir: Path) -> tuple[Path, list]:
    import numpy as np
    import soundfile as sf
    v = p.cfg["voice"]
    SR, speed = 48000, float(v.get("atempo") or 1.0)
    track, words, t = [], [], 0.0
    for i, (wav, ws, gap) in enumerate(pieces):
        fast = out_dir / f"line{i}_fast.wav"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav), "-af", f"atempo={speed},aresample={SR}", "-ac", "1", str(fast)])
        y, sr = sf.read(fast)
        if ws:
            s0 = max(0.0, ws[0]["start"] / speed - 0.03)
            s1 = min(len(y) / sr, ws[-1]["end"] / speed + 0.08)
        else:
            s0, s1 = 0.0, len(y) / sr
        t += gap
        track.append(np.zeros(int(round(gap * sr))))
        seg = y[int(s0 * sr): int(s1 * sr)].copy()
        n = min(len(seg) // 2, int(0.01 * sr))
        if n:
            seg[:n] *= np.linspace(0, 1, n)
            seg[-n:] *= np.linspace(1, 0, n)
        track.append(seg)
        for w in ws:
            words.append({"text": w["text"], "start": round(t + w["start"] / speed - s0, 3), "end": round(t + w["end"] / speed - s0, 3), "line": i})
        t += len(seg) / sr
    raw = out_dir / "vo_raw.wav"
    sf.write(raw, np.concatenate(track), SR)
    out = out_dir / "vo.wav"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), "-af", v["chain"] + ",aresample=48000", str(out)])
    return out, words


def run_stage(p) -> dict:
    v = p.cfg["voice"]
    out = p.build / "voice"
    if v["mode"] == "none":
        shutil.rmtree(out, ignore_errors=True)
        return {"vo": None}
    out.mkdir(parents=True, exist_ok=True)
    if v["mode"] == "file":
        src = p.path(v["file"])
        if not src.exists():
            raise PipelineError(f"voice.file not found: {src}")
        vo = out / "vo.wav"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-ar", "48000", str(vo)])
        words = read_json(p.path(v["words"]), []) if v.get("words") else []
    else:
        if not v.get("lines"):
            raise PipelineError("voice.mode=heygen needs voice.lines")
        pieces = []
        for i, line in enumerate(v["lines"]):
            wav = _heygen_line(p, line, out / f"{line.get('id', f'line{i}')}.wav")
            ws = read_json(wav.with_suffix(".words.json"), [])
            pieces.append((wav, ws, float(line.get("gap", 0.2 if i else 0.05))))
        vo, words = assemble(p, pieces, out)
    off = float(v.get("start") or 0.0)
    words = [{**w, "start": round(w["start"] + off, 3), "end": round(w["end"] + off, 3)} for w in words]
    write_json(out / "words.json", words)
    d = media_duration(vo)
    if off + d > p.duration + 0.05:
        log.warning("  voice runs to %.2fs, past the film end %.2fs", off + d, p.duration)
    log.info("  voice %.2fs at %.2fs, %d words", d, off, len(words))
    return {"vo": str(vo), "words": str(out / "words.json"), "duration": d}
