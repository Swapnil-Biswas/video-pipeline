"""Stage 10 · master: two-pass EBU R128 loudness normalisation; the video stream is copied untouched.

Original: loudnorm=I=-14:TP=-1.5:LRA=11 (measure) -> loudnorm ...:linear=true,alimiter=limit=0.84:level=false,
AAC 320k 48 kHz, -c:v copy -movflags +faststart."""
from __future__ import annotations

import json
import re
import shutil

from ..util import PipelineError, ffprobe_json, log, run


def run_stage(p) -> dict:
    m = p.cfg["master"]
    raw = p.build / "render" / "raw.mp4"
    if not raw.exists():
        raise PipelineError("run render first")
    out_dir = p.build / "final"
    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / f"{p.name}_{p.cfg['render']['resolution']}_{p.fps}fps.mp4"
    has_audio = any(s["codec_type"] == "audio" for s in ffprobe_json(raw)["streams"])
    if not has_audio:
        shutil.copy2(raw, final)
        log.info("  no audio stream; copied")
        return {"final": str(final)}
    target = f"I={m['lufs']}:TP={m['true_peak']}:LRA={m['lra']}"
    r = run(["ffmpeg", "-hide_banner", "-i", str(raw), "-af", f"loudnorm={target}:print_format=json", "-f", "null", "-"])
    txt = r.stdout + r.stderr
    js = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", txt, re.S).group(0))
    meas = (f"measured_I={js['input_i']}:measured_TP={js['input_tp']}:measured_LRA={js['input_lra']}:"
            f"measured_thresh={js['input_thresh']}:offset={js['target_offset']}")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), "-c:v", "copy", "-af",
         f"loudnorm={target}:{meas}:linear=true,alimiter=limit={m['limiter']}:level=false", "-ar", str(m["sample_rate"]),
         "-c:a", "aac", "-b:a", m["aac_bitrate"], "-movflags", "+faststart", str(final)])
    log.info("  mastered: input %s LUFS -> target %s LUFS", js["input_i"], m["lufs"])
    return {"final": str(final), "input_lufs": float(js["input_i"])}
