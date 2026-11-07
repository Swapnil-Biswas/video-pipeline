"""Stage 5 · compose: build a complete HyperFrames project in build/<name>/hf from the storyboard.

- `file` scenes are copied verbatim (custom hand-authored compositions, e.g. the original showreel scenes).
- template scenes (kinetic, card, chat, endcard, footage) are rendered from templates/scenes/*.j2 with Jinja.
- templates emit sound cues and click ducks while rendering; they are saved for the sfx stage."""
from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path

import jinja2

from ..util import PipelineError, copy_into, log, num, read_json, run, write_json
from .autoedit import icon_for

RESERVED = {"main", "root", "ground", "captions", "music", "voice"}


SAFE_KEYS = {"id", "type", "video", "src", "logo", "icon", "entry", "exit", "world", "caption_pos", "state", "side", "fit"}


def esc(obj, key=None):
    """HTML-escape every user/transcript string that reaches the render page (<, >, &), recursively.
    Paths, ids and enum-like keys are left alone; they never come from end users in the API."""
    if isinstance(obj, str):
        return obj if key in SAFE_KEYS else obj.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if isinstance(obj, list):
        return [esc(x, key) for x in obj]
    if isinstance(obj, dict):
        return {k: esc(v, k) for k, v in obj.items()}
    return obj


def split_words(text: str) -> list[tuple[str, bool]]:
    """'Pay only for [finished work.]' -> [('Pay',F),('only',F),('for',F),('finished work.',T)]"""
    out, pos = [], 0
    for m in re.finditer(r"\[([^\]]+)\]", text):
        out += [(w, False) for w in text[pos:m.start()].split()]
        out.append((m.group(1), True))
        pos = m.end()
    out += [(w, False) for w in text[pos:].split()]
    return out


