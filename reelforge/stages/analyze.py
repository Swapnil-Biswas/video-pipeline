"""Stage 2 · analyze: turn each reference into numbers and pictures the editor (human or AI) can read.

Original method: ffprobe; scene cuts with select='gt(scene,0.25)'; 4 fps timestamped contact sheets;
librosa tempo / beats / RMS per 0.5 s / strong onsets / band energy share."""
from __future__ import annotations

import re
from pathlib import Path

from ..util import PipelineError, log, read_json, run, write_json


def contact_sheets(video: Path, out_dir: Path, prefix: str, fps: float, width: int, tile: list, seconds: float,
                   duration: float) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cols, rows = tile
    sheets, t, i = [], 0.0, 0
    while t < duration - 0.01:
        dst = out_dir / f"{prefix}{i}.jpg"
        # timestamp burned in so findings can be quoted by time (original audits did the same)
        draw = (f"drawtext=text='%{{pts\\:hms\\:{t:.3f}}}':x=8:y=8:fontsize={max(14, width // 24)}:fontcolor=white:box=1:boxcolor=black@0.6:"
                f"fontfile='C\\:/Windows/Fonts/consola.ttf'") if Path("C:/Windows/Fonts/consola.ttf").exists() else None
        vf = f"fps={fps},scale={width}:-2" + (f",{draw}" if draw else "") + f",tile={cols}x{rows}"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-t", f"{seconds:.3f}", "-i", str(video),
             "-vf", vf, "-frames:v", "1", "-q:v", "3", str(dst)])
        sheets.append(str(dst))
        t += seconds
        i += 1
    return sheets


def scene_cuts(video: Path, threshold: float) -> list[float]:
    p = run(["ffmpeg", "-hide_banner", "-i", str(video), "-vf", f"select='gt(scene,{threshold})',showinfo", "-an",
             "-f", "null", "-"], check=False)
    return [round(float(x), 3) for x in re.findall(r"pts_time:([0-9.]+)", p.stdout + p.stderr)]


def audio_analysis(video: Path, wav: Path, cfg: dict) -> dict:
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "22050", str(wav)],
        check=False)
    if not wav.exists() or wav.stat().st_size < 1000:
        return {"has_audio": False}
    import librosa
    import numpy as np
    y, sr = librosa.load(str(wav), sr=22050)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    bt = librosa.frames_to_time(beats, sr=sr)
    rms = librosa.feature.rms(y=y, hop_length=sr // 2)[0]
    onsets = librosa.onset.onset_detect(y=y, sr=sr, units="time", delta=cfg["onset_delta"])
    S = np.abs(librosa.stft(y, n_fft=4096))
    f = librosa.fft_frequencies(sr=sr, n_fft=4096)
    bands = {f"{lo}-{hi}": round(float(S[(f >= lo) & (f < hi)].sum() / S.sum() * 100), 1) for lo, hi in cfg["bands"]}
    db = [round(float(20 * np.log10(x + 1e-9)), 1) for x in rms]
    # loudest rise = likely drop: largest increase of 2 s mean energy
    w = 4
    means = [float(np.mean(db[i:i + w])) for i in range(0, max(1, len(db) - w))]
    rises = [(means[i + w] - means[i], i) for i in range(0, max(0, len(means) - w))]
    drop = round((max(rises)[1] + w) * 0.5, 2) if rises else None
    return {"has_audio": True, "tempo_bpm": round(float(np.atleast_1d(tempo)[0]), 1), "beats": [round(float(b), 3) for b in bt],
            "rms_db_per_0_5s": db, "strong_onsets": [round(float(o), 3) for o in onsets], "band_share_pct": bands,
            "likely_drop_s": drop}


def run_stage(p) -> dict:
    man = read_json(p.build / "ingest" / "manifest.json")
    if man is None:
        raise PipelineError("run ingest first")
    out = p.build / "analyze"
    a = p.cfg["analyze"]
    result = []
    for i, r in enumerate(man["references"]):
        v = Path(r["path"])
        st = {s["codec_type"]: s for s in r["probe"]["streams"]}
        dur = float(r["probe"]["format"]["duration"])
        vs = st.get("video", {})
        num, den = (vs.get("r_frame_rate", "0/1").split("/") + ["1"])[:2]
        info = {"file": v.name, "duration": round(dur, 3), "width": vs.get("width"), "height": vs.get("height"),
                "fps": round(float(num) / float(den or 1), 3) if float(den or 1) else None}
        log.info("  ref%d: %.1fs %sx%s @ %s fps", i + 1, dur, info["width"], info["height"], info["fps"])
        info["cuts"] = scene_cuts(v, a["scene_threshold"])
        if len(info["cuts"]) > 1:
            gaps = [b - a_ for a_, b in zip([0.0] + info["cuts"], info["cuts"] + [dur])]
            info["avg_shot_s"] = round(sum(gaps) / len(gaps), 2)
        info["sheets"] = contact_sheets(v, out, f"ref{i + 1}_sheet", a["sheet_fps"], a["sheet_width"], a["sheet_tile"],
                                        a["sheet_seconds"], dur)
        info["audio"] = audio_analysis(v, out / f"ref{i + 1}.wav", a)
        if info["audio"].get("has_audio"):
            log.info("    tempo %.1f BPM, %d strong onsets, likely drop %.2fs", info["audio"]["tempo_bpm"],
                     len(info["audio"]["strong_onsets"]), info["audio"]["likely_drop_s"] or -1)
        log.info("    %d cuts, %d contact sheets", len(info["cuts"]), len(info["sheets"]))
        result.append(info)
    write_json(out / "analysis.json", {"references": result})
    (out / "STYLE_NOTES_PROMPT.md").write_text(p.prompts["review"]["style_notes"], encoding="utf-8")
    return {"analysis": str(out / "analysis.json")}
