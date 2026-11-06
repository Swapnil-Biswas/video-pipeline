"""Stage · style: learn a reference video's editing style and turn it into settings for this project.

Measured from the reference (no guessing from file names):
  pacing        shot lengths from scene cuts -> jump-cut rhythm (autoedit min/max shot, punch cadence)
  transitions   what happens at each cut: white flash (luma spike), blur/whip (sharpness dip), jump/punch
                (same scene re-framed), hard cut -> weights the auto-edit draws transitions from
  energy        frame-to-frame motion -> punch-in strength, overlay density, music energy
  palette       k-means colours (Lab) -> dark world, light world, accent; contrast-checked
  grade         luma, contrast, saturation, warmth, shadow/highlight tints, vignette vs the user's footage ->
                a HyperFrames realtime grading payload (data-color-grading) for the footage
  text          EasyOCR on sampled frames -> caption presence, position, size, case, words per caption,
                text/highlight colours, condensed vs wide letterforms -> caption style + display font
  audio         tempo, drop, onset density, brightness (from analyze) -> music BPM / prompt / drop
Writes build/<name>/style/style.json {measured, theme, edit, captions, grade, music}. Later stages read it
(project.yaml values always win: anything set there is not overridden by the reference)."""
from __future__ import annotations

import math
from pathlib import Path

from ..theme import BUNDLED_FONTS, DEFAULT_THEME, contrast, hex_to_rgb, readable_on, rgb_to_hex, shade
from ..util import PipelineError, log, read_json, write_json


# ---------------------------------------------------------------- frame sampling
def sample_frames(video: Path, fps: float, width: int, max_frames: int = 400):
    import cv2
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise PipelineError(f"cannot decode {video.name}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, int(round(src_fps / fps)))
    frames, times, i = [], [], 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if i % step == 0:
            ok, f = cap.retrieve()
            if not ok:
                break
            h, w = f.shape[:2]
            f = cv2.resize(f, (width, int(round(h * width / w))), interpolation=cv2.INTER_AREA)
            frames.append(f)
            times.append(i / src_fps)
            if len(frames) >= max_frames:
                break
        i += 1
    cap.release()
    if not frames:
        raise PipelineError(f"no frames decoded from {video.name}")
    return frames, times, src_fps, n


def frame_stats(frames):
    import cv2
    import numpy as np
    lum, sharp, sat, warm = [], [], [], []
    for f in frames:
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        lum.append(float(g.mean()))
        sharp.append(float(cv2.Laplacian(g, cv2.CV_64F).var()))
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
        sat.append(float(hsv[..., 1].mean()))
        b, _, r = [c.astype(np.float32) for c in cv2.split(f)]
        warm.append(float((r - b).mean()))
    return lum, sharp, sat, warm


# ---------------------------------------------------------------- measurements
def measure_pacing(cuts, dur):
    import numpy as np
    edges = [0.0] + [c for c in cuts if 0.15 < c < dur - 0.15] + [dur]
    shots = [b - a for a, b in zip(edges, edges[1:]) if b - a > 0.08]
    if len(shots) < 2:
        return {"cuts": len(cuts), "avg_shot": round(dur, 2), "median_shot": round(dur, 2), "cuts_per_min": 0.0, "shots": shots}
    return {"cuts": len(shots) - 1, "avg_shot": round(float(np.mean(shots)), 2), "median_shot": round(float(np.median(shots)), 2),
            "p25_shot": round(float(np.percentile(shots, 25)), 2), "p75_shot": round(float(np.percentile(shots, 75)), 2),
            "cuts_per_min": round((len(shots) - 1) / dur * 60, 1), "shots": [round(s, 2) for s in shots]}


def measure_transitions(cuts, times, frames, lum, sharp):
    """Classify each cut from the frames around it."""
    import cv2
    import numpy as np
    counts = {"cut": 0, "flash": 0, "blur": 0, "punch": 0}
    T = np.array(times)
    med_sharp = float(np.median(sharp)) or 1.0
    for c in cuts:
        i = int(np.argmin(np.abs(T - c)))
        lo, hi = max(0, i - 3), min(len(frames) - 1, i + 3)
        around = lum[lo:hi + 1]
        base = (np.mean(lum[max(0, lo - 4):lo + 1]) + np.mean(lum[hi:min(len(lum), hi + 5)])) / 2
        after = lum[min(len(lum) - 1, hi + 2):min(len(lum), hi + 6)]
        peak = max(around)
        if peak > 200 and peak - base > 45 and after and peak - float(np.mean(after)) > 40:
            counts["flash"] += 1
            continue
        if min(sharp[lo:hi + 1]) < 0.3 * med_sharp:
            counts["blur"] += 1
            continue
        a, b = frames[max(0, i - 1)], frames[min(len(frames) - 1, i + 1)]
        ha = cv2.calcHist([cv2.cvtColor(a, cv2.COLOR_BGR2HSV)], [0, 1], None, [24, 16], [0, 180, 0, 256])
        hb = cv2.calcHist([cv2.cvtColor(b, cv2.COLOR_BGR2HSV)], [0, 1], None, [24, 16], [0, 180, 0, 256])
        cv2.normalize(ha, ha)
        cv2.normalize(hb, hb)
        if cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL) > 0.9:
            counts["punch"] += 1          # same scene, re-framed: a jump cut / punch-in
        else:
            counts["cut"] += 1
    tot = max(1, sum(counts.values()))
    return {"counts": counts, "weights": {k: round(v / tot, 3) for k, v in counts.items()}}