# ---------------------------------------------------------------- chat layout + camera path
def chat_layout(s: dict, W: int, H: int, sid: str) -> dict:
    u = min(W, H) / 1080
    colW = min(1060 * u, W * 0.86)
    left = (W - colW) / 2
    right = left + colW
    s_close = min(1.6, (W * 0.94) / colW)
    groups = s.get("groups") or [{"messages": s.get("messages", [])}]
    step_default = float(s.get("step", 0.62))
    msgs, labels, cams, swipes, glows = [], [], [], [], []
    t = 0.0
    y_top = 300 * u
    gap = 26 * u
    first_visible = bool(s.get("first_visible", True))
    n_total = sum(len(g["messages"]) for g in groups)
    k = 0
    for gi, g in enumerate(groups):
        y = y_top
        g_start_y = y
        glows.append({"x": W / 2 - 500 * u, "y": y_top - 400 * u, "r": 1000 * u})
        label_done = False
        g_first_t = None
        for mi, m in enumerate(g["messages"]):
            side = m.get("side", "out")
            big = bool(m.get("big"))
            fs = (70 if big else 40) * u
            pad_x = (42 if big else 32) * u * 2
            time_w = (18 + 22 * 0.62 * len(m.get("time", ""))) * u if m.get("time") else 0
            est = len(m["text"]) * fs * (0.62 if big else 0.56) + time_w
            maxw = colW if big else colW * 0.88
            lines = max(1, math.ceil(est / (maxw - pad_x)))
            h = (52 if big else 46) * u + lines * fs * 1.2
            width = min(maxw, est + pad_x)
            if side == "in" and g.get("who") and not label_done:
                labels.append({"id": f"{sid}-w{gi}", "x": left + 6 * u, "y": y, "text": g["who"], "note": g.get("note"),
                               "avatar": g.get("avatar"), "t": None, "g": gi})
                y += 52 * u
                label_done = True
            # timing
            if m.get("at") is not None:
                t = float(m["at"])
            elif k == 0:
                t = 0.0 if first_visible else 0.35
            else:
                t += float(m.get("step", step_default)) + (0.5 if side == "in" else 0)
            if gi > 0 and mi == 0 and m.get("at") is None:
                t += 0.55                                  # swipe between chats
            if labels and labels[-1]["t"] is None and labels[-1]["g"] == gi:
                labels[-1]["t"] = round(max(0.0, t - 0.55), 3)
            if g_first_t is None:
                g_first_t = t
            mid = f"{sid}-m{k}"
            edge = left if side == "in" else W - right
            msgs.append({"id": mid, "side": side, "text": m["text"], "time": m.get("time"), "big": big, "edge": edge,
                         "y": y, "h": h, "w": width, "maxw": maxw, "nowrap": lines == 1, "t": round(t, 3),
                         "dots": side == "in" and m.get("typing", True) and not (k == 0 and first_visible), "g": gi})
            # camera: frame this message (column always fully inside the frame horizontally)
            cy = y + h / 2
            is_last_in_group = mi == len(g["messages"]) - 1
            if big:
                # punch in on the payoff, centred on the bubble itself, never wider than the frame
                zb = min(1.5, (W * 0.86) / max(width * 1.1, 1))
                bx = (W - edge - width / 2) if side == "out" else (edge + width / 2)
                cams.append({"t": round(t + 0.07, 3), "d": 0.18, "x": bx, "y": cy, "s": round(zb * 1.05, 3), "ease": "power3.out"})
                cams.append({"t": round(t + 0.25, 3), "d": 0.6, "x": bx, "y": cy, "s": round(zb, 3), "ease": "expo.out"})
            elif is_last_in_group and len(g["messages"]) > 2:
                gh = (y + h) - g_start_y
                zw = round(min(1.0, (H * 0.82) / gh, s_close), 3)
                cams.append({"t": round(t - 0.4, 3), "d": 0.55, "x": W / 2, "y": g_start_y + gh / 2, "s": zw, "ease": "power3.inOut"})
            elif k == 0:
                cams.append({"t": 0, "d": 0, "x": W / 2, "y": cy, "s": round(s_close, 3), "ease": "none"})
            else:
                lead = 0.6 if side == "in" else 0.25
                cams.append({"t": round(max(0.0, t - lead), 3), "d": 0.45, "x": W / 2, "y": cy, "s": round(s_close, 3), "ease": "power3.inOut"})
            y += h + gap
            k += 1
        if gi < len(groups) - 1:
            swipes.append({"g": gi, "t": round(t + float(s.get("hold", 0.45)), 3)})
            y_top = y + 700 * u
    # sort and make sure camera moves do not overlap (each ends before the next starts)
    cams.sort(key=lambda c: c["t"])
    for a, b in zip(cams, cams[1:]):
        if a["t"] + a["d"] > b["t"]:
            a["d"] = round(max(0.12, b["t"] - a["t"]), 3)
    # swipe camera moves are just the next group's first camera; make them faster and smoother
    for sw in swipes:
        nxt = next((c for c in cams if c["t"] >= sw["t"]), None)
        if nxt:
            nxt["ease"] = "power4.inOut"
    end = msgs[-1]
    zt = None
    if s.get("zoom_through", end["big"]):
        zx = (W - end["edge"] - end["w"] / 2) if end["side"] == "out" else (end["edge"] + end["w"] / 2)
        zt = {"x": round(zx, 1), "y": round(end["y"] + end["h"] / 2, 1), "s": 10}
    last_t = max(m["t"] for m in msgs)
    if last_t + 0.6 > float(s["duration"]):
        raise PipelineError(f"scene '{sid}': last chat message at {last_t:.2f}s does not fit in {s['duration']}s "
                            f"(lower 'step' or raise 'duration')")
    return {"msgs": msgs, "labels": labels, "cams": cams, "swipes": swipes, "glows": glows,
            "col": {"left": left, "width": colW}, "zoom_through": zt, "first_visible": first_visible,
            "height": y + 400 * u, "n": n_total}


def speech_words(p, for_captions: bool = False) -> list[dict]:
    """Spoken words in film time: auto-edit plan > transcript (A-roll at film time = source time) > voice words."""
    if p.auto:
        plan = p.plan()
        return plan["film_words"] if for_captions else plan["all_film_words"]
    tr = read_json(p.build / "transcribe" / "transcript.json")
    if tr and p.cfg["transcribe"].get("enabled"):
        return tr["caption_words"] if for_captions else tr["words"]
    if p.cfg["voice"]["mode"] != "none":
        return read_json(p.build / "voice" / "words.json", []) or []
    return []


def caption_phrases(words: list[dict], max_words: int) -> list[dict]:
    out, cur = [], []
    for w in words:
        cur.append(w)
        end_punct = w["text"].rstrip().endswith((".", "!", "?", ",", "।"))
        if len(cur) >= max_words or end_punct:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    ph = []
    for i, c in enumerate(out):
        nxt = out[i + 1][0]["start"] if i + 1 < len(out) else c[-1]["end"] + 0.4
        ph.append({"id": f"cap{i}", "start": round(c[0]["start"], 3), "end": round(max(c[0]["start"] + 0.12, min(c[-1]["end"] + 0.25, nxt - 0.05)), 3),
                   "words": c})
    return ph


