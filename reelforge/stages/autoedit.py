"""Stage · autoedit: an editor's first cut of a talking-head video, planned from the transcript.

When project `scenes: auto` and `aroll.video` is set, this writes build/<name>/autoedit/plan.json:
  - silence trimmed: pauses longer than autoedit.min_gap are removed (padding kept around speech)
  - jump cuts at word boundaries, shots between min_shot and max_shot, alternating punch-in framing
  - motivated transitions: hard cuts, a zoom punch every few cuts, a flash/whip on new sentences and cutaways
  - motion-graphics representations of what is said:
      list cutaways   ("a good camera, a good mic, good lighting, a good setup" -> full-screen checklist)
      stat overlays   ("100%" -> counter card over the speaker)
      keyword pop-ups (phone, camera, money, viral, goal ...)
  - a hook title over the first shot, an optional outro, and a lower-third name tag
  - the dialogue track as one audio range per kept span, so speech is continuous under cutaways
Everything is plain data; compose renders it with the scene templates. Review it at the preview checkpoint."""
from __future__ import annotations

import re

from pathlib import Path

from ..util import PipelineError, log, read_json, write_json

STOP = set("""a an the and or but so to of in on at for with by from as is are was were be been being am i you he she it we they
me my your our their his her its this that these those there here then than too very just also not no yes do does did done
have has had will would can could should may might must shall if when while because about into over under up down out
more most much many lot lots some any all each every such own same other only even still again ever never always people
thing things one get got go goes going make makes made like want need say said know think really actually okay ok yeah
let us them what which who whom whose how why where today it's that's don't you're i'm i've there's what's can't
etc""".split())

ICONS = {  # keyword (lowercase, prefix match) -> glyph name in _lib.j2
    "phone": "phone", "mobile": "phone", "camera": "camera", "video": "play", "mic": "mic", "microphone": "mic",
    "light": "bulb", "lighting": "bulb", "setup": "grid", "money": "coin", "income": "coin", "paid": "coin", "pay": "coin",
    "cost": "coin", "campaign": "chart", "viral": "bolt", "following": "users", "followers": "users", "influencer": "users",
    "creator": "star", "content": "play", "quality": "star", "goal": "target", "journey": "steps", "step": "steps",
    "comment": "chat", "equipment": "camera", "professional": "check", "sustainable": "chart", "easy": "check",
    "brand": "star", "growth": "chart", "time": "clock", "audience": "users", "subscribe": "bolt", "start": "play",
}


def icon_for(word: str) -> str | None:
    w = re.sub(r"[^a-z]", "", word.lower())
    for k, g in ICONS.items():
        if w.startswith(k):
            return g
    return None


EMOJI = {  # keyword (lowercase, prefix match) -> emoji sticker
    "money": "💰", "cash": "💰", "rich": "💰", "income": "💸", "paid": "💸", "pay": "💸", "dollar": "💵", "price": "💵",
    "cost": "💵", "budget": "💵", "cheap": "💵", "revenue": "📈", "profit": "📈", "sales": "📈", "growth": "📈", "grow": "🚀",
    "fast": "⚡", "fastest": "⚡", "speed": "⚡", "quick": "⚡", "viral": "🔥", "fire": "🔥", "hot": "🔥", "trend": "🔥",
    "best": "🏆", "win": "🏆", "winner": "🏆", "number": "🔢", "idea": "💡", "light": "💡", "smart": "🧠", "brain": "🧠",
    "think": "🧠", "learn": "🧠", "time": "⏰", "clock": "⏰", "deadline": "⏰", "love": "❤️", "heart": "❤️",
    "feel": "❤️", "feeling": "❤️", "emotion": "❤️", "emotional": "❤️", "home": "🏠", "house": "🏠", "property": "🏠",
    "listing": "🏡", "remodel": "🔨", "build": "🔨", "city": "🏙️", "cities": "🏙️", "phone": "📱", "camera": "📷",
    "video": "🎬", "content": "🎬", "star": "⭐", "quality": "⭐", "people": "👥", "audience": "👥", "team": "👥",
    "crew": "👥", "goal": "🎯", "target": "🎯", "rocket": "🚀", "launch": "🚀", "check": "✅", "done": "✅", "yes": "✅",
    "stop": "🛑", "warning": "⚠️", "secret": "🤫", "crazy": "🤯", "mind": "🤯", "wow": "😮", "look": "👀", "miss": "👀",
    "deal": "🤝", "offer": "🤝", "sign": "✍️", "email": "📧", "message": "💬", "comment": "💬", "call": "📞",
}