def measure_motion(frames):
    import cv2
    import numpy as np
    d = []
    for a, b in zip(frames, frames[1:]):
        ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
        gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
        d.append(float(np.mean(cv2.absdiff(ga, gb))))
    d = np.array(d) if d else np.zeros(1)
    # robust energy 0..1: median motion between frames sampled at ~4 fps
    return {"median_diff": round(float(np.median(d)), 2), "p90_diff": round(float(np.percentile(d, 90)), 2),
            "energy": round(float(min(1.0, np.median(d) / 25.0)), 3)}


def measure_palette(frames, k=7):
    import cv2
    import numpy as np
    from sklearn.cluster import KMeans
    px = np.concatenate([cv2.resize(f, (64, int(64 * f.shape[0] / f.shape[1]))).reshape(-1, 3) for f in frames[:: max(1, len(frames) // 60)]])
    lab = cv2.cvtColor(px.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    km = KMeans(n_clusters=k, n_init=4, random_state=0).fit(lab)
    share = np.bincount(km.labels_, minlength=k) / len(lab)
    cols = []
    for c, s in zip(km.cluster_centers_, share):
        bgr = cv2.cvtColor(np.uint8([[c]]), cv2.COLOR_LAB2BGR)[0, 0]
        L, a, b = c[0] * 100 / 255, c[1] - 128, c[2] - 128
        cols.append({"hex": rgb_to_hex(bgr[2], bgr[1], bgr[0]), "share": round(float(s), 4), "L": round(float(L), 1),
                     "chroma": round(float(math.hypot(a, b)), 1)})
    cols.sort(key=lambda x: -x["share"])
    return cols


def measure_accent(frames):
    """The dominant hue among strongly saturated pixels, even if it covers only ~0.3% of the frame."""
    import cv2
    import numpy as np
    sel = []
    for f in frames[:: max(1, len(frames) // 60)]:
        lab = cv2.cvtColor(f, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
        a, b = lab[:, 1] - 128, lab[:, 2] - 128
        L = lab[:, 0] * 100 / 255
        m = (np.hypot(a, b) > 38) & (L > 30) & (L < 88)
        if m.any():
            sel.append(f.reshape(-1, 3)[m])
    total = sum(f.shape[0] * f.shape[1] for f in frames[:: max(1, len(frames) // 60)])
    if not sel:
        return None
    px = np.concatenate(sel)
    if len(px) / total < 0.003:
        return None
    hsv = cv2.cvtColor(px.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    hist = np.bincount((hsv[:, 0] // 6).astype(int), minlength=30)
    best = int(np.argmax(hist))
    m = (hsv[:, 0] // 6) == best
    c = np.median(px[m], axis=0)
    return {"hex": rgb_to_hex(c[2], c[1], c[0]), "share": round(float(m.sum() / total), 4)}


def measure_grade(frames):
    import cv2
    import numpy as np
    L, S, W, flat, vig, sh, hi = [], [], [], [], [], [], []
    for f in frames[:: max(1, len(frames) // 40)]:
        lab = cv2.cvtColor(f, cv2.COLOR_BGR2LAB).astype(np.float32)
        l = lab[..., 0] * 100 / 255
        L.append((float(l.mean()), float(l.std())))
        S.append(float(cv2.cvtColor(f, cv2.COLOR_BGR2HSV)[..., 1].mean()))
        W.append(float((lab[..., 2] - 128).mean()))     # +b = warm
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        lap = np.abs(cv2.Laplacian(g, cv2.CV_32F))
        flat.append(float((lap < 2).mean()))
        h, w = g.shape
        cy, cx = h // 2, w // 2
        center = g[cy - h // 6:cy + h // 6, cx - w // 6:cx + w // 6].mean()
        corners = np.mean([g[:h // 8, :w // 8].mean(), g[:h // 8, -w // 8:].mean(), g[-h // 8:, :w // 8].mean(), g[-h // 8:, -w // 8:].mean()])
        vig.append(float((center - corners) / (center + 1)))
        m_sh, m_hi = l < np.percentile(l, 20), l > np.percentile(l, 80)
        if m_sh.any():
            sh.append((float(lab[..., 1][m_sh].mean() - 128), float(lab[..., 2][m_sh].mean() - 128)))
        if m_hi.any():
            hi.append((float(lab[..., 1][m_hi].mean() - 128), float(lab[..., 2][m_hi].mean() - 128)))
    sh = sh or [(0.0, 0.0)]
    hi = hi or [(0.0, 0.0)]
    sa, sb = np.mean([x[0] for x in sh]), np.mean([x[1] for x in sh])
    ha, hb = np.mean([x[0] for x in hi]), np.mean([x[1] for x in hi])
    return {"luma": round(float(np.mean([x[0] for x in L])), 1), "contrast": round(float(np.mean([x[1] for x in L])), 1),
            "saturation": round(float(np.mean(S)), 1), "warmth": round(float(np.mean(W)), 2),
            "flat_ratio": round(float(np.mean(flat)), 3), "vignette": round(float(np.mean(vig)), 3),
            "shadow_tint": {"hue": round(float(math.degrees(math.atan2(sb, sa)) % 360), 1), "amount": round(float(math.hypot(sa, sb)), 2)},
            "highlight_tint": {"hue": round(float(math.degrees(math.atan2(hb, ha)) % 360), 1), "amount": round(float(math.hypot(ha, hb)), 2)}}


def measure_text(frames, times, gpu: bool):
    """OCR a spread of frames: where captions sit, how big, what case, how many words, colours, letter shape."""
    import cv2
    import numpy as np
    try:
        import easyocr
    except ImportError:
        log.warning("  easyocr not installed: caption style falls back to defaults")
        return {"available": False}
    reader = easyocr.Reader(["en"], gpu=gpu, verbose=False)
    picks = list(range(0, len(frames), max(1, len(frames) // 36)))[:36]
    boxes = []
    for i in picks:
        f = frames[i]
        H, W = f.shape[:2]
        for (pts, txt, conf) in reader.readtext(f):
            if conf < 0.45 or len(txt.strip()) < 2:
                continue
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            x0, x1, y0, y1 = max(0, min(xs)), min(W, max(xs)), max(0, min(ys)), min(H, max(ys))
            h = y1 - y0
            if h < 6:
                continue
            crop = f[int(y0):int(y1), int(x0):int(x1)]
            if crop.size == 0:
                continue
            g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            # text colour = the minority tone in the box, background = majority
            thr, mask = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            fg_light = (mask > 0).mean() < 0.5
            fg = crop[mask > 0] if fg_light else crop[mask == 0]
            bg = crop[mask == 0] if fg_light else crop[mask > 0]
            fgc = fg.mean(axis=0) if len(fg) else np.array([255, 255, 255])
            bgc = bg.mean(axis=0) if len(bg) else np.array([0, 0, 0])
            letters = sum(c.isalnum() for c in txt) or 1
            boxes.append({"t": round(times[i], 2), "text": txt, "yc": (y0 + y1) / 2 / H, "h": h / H, "w": (x1 - x0) / W,
                          "aspect": (x1 - x0) / (letters * h), "upper": sum(c.isupper() for c in txt) / max(1, sum(c.isalpha() for c in txt)),
                          "words": len(txt.split()), "fg": rgb_to_hex(fgc[2], fgc[1], fgc[0]), "bg": rgb_to_hex(bgc[2], bgc[1], bgc[0]),
                          "fill": float(min((mask > 0).mean(), (mask == 0).mean()))})
    if not boxes:
        return {"available": True, "has_text": False}
    frames_with_text = len({b["t"] for b in boxes}) / max(1, len(picks))
    # caption-like: lower 60% of the frame, short lines, appears in many frames with changing content
    cap = [b for b in boxes if 0.45 < b["yc"] < 0.93 and b["words"] <= 6 and b["w"] < 0.95]
    texts = {b["text"].lower() for b in cap}
    captions = len(cap) >= 5 and len(texts) >= max(4, 0.5 * len(cap))
    med = lambda xs, d=0.0: float(np.median(xs)) if xs else d
    src = cap if captions else boxes
    # a coloured background behind caption words (TikTok-style highlight)
    hl = [b for b in src if contrast(b["fg"], b["bg"]) > 3 and _chroma(b["bg"]) > 35]
    return {"available": True, "has_text": True, "frames_with_text": round(frames_with_text, 2), "captions": captions,
            "caption_y": round(med([b["yc"] for b in cap], 0.74), 3), "caption_h": round(med([b["h"] for b in cap], 0.03), 4),
            "words_per_line": round(med([b["words"] for b in src], 3)), "upper_ratio": round(med([b["upper"] for b in src]), 2),
            "letter_aspect": round(med([b["aspect"] for b in src], 0.55), 3), "stroke_fill": round(med([b["fill"] for b in src], 0.2), 3),
            "text_color": _mode_color([b["fg"] for b in src]), "highlight_color": _mode_color([b["bg"] for b in hl]) if len(hl) >= 2 else None,
            "samples": [{k: b[k] for k in ("t", "text", "yc", "h")} for b in boxes[:12]]}


def _chroma(h):
    import cv2
    import numpy as np
    r, g, b = hex_to_rgb(h)
    lab = cv2.cvtColor(np.uint8([[[b, g, r]]]), cv2.COLOR_BGR2LAB)[0, 0].astype(float)
    return math.hypot(lab[1] - 128, lab[2] - 128)


def _mode_color(hexes):
    if not hexes:
        return None
    import numpy as np
    arr = np.array([hex_to_rgb(h) for h in hexes], dtype=float)
    q = (arr // 32).astype(int)
    keys, inv, cnt = np.unique(q, axis=0, return_inverse=True, return_counts=True)
    best = int(np.argmax(cnt))
    m = arr[inv.reshape(-1) == best].mean(axis=0)
    return rgb_to_hex(*m)


# ---------------------------------------------------------------- derive settings
def derive_theme(pal, text, grade, accent_px=None) -> dict:
    T = dict(DEFAULT_THEME)
    T["name"] = "from-reference"
    big = [c for c in pal if c["share"] >= 0.03] or pal
    darks = sorted([c for c in big if c["L"] < 28], key=lambda c: -c["share"])
    lights = sorted([c for c in big if c["L"] > 80], key=lambda c: -c["share"])
    accents = sorted([c for c in pal if c["chroma"] > 28 and 25 < c["L"] < 85 and c["share"] >= 0.008], key=lambda c: -(c["chroma"] * c["share"] ** 0.5))
    if darks:
        d = darks[0]["hex"]
        T.update(dark0=shade(d, -0.04), dark1=d, dark2=shade(d, 0.05), card_dark=shade(d, 0.08), card_dark_2=shade(d, 0.04), card_dark_3=shade(d, 0.14))
    if lights:
        l = lights[0]["hex"]
        T.update(light0=shade(l, 0.03), light1=l, light2=shade(l, -0.05), paper=shade(l, 0.02), light_row=shade(l, -0.03))
    # a strong palette colour first (OCR highlight boxes average with their text and come out washed-out)
    accent = (accents[0]["hex"] if accents and accents[0]["chroma"] > 45 else None)         or (text.get("highlight_color") if text.get("highlight_color") and _chroma(text["highlight_color"]) > 30 else None)         or (accents[0]["hex"] if accents else None) or (accent_px["hex"] if accent_px else None)
    if accent:
        T["accent"] = accent
        T["on_accent"] = readable_on(accent, light="#ffffff", dark=T["on_light"])
        T["accent_light"] = accent
        T["on_accent_light"] = T["on_accent"]
        T["cap_hl_bg"] = accent
        T["cap_hl_fg"] = T["on_accent"]
    # text on dark / light worlds must stay readable
    T["on_dark"] = "#f5f5f5" if contrast("#f5f5f5", T["dark1"]) >= 7 else readable_on(T["dark1"])
    T["on_light"] = "#151515" if contrast("#151515", T["light1"]) >= 7 else readable_on(T["light1"])
    T["on_dark_2"] = shade(T["on_dark"], -0.35) if luminance_hex(T["on_dark"]) > 0.5 else shade(T["on_dark"], 0.35)
    T["on_light_2"] = shade(T["on_light"], 0.32) if luminance_hex(T["on_light"]) < 0.5 else shade(T["on_light"], -0.32)
    if text.get("text_color"):
        tc = text["text_color"]
        if luminance_hex(tc) < 0.25 and accent and contrast(accent, tc) >= 4.5:
            # dark lettering on a coloured block (e.g. black on yellow): captions get the same block
            T["cap_fg"], T["cap_box"] = tc, accent
            T["cap_shadow"] = "0 0 0 rgba(0,0,0,0), 0 0 0 rgba(0,0,0,0), 0 0 0 rgba(0,0,0,0)"   # flat print look, no glow
            T["cap_hl_bg"], T["cap_hl_fg"] = tc, readable_on(tc)
        else:
            T["cap_fg"] = "#ffffff"
    # letterforms -> display font from HyperFrames' bundled families
    asp, fill, upper = text.get("letter_aspect", 0.55), text.get("stroke_fill", 0.2), text.get("upper_ratio", 0.0)
    if asp < 0.42:
        disp = "League Gothic" if fill > 0.3 else "Oswald"
    elif asp > 0.66 and fill > 0.28:
        disp = "Archivo Black"
    elif fill > 0.3:
        disp = "Montserrat"
    elif asp > 0.6:
        disp = "Poppins"
    else:
        disp = None                 # keep the brand font
    if disp and disp in BUNDLED_FONTS:
        T["font_display"] = f'"{disp}", sans-serif'
        T["display_weight"] = 400 if disp in ("League Gothic", "Archivo Black") else 800 if disp == "Montserrat" else 700
        T["display_tracking"] = "0.01em" if disp in ("League Gothic", "Oswald") else "-0.03em"
    T["display_upper"] = upper > 0.7
    return T


def luminance_hex(h):
    from ..theme import luminance
    return luminance(h)


def derive_edit(pacing, trans, motion) -> dict:
    avg = pacing.get("median_shot") or pacing.get("avg_shot") or 2.5
    w = trans["weights"]
    e = motion["energy"]
    return {
        "min_shot": round(max(0.7, min(3.0, avg * 0.6)), 2),
        "max_shot": round(max(1.6, min(6.0, avg * 1.6)), 2),
        "punch": round(1.08 + 0.1 * min(1.0, e * 1.5 + w.get("punch", 0)), 3),
        "punch_every": 2 if (w.get("punch", 0) > 0.25 or pacing.get("cuts_per_min", 0) > 35) else 3,
        "transition_weights": {"cut": max(0.25, w.get("cut", 0) + w.get("punch", 0) * 0.5), "flash": w.get("flash", 0),
                               "zoom-blur": w.get("blur", 0), "punch": w.get("punch", 0) * 0.5 + 0.1},
        "keyword_spacing": round(max(2.0, min(6.0, 4.5 - e * 3)), 2),
        "energy": e,
    }


def derive_captions(text, energy) -> dict:
    if not text.get("has_text") or not text.get("captions"):
        return {"style": "pill" if energy > 0.25 else "clean", "reel_y": 0.74, "upper": False, "box": True, "max_words": 3}
    wpl = int(text.get("words_per_line", 3))
    if wpl <= 1:
        style = "slam"
    elif text.get("highlight_color"):
        style = "highlight"
    else:
        style = "color" if text.get("upper_ratio", 0) > 0.7 else "pill"
    return {"style": style, "reel_y": round(min(0.86, max(0.55, text.get("caption_y", 0.74) - text.get("caption_h", 0.03))), 3),
            "upper": text.get("upper_ratio", 0) > 0.7, "box": True,     # over footage a backing keeps captions readable
            "max_words": max(1, min(4, wpl)), "reel_size": int(max(44, min(96, text.get("caption_h", 0.035) * 1920 * 0.9)))}


def derive_grade(ref, foot) -> dict | None:
    """Move the footage's look toward the reference, bounded; graphics-heavy references weigh less."""
    if not foot:
        return None
    k = max(0.25, 1.0 - ref["flat_ratio"])       # flat motion-graphics frames say little about how footage should look
    clamp = lambda v, a: round(max(-a, min(a, v)), 3)
    adjust = {
        "exposure": clamp((ref["luma"] - foot["luma"]) / 60 * k, 0.35),
        "contrast": clamp((ref["contrast"] - foot["contrast"]) / 40 * k, 0.3),
        "saturation": clamp((ref["saturation"] - foot["saturation"]) / 120 * k, 0.35),
        "temperature": clamp((ref["warmth"] - foot["warmth"]) / 18 * k, 0.3),
    }
    adjust = {a: v for a, v in adjust.items() if abs(v) >= 0.02}
    out = {"adjust": adjust} if adjust else {}
    wheels = {}
    for zone, key in (("shadows", "shadow_tint"), ("highlights", "highlight_tint")):
        t = ref[key]
        amt = round(min(0.12, t["amount"] / 60 * k), 3)
        if amt >= 0.02 and t["hue"] == t["hue"]:          # skip NaN hues
            wheels[zone] = {"hue": t["hue"], "amount": amt, "level": 0}
    if wheels:
        out["wheels"] = wheels
    vig = ref["vignette"] * k
    if vig > 0.15:
        out["details"] = {"vignette": round(min(0.3, vig), 3)}
    return out or None


def derive_music(audio) -> dict:
    if not audio or not audio.get("has_audio"):
        return {"bpm": None, "prompt_key": None}
    bpm = audio["tempo_bpm"]
    bright = audio["band_share_pct"].get("4000-11025", 0) + audio["band_share_pct"].get("1000-4000", 0)
    on_rate = len(audio["strong_onsets"]) / max(1.0, len(audio["rms_db_per_0_5s"]) * 0.5) * 60
    if bpm >= 112 and bright > 18:
        mood = "upbeat modern electronic, bright plucky synths, punchy drums, energetic, polished commercial mix"
    elif bpm < 95:
        mood = "chill lofi hip hop, warm keys, soft drums, relaxed, clean mix"
    else:
        mood = "confident modern pop instrumental, steady drums, warm bass, clean polished mix"
    return {"bpm": round(bpm), "drop": audio.get("likely_drop_s"), "onsets_per_min": round(on_rate, 1),
            "prompt": f"{mood}, {round(bpm)} bpm, instrumental"}


def run_stage(p) -> dict:
    sc = p.cfg["style"]
    out = p.build / "style"
    if not sc.get("from_reference"):
        return {"style": None}
    man = read_json(p.build / "ingest" / "manifest.json")
    ana = read_json(p.build / "analyze" / "analysis.json")
    if not man or not man.get("references"):
        raise PipelineError("style.from_reference needs a reference video (project.references)")
    ref = Path(man["references"][0]["path"])
    ra = ana["references"][0] if ana and ana.get("references") else {}
    out.mkdir(parents=True, exist_ok=True)
    log.info("  sampling %s", ref.name)
    frames, times, src_fps, _ = sample_frames(ref, 4.0, 480)
    lum, sharp, sat, warm = frame_stats(frames)
    dur = float(man["references"][0]["probe"]["format"]["duration"])
    cuts = ra.get("cuts") or []
    pacing = measure_pacing(cuts, dur)
    trans = measure_transitions(cuts, times, frames, lum, sharp)
    motion = measure_motion(frames)
    pal = measure_palette(frames)
    accent_px = measure_accent(frames)
    grade_ref = measure_grade(frames)
    try:
        import torch
        gpu = torch.cuda.is_available()
    except ImportError:
        gpu = False
    text = measure_text(frames, times, gpu) if sc.get("ocr", True) else {"available": False}
    foot_grade = None
    av = (p.cfg.get("aroll") or {}).get("video") or (man.get("footage") or [{}])[0].get("id")
    f = next((x for x in man.get("footage", []) if x["id"] == av), None)
    if f:
        ff, _, _, _ = sample_frames(Path(f["path"]), 1.0, 360, 60)
        foot_grade = measure_grade(ff)
    theme = derive_theme(pal, text, grade_ref, accent_px)
    edit = derive_edit(pacing, trans, motion)
    caps = derive_captions(text, motion["energy"])
    grade = derive_grade(grade_ref, foot_grade) if sc.get("grade", True) else None
    music = derive_music(ra.get("audio"))
    data = {"reference": str(ref), "measured": {"duration": dur, "pacing": pacing, "transitions": trans, "motion": motion,
                                               "palette": pal, "accent_pixels": accent_px, "grade": grade_ref, "footage_grade": foot_grade, "text": text,
                                               "audio": {k: v for k, v in (ra.get("audio") or {}).items() if k not in ("beats", "rms_db_per_0_5s", "strong_onsets")}},
            "theme": theme, "edit": edit, "captions": caps, "grade": grade, "music": music}
    write_json(out / "style.json", data)
    log.info("  pacing: median shot %.2fs, %.0f cuts/min | transitions %s | energy %.2f", pacing.get("median_shot", 0),
             pacing.get("cuts_per_min", 0), trans["counts"], motion["energy"])
    log.info("  palette: %s", " ".join(f"{c['hex']}({c['share']:.0%})" for c in pal[:6]))
    log.info("  theme: dark %s light %s accent %s/%s, display font %s%s", theme["dark1"], theme["light1"], theme["accent"],
             theme["on_accent"], theme["font_display"].split(",")[0], " UPPER" if theme["display_upper"] else "")
    log.info("  captions: %s (y %.2f, upper %s, %s words) | text in %s of frames", caps["style"], caps["reel_y"], caps["upper"],
             caps["max_words"], text.get("frames_with_text", "n/a"))
    log.info("  grade for footage: %s", grade)
    log.info("  music: %s", music.get("prompt"))
    return {"style": str(out / "style.json")}
