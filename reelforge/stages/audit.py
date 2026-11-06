"""Stage 11 · audit: verify the delivered file (format, duration, loudness) and make contact sheets for sign-off."""
from __future__ import annotations

import re
from pathlib import Path

from ..util import PipelineError, ffprobe_json, log, run, write_json
from .analyze import contact_sheets


def run_stage(p) -> dict:
    finals = sorted((p.build / "final").glob("*.mp4"))
    if not finals:
        raise PipelineError("run master first")
    f = max(finals, key=lambda x: x.stat().st_mtime)
    info = ffprobe_json(f)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    num, den = v["r_frame_rate"].split("/")
    rep = {"file": str(f), "size_mb": round(int(info["format"]["size"]) / 2**20, 1), "codec": v["codec_name"],
           "width": v["width"], "height": v["height"], "fps": round(int(num) / int(den), 3),
           "duration": round(float(info["format"]["duration"]), 3), "audio": bool(a)}
    issues = []
    from ..config import RES_PRESETS
    ew, eh = RES_PRESETS[p.cfg["render"]["resolution"]]
    if (v["width"], v["height"]) != (ew, eh):
        issues.append(f"resolution {v['width']}x{v['height']} != {ew}x{eh}")
    if abs(rep["fps"] - p.fps) > 0.01:
        issues.append(f"fps {rep['fps']} != {p.fps}")
    if abs(rep["duration"] - p.duration) > 2.0 / p.fps + 0.05:
        issues.append(f"duration {rep['duration']} != {p.duration:.3f}")
    if a:
        r = run(["ffmpeg", "-hide_banner", "-i", str(f), "-af", "ebur128=peak=true", "-f", "null", "-"])
        txt = (r.stdout + r.stderr).split("Summary:")[-1]
        i = re.search(r"I:\s+(-?[\d.]+) LUFS", txt)
        pk = re.search(r"Peak:\s+(-?[\d.]+) dBFS", txt)
        rep["lufs"] = float(i.group(1)) if i else None
        rep["true_peak_dbfs"] = float(pk.group(1)) if pk else None
        if rep["lufs"] is not None and abs(rep["lufs"] - p.cfg["master"]["lufs"]) > 1.0:
            issues.append(f"loudness {rep['lufs']} LUFS off target {p.cfg['master']['lufs']}")
        if rep["true_peak_dbfs"] is not None and rep["true_peak_dbfs"] > p.cfg["master"]["true_peak"] + 0.3:
            issues.append(f"peak {rep['true_peak_dbfs']} dBFS above {p.cfg['master']['true_peak']}")
    au = p.cfg["audit"]
    rep["sheets"] = contact_sheets(f, p.build / "audit", "final_sheet", au["sheet_fps"], au["sheet_width"], au["sheet_tile"],
                                   au["sheet_tile"][0] * au["sheet_tile"][1] / au["sheet_fps"], rep["duration"])
    thumb = p.build / "final" / f"{f.stem}_thumb.jpg"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(min(rep["duration"] * 0.3, rep["duration"] - 0.1)),
         "-i", str(f), "-frames:v", "1", "-vf", "scale=1280:-2", str(thumb)])
    rep["thumbnail"] = str(thumb)
    rep["issues"] = issues
    write_json(p.build / "audit" / "audit.json", rep)
    log.info("  %s: %sx%s %s fps %.3fs, %s LUFS, peak %s dBFS, %.1f MB", f.name, rep["width"], rep["height"], rep["fps"],
             rep["duration"], rep.get("lufs"), rep.get("true_peak_dbfs"), rep["size_mb"])
    for x in issues:
        log.warning("  AUDIT ISSUE: %s", x)
    log.info("  CHECKPOINT: sign off on the final contact sheets in %s", p.build / "audit")
    if issues:
        raise PipelineError("audit found issues: " + "; ".join(issues))
    return rep