def emoji_for(word: str, extra: dict | None = None) -> str | None:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return None
    for k, e in {**EMOJI, **(extra or {})}.items():
        if (w == k or w == k + 's' or (len(k) >= 5 and w.startswith(k))):
            return e
    return None


def clean(w: str) -> str:
    return re.sub(r"[^\w%$'-]", "", w)


def score_word(w: str) -> float:
    c = clean(w).lower()
    if not c or c in STOP or len(c) < 3:
        return 0.0
    return len(c) * 0.25 + (3.0 if (icon_for(c) or emoji_for(c)) else 0.0) + (2.5 if re.search(r"\d", c) else 0.0)


# ---------------------------------------------------------------- spans and shots
def speech_spans(words, min_gap, pad, dur):
    spans = []
    for w in words:
        if spans and w["start"] - spans[-1][1] < min_gap:
            spans[-1][1] = max(spans[-1][1], w["end"])
        else:
            spans.append([w["start"], w["end"]])
    out = []
    for a, b in spans:
        a, b = max(0.0, a - pad), min(dur, b + pad)
        if out and a <= out[-1][1]:
            out[-1][1] = b
        else:
            out.append([a, b])
    return out


def split_span(a, b, words, min_shot, max_shot):
    """Split [a, b] into shots no longer than max_shot, cutting in the widest gap between words."""
    if b - a <= max_shot:
        return [(a, b)]
    inner = [w for w in words if a < w["start"] < b]
    cands = []
    for w0, w1 in zip(inner, inner[1:]):
        t = (w0["end"] + w1["start"]) / 2
        if t - a >= min_shot and b - t >= min_shot:
            cands.append((w1["start"] - w0["end"], -abs(t - (a + b) / 2), t))
    if not cands:
        return [(a, b)]
    # prefer cuts that land near max_shot from the start, among the wider gaps
    target = a + min(max_shot, (b - a) / 2 + 0.5)
    best = max(cands, key=lambda c: c[0] * 3 - abs(c[2] - target) * 0.6)
    return split_span(a, best[2], words, min_shot, max_shot) + split_span(best[2], b, words, min_shot, max_shot)


# ---------------------------------------------------------------- representations
def find_list(text: str):
    """'... a good camera, a good mic, good lighting, a good setup, etc.' -> ['Good camera', ...]"""
    parts = [x.strip() for x in re.split(r",|\band\b", text) if x.strip()]
    items, run = [], []
    for x in parts:
        x = re.split(r"[.!?]\s+", x)[-1]              # keep only the clause that leads into the item
        x2 = re.sub(r"^((you|we|i)\s+)?(need|needs|should have|must have|have|get|buy)\s+", "", x, flags=re.I)
        x2 = re.sub(r"^(a|an|the|and)\s+", "", x2, flags=re.I).strip(" .")
        x2 = re.sub(r"\b(etc|etc\.)\b.*$", "", x2, flags=re.I).strip(" .")
        if 1 <= len(x2.split()) <= 3 and len(x2) <= 22 and x2:
            run.append(x2)
        else:
            if len(run) >= 3:
                items = run
                break
            run = []
    if len(run) >= 3 and not items:
        items = run
    return [i[0].upper() + i[1:] for i in items[:5]] if len(items) >= 3 else None


def map_time(t, ranges):
    """source time -> film time, or None if t was trimmed away"""
    for r in ranges:
        if r["src"] - 1e-6 <= t <= r["src"] + r["dur"] + 1e-6:
            return r["film"] + (t - r["src"])
    return None


