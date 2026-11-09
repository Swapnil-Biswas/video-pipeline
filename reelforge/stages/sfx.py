"""Stage 6 · sfx: write the <!-- AUDIO --> block: music (with ducking automation), voice, and every SFX cue.

Each cue starts at picture_time + frame_offset/fps - PEAK[file]
so the sound's peak lands one frame after the picture event; cues are packed greedily into lanes."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..util import PipelineError, log, media_duration, npx, num, read_json, write_json

# seconds from file start to its peak, measured in the original session with `hyperframes audio --json`
ORIGINAL_PEAKS = {"click": .09, "click-soft": .09, "click-lo": .09, "impact-bass-1": .10, "impact-bass-2": 1.83, "key-press": .12,
                  "pop": .15, "pop-hi": .14, "pop-lo": .19, "stamp": .10, "typing": 0.0, "whoosh-cinematic": 2.90, "whoosh": .17,
                  "whoosh-short": .17, "whoosh-hi": .15, "whoosh-lo": .20, "glitch-3": .62, "ping": .36}


def measure_peak(p, f: Path) -> float:
    r = npx(["audio", str(f), "--json"], cwd=p.hf, check=False, timeout=120)
    try:
        d = json.loads(r.stdout[r.stdout.index("{"):])
        return float(d["items"][0]["moments"]["peak"])
    except Exception:
        log.warning("  could not measure the peak of %s; assuming 0.1 s", f.name)
        return 0.1


def run_stage(p) -> dict:
    hf = p.hf
    idx_path = hf / "index.html"
    if not idx_path.exists():
        raise PipelineError("run compose first")
    sx = p.cfg["sfx"]
    fps, total = p.fps, float(num(p.duration))
    F = sx.get("frame_offset", 1) / fps
    auto = read_json(p.build / "compose" / "cues.json", {"cues": [], "ducks": []})
    cues = (auto["cues"] if sx.get("auto", True) else []) + [list(c) for c in (sx.get("cues") or [])]
    sfx_dir = hf / "assets" / "sfx"
    peaks_cache = p.build / "sfx" / "peaks.json"
    peaks = {**ORIGINAL_PEAKS, **(read_json(peaks_cache, {}) or {}), **(sx.get("peaks") or {})}
    durs = {}
    for f, t, v in cues:
        path = sfx_dir / f"{f}.mp3"
        if not path.exists():
            raise PipelineError(f"sfx file not found: {path} (add it to an assets folder named sfx)")
        if f not in peaks:
            peaks[f] = measure_peak(p, path)
        if f not in durs:
            durs[f] = media_duration(path)
    write_json(peaks_cache, {k: v for k, v in peaks.items() if k not in ORIGINAL_PEAKS})

    tags = []
    m = p.cfg["music"]
    from .compose import speech_words
    vo_words = speech_words(p) if m["duck"].get("under_speech", True) else []
    if m["mode"] != "none":
        vol = float(m["volume"])
        pts = [{"t": 0, "v": 1}]
        events = []
        if m["duck"]["at_clicks"]:
            for c in auto.get("ducks", []) + list(m.get("duck_at") or []):
                events.append((c - 0.05, c - 0.01, c + 0.1, c + 0.22, float(m["duck"]["level"])))
        if vo_words:  # sit the music under the voice / dialogue (phrases merged when gaps < 0.6 s)
            under = float(m["volume_under_voice"]) / vol
            spans = []
            for w in vo_words:
                if spans and w["start"] - spans[-1][1] < 0.6:
                    spans[-1][1] = w["end"]
                else:
                    spans.append([w["start"], w["end"]])
            for a, b in spans:
                events.append((a - 0.25, a - 0.05, b + 0.05, b + 0.35, under))
        for a0, a1, b0, b1, lv in sorted(events):
            pts += [{"t": round(max(0.0, a0), 3), "v": 1}, {"t": round(max(0.0, a1), 3), "v": round(lv, 3)},
                    {"t": round(b0, 3), "v": round(lv, 3)}, {"t": round(b1, 3), "v": 1}]
        pts.sort(key=lambda x: x["t"])
        auto_attr = json.dumps({"version": 1, "lanes": [{"target": "volume", "points": pts}]}).replace('"', "&quot;")
        tags.append(f'      <audio id="music" class="clip" src="assets/music/bed.wav" data-start="0" data-duration="{num(total)}" '
                    f'data-track-index="10" data-volume="{vol}" data-automation="{auto_attr}"></audio>')
    ar = (p.cfg.get("aroll") or {}).get("video")
    if ar:  # the dialogue, re-cut to match the picture: one clip per kept span, tiny edge fades against clicks
        if p.auto:
            ranges = p.plan()["aroll_ranges"]
        else:
            ranges = [{"film": 0.0, "src": float((p.cfg.get("aroll") or {}).get("start") or 0), "dur": total}]
        src_dur = media_duration(hf / "assets" / "footage" / f"{ar}_dialog.wav")
        for i, r in enumerate(ranges):
            d = round(min(r["dur"], src_dur - r["src"], total - r["film"]), 3)
            if d <= 0.02:
                continue
            tags.append(f'      <audio id="dlg{i}" class="clip" src="assets/footage/{ar}_dialog.wav" data-start="{num(r["film"])}" '
                        f'data-duration="{num(d)}" data-media-start="{num(r["src"])}" data-track-index="8" data-volume="1" '
                        f'data-fade-in="0.012" data-fade-out="0.012"></audio>')
    if p.cfg["voice"]["mode"] != "none":
        vs = float(p.cfg["voice"].get("start") or 0)
        vd = round(min(media_duration(hf / "assets" / "voice" / "vo.wav"), total - vs), 3)
        tags.append(f'      <audio id="voice" class="clip" src="assets/voice/vo.wav" data-start="{vs}" data-duration="{vd}" '
                    f'data-track-index="9" data-volume="{p.cfg["voice"]["volume"]}"></audio>')
    lanes = []
    placed = 0
    for i, (f, t, v) in enumerate(cues):        # given order (ids and lane packing match the original audio.py)
        start = max(0.0, round(t + F - peaks[f], 3))
        if start >= total - 0.02:
            log.warning("  cue %s at %.2fs is past the film end; skipped", f, t)
            continue
        d = round(min(durs[f] - 0.01, total - start, 0.7 if f == "typing" else 99), 3)
        lane = next((k for k, e in enumerate(lanes) if e <= start), None)
        if lane is None:
            lanes.append(0.0)
            lane = len(lanes) - 1
        lanes[lane] = start + d
        tags.append(f'      <audio id="sx{i}" class="clip" src="assets/sfx/{f}.mp3" data-start="{start}" data-duration="{d}" '
                    f'data-track-index="{11 + lane}" data-volume="{v}"></audio>')
        placed += 1
    idx = idx_path.read_text(encoding="utf-8")
    idx, n = re.subn(r"<!-- AUDIO -->.*?<!-- /AUDIO -->", lambda _: "<!-- AUDIO -->\n" + "\n".join(tags) + "\n      <!-- /AUDIO -->", idx, flags=re.S)
    if n != 1:
        raise PipelineError("index.html has no <!-- AUDIO --> block")
    idx_path.write_text(idx, encoding="utf-8", newline="\n")
    log.info("  %d sfx cues in %d lanes%s%s", placed, len(lanes), ", music" if m["mode"] != "none" else "",
             ", voice" if p.cfg["voice"]["mode"] != "none" else "")
    return {"cues": placed, "lanes": len(lanes)}