# ---------------------------------------------------------------- stage
def run_stage(p) -> dict:
    hf = p.hf
    hf.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(hf / "compositions", ignore_errors=True)
    shutil.rmtree(hf / "assets", ignore_errors=True)
    (hf / "compositions").mkdir(parents=True)
    write_json(hf / "hyperframes.json", {
        "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
        "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
        "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
        "media": {"autoProxy": True}})
    write_json(hf / "package.json", {"name": p.name, "private": True, "type": "module"})
    write_json(hf / "meta.json", {"id": p.name, "name": p.name})

    # assets
    for a in p.cfg.get("assets") or []:
        src = p.path(a)
        if not src.exists():
            raise PipelineError(f"asset folder not found: {src}")
        copy_into(src, hf / "assets" / src.name)
    man = read_json(p.build / "ingest" / "manifest.json", {"footage": []}) or {"footage": []}
    for f in man.get("footage", []):
        copy_into(Path(f["path"]), hf / "assets" / "footage" / f"{f['id']}.mp4")
    ar = (p.cfg.get("aroll") or {}).get("video")
    if ar:
        f = next((x for x in man.get("footage", []) if x["id"] == ar), None)
        if not f:
            raise PipelineError(f"aroll.video '{ar}' is not in project.footage")
        dst = hf / "assets" / "footage" / f"{ar}_dialog.wav"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", f["path"], "-vn", "-ac", "2", "-ar", "48000", str(dst)])
    bed = p.build / "music" / "bed.wav"
    if p.cfg["music"]["mode"] != "none":
        if not bed.exists():
            raise PipelineError("music bed missing: run the music stage")
        copy_into(bed, hf / "assets" / "music" / "bed.wav")
    vo = p.build / "voice" / "vo.wav"
    if p.cfg["voice"]["mode"] != "none":
        if not vo.exists():
            raise PipelineError("voice track missing: run the voice stage")
        copy_into(vo, hf / "assets" / "voice" / "vo.wav")

    W, H = p.W, p.H
    u = min(W, H) / 1080
    from ..config import deep_merge
    from ..theme import DEFAULT_THEME, theme_css
    T = deep_merge(DEFAULT_THEME, p.cfg.get("theme") or {})
    G = p.cfg.get("grade") or None
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(p.root / "templates" / "scenes")),
                             undefined=jinja2.ChainableUndefined, autoescape=False, trim_blocks=False)
    cues, ducks = [], []

    def cue(f, t, v):
        cues.append([f, round(float(t), 3), float(v)])
        return ""

    def duck(t):
        ducks.append(round(float(t), 3))
        return ""

    env.globals.update(split_words=split_words, cue=cue, duck=duck,
                       has_plain=lambda text: any(not acc for _, acc in split_words(text)), icon_for=icon_for)
    footage_ids = {f["id"] for f in man.get("footage", [])}
    scenes = p.scenes()
    for s in scenes:
        sid = s["id"]
        if sid in RESERVED or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", sid):
            raise PipelineError(f"scene id '{sid}' is reserved or not a valid HTML id")
        dst = hf / "compositions" / f"{sid}.html"
        if s["type"] == "file":
            src = p.path(s["src"])
            if not src.exists():
                raise PipelineError(f"scene '{sid}': file not found {src}")
            html = src.read_text(encoding="utf-8")
            if f'data-composition-id="{sid}"' not in html or f'window.__timelines["{sid}"]' not in html:
                raise PipelineError(f"scene '{sid}': {src.name} must declare data-composition-id=\"{sid}\" and window.__timelines[\"{sid}\"]")
            shutil.copyfile(src, dst)                 # byte-exact copy of the hand-authored scene
            for c in s.get("cues") or []:           # optional cues in scene-local time
                cue(c[0], s["start"] + float(c[1]), c[2])
            continue
        if s["type"] == "footage":
            if s["video"] not in footage_ids:
                raise PipelineError(f"scene '{sid}': footage id '{s['video']}' is not in project.footage")
            if "audio" not in s:                       # keep the raw clip's own sound by default;
                s = {**s, "audio": s["video"] != ar}   # mute only when this clip is the aroll dialogue source
        s = esc(s)
        ctx = {"s": s, "W": W, "H": H, "u": u, "id": sid, "T": T, "G": G}
        if s["type"] == "chat":
            ctx["L"] = chat_layout(s, W, H, sid)
        html = env.get_template(f"{s['type']}.html.j2").render(**ctx)
        dst.write_text(html, encoding="utf-8", newline="\n")
        log.info("  %-8s %-8s %5.2fs @ %6.2fs", sid, s["type"], s["duration"], s["start"])

    captions = False
    prog = p.duration if (p.auto and p.cfg["autoedit"].get("progress_bar")) else 0
    if p.cfg["captions"]["enabled"] or prog:
        words = speech_words(p, for_captions=True) if p.cfg["captions"]["enabled"] else []
        if p.cfg["captions"]["enabled"] and not words:
            raise PipelineError("captions.enabled needs words: transcribe.enabled with aroll, or a voice with word timings")
        # no captions over full-screen graphics (they carry their own text)
        busy = [(x["start"], x["start"] + x["duration"]) for x in scenes if x["type"] in ("list", "kinetic", "card", "endcard", "chat")]
        words = [w for w in words if not any(a - 0.05 <= w["start"] < b for a, b in busy)]
        cst = p.cfg["captions"].get("style")
        mw = 1 if cst == "slam" else min(3, int(p.cfg["captions"]["max_words"])) if cst in ("reel", "pill", "highlight", "color") else int(p.cfg["captions"]["max_words"])
        P = caption_phrases(esc(words), mw)
        C = dict(p.cfg["captions"])
        if p.auto:                                  # never on the speaker's face
            safe = p.plan().get("safe") or {}
            if safe.get("caption_y_min") and C.get("style") != "subtle":
                C["reel_y"] = max(float(C.get("reel_y", 0.74)), safe["caption_y_min"])
        for ph in P:   # a caption never hangs over the start of a graphic
            nxt = [b0 for b0, _ in busy if b0 > ph["start"]]
            if nxt:
                ph["end"] = round(min(ph["end"], min(nxt) - 0.08), 3)
        html = env.get_template("captions.html.j2").render(P=P, C=C, PROG=prog, W=W, H=H, u=u, T=T)
        (hf / "compositions" / "captions.html").write_text(html, encoding="utf-8", newline="\n")
        captions = True

    css = "\n".join(p.path(c).read_text(encoding="utf-8") for c in p.cfg["style"]["css"])
    if p.cfg.get("theme"):
        css += theme_css(T)

    # persistent brand watermark / handle, drawn over every frame
    wm = (p.cfg.get("brand") or {}).get("watermark") or {}
    watermark = None
    if wm.get("text") or wm.get("logo"):
        logo_rel = None
        if wm.get("logo"):
            lsrc = p.path(wm["logo"])
            if not lsrc.exists():
                raise PipelineError(f"brand.watermark.logo not found: {lsrc}")
            copy_into(lsrc, hf / "assets" / "brand" / lsrc.name)
            logo_rel = f"assets/brand/{lsrc.name}"
        watermark = {"text": esc(wm.get("text")) if wm.get("text") else None, "logo": logo_rel,
                     "position": wm.get("position", "bottom-right"), "opacity": float(wm.get("opacity", 0.8)),
                     "size": int(wm.get("size", 30)), "margin": int(wm.get("margin", 54))}

    idx_env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(p.root / "templates")), autoescape=False)
    index = idx_env.get_template("index.html.j2").render(
        W=W, H=H, u=u, T=T, fps=p.fps, duration=num(p.duration), scenes=[{**x, 'start': str(float(x['start'])), 'duration': str(float(x['duration']))} for x in scenes], css=css, gsap=p.cfg["style"]["gsap"],
        motion_blur=p.cfg["canvas"].get("motion_blur", True), captions=captions, watermark=watermark, project_file=str(p.dir / "project.yaml"))
    (hf / "index.html").write_text(index, encoding="utf-8", newline="\n")
    write_json(p.build / "compose" / "cues.json", {"cues": sorted(cues, key=lambda c: c[1]), "ducks": sorted(set(ducks))})
    log.info("  %d scenes, %.2fs, %d auto cues, %d click ducks%s", len(scenes), p.duration, len(cues), len(set(ducks)),
             ", captions" if captions else "")
    return {"hf": str(hf), "scenes": len(scenes), "auto_cues": len(cues)}