def run_stage(p) -> dict:
    if p.cfg.get("scenes") != "auto":
        return {"plan": None}
    a = p.cfg.get("aroll") or {}
    man = read_json(p.build / "ingest" / "manifest.json", {})
    tr = read_json(p.build / "transcribe" / "transcript.json") if a.get("video") else None
    ae0 = p.cfg["autoedit"]
    if ae0.get("mode") == "montage" or not a.get("video") or not tr or len(tr.get("words", [])) < ae0.get("min_words_for_talk", 8):
        return plan_montage(p, man)
    foot = next(f for f in man["footage"] if f["id"] == a["video"])
    dur = float(foot["probe"]["format"]["duration"])
    ae = p.cfg["autoedit"]
    words = tr["words"]
    # 1. keep speech: drop long pauses and filler sounds
    speech = [w for w in words if not is_filler(w["text"])]
    spans = speech_spans(speech, ae["min_gap"], ae["pad"], dur) if ae["trim_silence"] else [[0.0, dur]]
    # 2. shots: cut where the speaker breathes, not on a timer
    shots = []
    for s0, s1 in spans:
        shots += split_span(s0, s1, speech, ae["min_shot"], ae["max_shot"])
    shots = merge_short(shots, ae["min_shot"] * 0.6)
    ranges, t = [], 0.0
    for s0, s1 in shots:
        ranges.append({"film": round(t, 3), "src": round(s0, 3), "dur": round(s1 - s0, 3)})
        t += s1 - s0
    talk_end = round(t, 3)
    removed = dur - talk_end
    # 3. caption words in film time
    film_words = []
    for w in tr["caption_words"]:
        fs, fe = map_time(w["start"], ranges), map_time(w["end"], ranges)
        if fs is None and fe is None:
            continue
        fs = fs if fs is not None else fe - 0.15
        fe = fe if fe is not None else fs + 0.15
        film_words.append({**w, "start": round(fs, 3), "end": round(max(fe, fs + 0.08), 3)})
    phrases = []
    for i, ph in enumerate(tr["phrases"]):
        ws = [w for w in film_words if w.get("phrase") == i]
        if ws:
            phrases.append({"i": i, "text": ph["text"], "start": ws[0]["start"], "end": ws[-1]["end"], "words": ws})
    # 4. what appears over the picture (film-wide, independent of the cuts)
    ec = ae.get("emoji") or {}
    overlays = plan_overlays(ae, phrases, film_words, ec.get("enabled", "auto") not in (False, "off", "false"), ec.get("extra") or {})
    beats = sorted(o["t"] for o in overlays if o["type"] in ("emoji", "stat"))
    # 5. picture: framing per shot, B-roll, transitions
    foot_dur = {f["id"]: float(f["probe"]["format"]["duration"]) for f in man.get("footage", [])}
    bc = ae.get("broll") or {}
    if bc.get("clips", "auto") == "auto":
        broll_ids = [f["id"] for f in man.get("footage", []) if f["id"] != a["video"]]
    else:
        broll_ids = [b for b in (bc.get("clips") or []) if b in foot_dur and b != a["video"]]
    broll_on = bool(broll_ids) and bc.get("enabled", "auto") not in (False, "off", "false")
    bevery = bc.get("every", "auto")
    if bevery == "auto":
        cpm = (((read_json(p.build / "style" / "style.json") or {}).get("measured") or {}).get("pacing") or {}).get("cuts_per_min") or 0
        bevery = 2 if cpm >= 24 else 3 if cpm >= 10 else 4
    bevery = max(2, int(bevery))
    broll_cur = {b: min(0.3, foot_dur.get(b, 0.0) * 0.05) for b in broll_ids}
    safe = safe_zones(Path(foot["path"]), ae["punch_hi"])
    scenes, prev_zoom, bi, belig, n_broll = [], None, 0, 0, 0
    for k, r in enumerate(ranges):
        f0, f1 = r["film"], r["film"] + r["dur"]
        shot_words = " ".join(w["text"] for w in film_words if f0 <= w["start"] < f1)
        ph_start = next((ph for ph in phrases if abs(ph["start"] - f0) < 0.3), None)
        motivated = bool(ph_start and re.match(r"^(but|so|and if|now|that's why|here's|the truth)\b", ph_start["text"], re.I))
        emphatic = motivated or bool(re.search(r"[!?]", shot_words)) or any(f0 <= b < f1 for b in beats)
        zoom = 1.0 if k == 0 else next_zoom(prev_zoom, emphatic, ae["punch"], ae["punch_hi"])
        prev_zoom = zoom
        hits = [{"at": round(b - f0, 3), "by": 0.08} for b in beats if f0 + 0.6 <= b <= f1 - 0.6 and r["dur"] >= 2.2][:1]
        sc = {"id": f"shot{k}", "type": "footage", "video": a["video"], "media_start": r["src"], "duration": r["dur"],
              "push": [zoom, round(zoom + 0.03, 3)], "focus": safe["focus"], "hits": hits, "overlays": [], "exit": "none",
              "entry": "none" if k == 0 else pick_transition(ae, k, motivated)}
        if broll_on and k > 0:
            belig += 1
            bid = broll_ids[bi % len(broll_ids)] if belig % bevery == 0 else None
            if bid and foot_dur.get(bid, 0.0) >= r["dur"]:
                ms = broll_cur.get(bid, 0.0)
                if ms + r["dur"] > foot_dur[bid] - 0.1:
                    ms = min(0.3, foot_dur[bid] * 0.05)
                broll_cur[bid] = ms + r["dur"]
                bi += 1
                n_broll += 1
                sc.update({"video": bid, "media_start": round(ms, 3), "audio": False, "push": [1.0, 1.05], "focus": None, "hits": [], "broll": True})
        scenes.append(sc)
    out_cfg = ae.get("outro")
    if out_cfg:
        scenes.append({"id": "outro", "type": out_cfg.get("type", "kinetic"), "duration": out_cfg.get("duration", 2.6),
                       "world": out_cfg.get("world", "dark"), "entry": out_cfg.get("entry", "whip-left"), "exit": "none",
                       **{k2: v for k2, v in out_cfg.items() if k2 not in ("type", "duration", "world", "entry")}})
    plan = {"safe": safe, "scenes": scenes, "overlays": overlays, "film_words": film_words, "all_film_words": film_words, "aroll_ranges": ranges,
            "talk_end": talk_end, "removed_s": round(removed, 3), "source_duration": dur}
    write_json(p.build / "autoedit" / "plan.json", plan)
    log.info("  %.1fs kept from %.1fs (%.1fs of pauses cut), %d shots (%d B-roll), overlays: %s%s", talk_end, dur, removed, len(ranges), n_broll,
             ", ".join(f"{o['type']}@{o['t']:.1f}" for o in overlays) or "none", ", outro" if out_cfg else "")
    for s in scenes:
        log.info("    %-7s %5.2fs  zoom %s  %s%s", s["id"], s["duration"], (s.get("push") or ["-"])[0], s.get("entry", ""), " BROLL" if s.get("broll") else "")
    return {"plan": str(p.build / "autoedit" / "plan.json"), "scenes": len(scenes), "talk_end": talk_end}


FILLERS = {"um", "umm", "uh", "uhh", "uhm", "erm", "hmm", "hm", "ah", "er"}


def is_filler(text: str) -> bool:
    return re.sub(r"[^\w]", "", text).lower() in FILLERS


def merge_short(shots, min_len):
    """A shot too short to register reads as a glitch: fold it into its neighbour when they are contiguous."""
    out = []
    for s in shots:
        if out and (s[1] - s[0] < min_len or out[-1][1] - out[-1][0] < min_len) and abs(s[0] - out[-1][1]) < 1e-6:
            out[-1] = (out[-1][0], s[1])
        else:
            out.append(tuple(s))
    return out


def next_zoom(prev, emphatic, med, close):
    """Framing changes by a clearly visible step on every cut; emphasis goes tight. Never the same framing twice."""
    if emphatic:
        return close if prev != close else med
    return 1.0 if prev != 1.0 else med


def hook_text_from(sentence: str, max_words: int = 12) -> str | None:
    clause = sentence.strip()
    if len(clause.split()) > max_words:
        clause = re.split(r"[,;:]", clause)[0].strip()
    if not clause or len(clause.split()) > max_words:
        return None
    return " ".join(l for l, _ in hook_from(clause))


def plan_overlays(ae, phrases, film_words, emoji_on, extra) -> list[dict]:
    """Graphics a reel editor would actually add: a hook line, a stat when one is said, a checklist when a list is said,
    and an occasional emoji. Sparse on purpose; they never overlap each other."""
    O, busy = [], []
    free = lambda a, b: all(b <= x or a >= y for x, y in busy)
    if ae.get("hook", True) and phrases:
        h = ae.get("hook_text")
        if isinstance(h, list):
            h = " ".join(x[0] if isinstance(x, (list, tuple)) else str(x) for x in h)
        h = h or hook_text_from(re.split(r"(?<=[.!?])\s", phrases[0]["text"])[0])
        if h:
            end = max(float(ae.get("hook_min_s", 2.6)), min(3.6, phrases[0]["end"]))
            O.append({"type": "hook", "t": 0.05, "end": round(end, 3), "text": h})
            busy.append((0.0, end))
    if ae.get("cutaways", True):
        for ph in phrases:
            items = find_list(ph["text"])
            if not items:
                continue
            items = items[:4]
            rows = []
            for it in items:
                key = clean(it.split()[-1]).lower()
                hit = next((w for w in ph["words"] if clean(w["text"]).lower().startswith(key[:4])), None)
                rows.append({"text": it, "t": hit["start"] if hit else None})
            known = [x["t"] for x in rows if x["t"] is not None]
            if len(known) < 2:
                continue
            a0, a1 = min(known) - 0.1, max(known) + 1.5
            for j, x in enumerate(rows):
                x["t"] = round(x["t"] if x["t"] is not None else a0 + 0.2 * j, 3)
            if free(a0, a1):
                O.append({"type": "checklist", "t": round(a0, 3), "end": round(a1, 3), "items": rows})
                busy.append((a0, a1))
    for i, w in enumerate(film_words):
        if re.search(r"\d+%|\$\d", w["text"]):
            a0, a1 = w["start"], w["start"] + 1.9
            if free(a0 - 0.5, a1 + 0.5):
                O.append({"type": "stat", "t": a0, "end": round(a1, 3), "value": int(re.search(r"\d+", w["text"]).group(0)),
                          "prefix": "$" if "$" in w["text"] else "", "suffix": "%" if "%" in w["text"] else "", "label": stat_label(w, film_words)})
                busy.append((a0, a1))
    if emoji_on:
        last, side = -99.0, 0
        for w in film_words:
            if clean(w["text"]).lower() in STOP:
                continue
            e = emoji_for(clean(w["text"]), extra)
            a0, a1 = w["start"], w["start"] + 1.25
            if e and a0 - last >= float(ae["keyword_spacing"]) and free(a0 - 0.2, a1 + 0.2):
                O.append({"type": "emoji", "t": a0, "end": round(a1, 3), "emoji": e, "side": side % 2})
                busy.append((a0, a1))
                last, side = a0, side + 1
    return sorted(O, key=lambda o: o["t"])


def safe_zones(video, close: float) -> dict:
    """Zoom centre (the speaker's face) and where text may go at the tightest framing."""
    from ..vision import face_box
    fb = face_box(video)
    if not fb:
        return {"face": None, "focus": [0.5, 0.38], "caption_y_min": 0.0, "overlay_top": 0.08}
    fx, fy = fb["cx"], (fb["top"] + fb["bottom"]) / 2
    z = close + 0.03
    return {"face": fb, "focus": [round(fx, 3), round(fy, 3)], "caption_y_min": round(min(0.84, fy + (fb["bottom"] - fy) * z + 0.02), 3),
            "overlay_top": 0.06}


def graphic_world(p, n: int) -> str:
    """Full-screen graphics use the world the reference lives in (light paper vs dark), alternating if it is mixed."""
    st = read_json(p.build / "style" / "style.json") or {}
    pal = ((st.get("measured") or {}).get("palette")) or []
    light = sum(c["share"] for c in pal if c["L"] > 75)
    dark = sum(c["share"] for c in pal if c["L"] < 30)
    if pal and light > dark * 1.5:
        return "light"
    if pal and dark > light * 1.5:
        return "dark"
    return "dark" if n % 2 == 0 else "light"


def pick_transition(ae: dict, k: int, motivated: bool, after_graphic: bool = False, into_graphic: bool = False) -> str:
    """Hard cuts by default, as in real reels. Effects only when the reference clearly uses them or a sentence turns."""
    w = {"cut": 0.8, "flash": 0.0, "zoom-blur": 0.05, "punch": 0.15, **(ae.get("transition_weights") or {})}
    if into_graphic or after_graphic:
        return "zoom-blur"
    if motivated:
        if w["flash"] >= 0.25:
            return "flash"
        return "punch"
    if k % int(ae.get("punch_every", 5)) == 0 and w["punch"] >= 0.05:
        return "punch"
    return "cut"


def plan_montage(p, man) -> dict:
    """No speech to follow: cut the footage on the music's beat grid at the reference's shot lengths."""
    ae = p.cfg["autoedit"]
    clips = [f for f in man.get("footage", [])]
    if not clips:
        raise PipelineError("scenes: auto needs footage")
    bpm = float((p.cfg["music"].get("arrange") or {}).get("bpm") or 120)
    beat = 60.0 / bpm
    style = read_json(p.build / "style" / "style.json") or {}
    shots_ref = [s for s in ((style.get("measured") or {}).get("pacing") or {}).get("shots", []) if 0.3 <= s <= 8] or                 [ae["max_shot"], ae["min_shot"], (ae["min_shot"] + ae["max_shot"]) / 2]
    limit = float(ae.get("max_duration") or 30.0)
    scenes, t, k, ri = [], 0.0, 0, 0
    for c in clips:
        cdur = float(c["probe"]["format"]["duration"])
        pos = min(0.2, cdur * 0.05)
        while pos < cdur - 0.4 and t < limit:
            want = shots_ref[ri % len(shots_ref)]
            ri += 1
            d = max(beat, round(want / beat) * beat)          # snap to whole beats
            d = min(d, cdur - pos, limit - t)
            if d < 0.4:
                break
            punch = ae["punch"]
            push = [1.0, 1.05] if k % 2 == 0 else [punch, punch + 0.04]
            sc = {"id": f"shot{k}", "type": "footage", "video": c["id"], "media_start": round(pos, 3), "duration": round(d, 3),
                  "push": push, "entry": "none" if k == 0 else pick_transition(ae, k, k % 4 == 0), "exit": "none",
                  "overlays": [], "audio": bool(ae.get("keep_footage_audio"))}
            if k == 0 and ae.get("hook_text"):
                sc["caption_pos"] = "middle"
                sc["lines"] = [{"text": l, "size": sz} for l, sz in ae["hook_text"]]
            scenes.append(sc)
            t += d
            pos += d
            k += 1
        if t >= limit:
            break
    out_cfg = ae.get("outro")
    if out_cfg:
        scenes.append({"id": "outro", "type": out_cfg.get("type", "kinetic"), "duration": out_cfg.get("duration", 2.6),
                       "world": out_cfg.get("world", "dark"), "entry": out_cfg.get("entry", "whip-left"), "exit": "none",
                       **{k2: v for k2, v in out_cfg.items() if k2 not in ("type", "duration", "world", "entry")}})
    plan = {"mode": "montage", "scenes": scenes, "film_words": [], "all_film_words": [], "aroll_ranges": [], "talk_end": round(t, 3),
            "removed_s": 0, "source_duration": sum(float(c["probe"]["format"]["duration"]) for c in clips)}
    write_json(p.build / "autoedit" / "plan.json", plan)
    log.info("  montage: %d shots on a %.0f BPM grid, %.1fs%s", k, bpm, t, ", outro" if out_cfg else "")
    for s in scenes:
        log.info("    %-7s %-8s %5.2fs  %s", s["id"], s["type"], s["duration"], s.get("entry", ""))
    return {"plan": str(p.build / "autoedit" / "plan.json"), "scenes": len(scenes), "talk_end": round(t, 3)}


def hook_from(sentence: str):
    """Hook title from the first sentence: the strongest 1-2 word phrase becomes the accent pill."""
    toks = sentence.strip().rstrip(".!?").split()
    if not toks:
        return []
    best_i = max(range(len(toks)), key=lambda i: score_word(toks[i]) + (score_word(toks[i + 1]) * 0.8 if i + 1 < len(toks) else 0))
    j = best_i + 1 if best_i + 1 < len(toks) and score_word(toks[best_i + 1]) > 0 else best_i
    head = " ".join(toks[:best_i])
    acc = " ".join(toks[best_i:j + 1])
    tail = " ".join(toks[j + 1:])
    lines = []
    if head:
        lines.append((head, 64))
    lines.append((f"[{acc}]" + (f" {tail}" if tail and len(tail) < 14 else ""), 96))
    if tail and len(tail) >= 14:
        lines.append((tail, 56))
    return lines


def stat_label(stat, words):
    """The word(s) right after the number, up to the end of the clause: '100% true. But' -> 'TRUE'."""
    i = words.index(stat)
    out = []
    if re.search(r"[.!?,]$", stat["text"]):
        return ""
    for w in words[i + 1:i + 4]:
        c = clean(w["text"])
        if c.lower() not in STOP:
            out.append(c)
        if re.search(r"[.!?,]$", w["text"]) or len(out) == 2:
            break
    return " ".join(out).upper()[:16]
