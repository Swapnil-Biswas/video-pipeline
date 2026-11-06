"""Stage · transcribe: speech -> timed words and phrases (Whisper on the GPU, via transformers).

1. Word timings in the spoken language: Whisper large-v3-turbo with word timestamps (sequential long-form,
   no chunk stitching, which repeated text at chunk seams in testing).
2. Phrases: words grouped at pauses (gap >= transcribe.phrase_gap) and capped in length.
3. Optional English: each phrase's own audio slice is translated by Whisper large-v3 (turbo cannot translate),
   so the English caption stays timed to the real phrase. Words inside a phrase are spread by character length.

Source audio: the A-roll footage (project.aroll.video) or the voice-over track."""
from __future__ import annotations

import re
from pathlib import Path

from ..util import PipelineError, log, read_json, run, write_json

SR = 16000


def _audio_source(p) -> Path | None:
    a = p.cfg.get("aroll") or {}
    if a.get("video"):
        man = read_json(p.build / "ingest" / "manifest.json", {}) or {}
        f = next((x for x in man.get("footage", []) if x["id"] == a["video"]), None)
        if not f:
            raise PipelineError(f"aroll.video '{a['video']}' is not an ingested footage id")
        return Path(f["path"])
    vo = p.build / "voice" / "vo.wav"
    return vo if vo.exists() else None


def _pipe(model: str, dev: str):
    import torch
    from transformers import pipeline
    return pipeline("automatic-speech-recognition", model=model, device=0 if dev == "cuda" else -1,
                    torch_dtype=torch.float16 if dev == "cuda" else torch.float32)


GEN = {"condition_on_prev_tokens": False, "temperature": (0.0, 0.2, 0.4), "compression_ratio_threshold": 1.35,
       "logprob_threshold": -1.0}


def phrases_from_words(words: list[dict], gap: float, max_s: float, max_words: int) -> list[dict]:
    out, cur = [], []
    for w in words:
        if cur and (w["start"] - cur[-1]["end"] >= gap or w["end"] - cur[0]["start"] > max_s or len(cur) >= max_words):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return [{"start": c[0]["start"], "end": c[-1]["end"], "orig": " ".join(x["text"] for x in c).strip(), "words": c} for c in out]


def spread_words(text: str, start: float, end: float) -> list[dict]:
    toks = text.split()
    if not toks:
        return []
    weights = [len(t) + 2 for t in toks]
    tot, t, out = sum(weights), start, []
    for tok, w in zip(toks, weights):
        d = (end - start) * w / tot
        out.append({"text": tok, "start": round(t, 3), "end": round(t + d * 0.92, 3)})
        t += d
    return out


def fix_text(text: str, fixes: list) -> str:
    for f in fixes:
        text = re.sub(f[0], f[1], text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def spread_on_speech(text: str, win: list[dict]) -> list[dict]:
    """Place translated words over the cumulative *speech* time of the source words (pauses skipped)."""
    toks = text.split()
    if not toks:
        return []
    spans = [(w["start"], max(w["end"], w["start"] + 0.05)) for w in win]
    total = sum(b - a for a, b in spans)

    def at(x):  # speech time -> real time
        for a, b in spans:
            if x <= b - a:
                return a + x
            x -= b - a
        return spans[-1][1]
    weights = [len(t) + 2 for t in toks]
    tw, acc, out = sum(weights), 0.0, []
    for tok, w in zip(toks, weights):
        d = total * w / tw
        out.append({"text": tok, "start": round(at(acc), 3), "end": round(at(acc + d * 0.95), 3)})
        acc += d
    return out


def run_stage(p) -> dict:
    tc = p.cfg["transcribe"]
    out = p.build / "transcribe"
    if not tc.get("enabled"):
        return {"transcript": None}
    src = _audio_source(p)
    if src is None:
        raise PipelineError("transcribe needs aroll.video (talking footage) or a voice track")
    out.mkdir(parents=True, exist_ok=True)
    wav = out / "speech16k.wav"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", str(SR), str(wav)])
    try:
        import numpy as np
        import soundfile as sf
        import torch
    except ImportError as e:
        raise PipelineError(f"transcribe needs torch + transformers ({e}); see README") from e
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    y, _ = sf.read(wav, dtype="float32")
    log.info("  loading %s on %s", tc["model"], dev)
    asr = _pipe(tc["model"], dev)
    lang = tc.get("language")
    if not lang:  # detect on the first 30 s
        r = asr({"raw": y[:SR * 30], "sampling_rate": SR}, return_timestamps=True, return_language=True, generate_kwargs=dict(GEN))
        lang = (r.get("chunks") or [{}])[0].get("language") or "english"
        log.info("  detected language: %s", lang)
    r = asr({"raw": y, "sampling_rate": SR}, return_timestamps="word", generate_kwargs={**GEN, "language": lang, "task": "transcribe"})
    words = []
    for c in r["chunks"]:
        a, b = c["timestamp"]
        t = c["text"].strip()
        if not t:
            continue
        if b is None:
            b = a + 0.3
        if words and re.fullmatch(r"[%.,!?،۔]+", t):        # glue punctuation/percent to the previous word
            words[-1]["text"] += t
            words[-1]["end"] = round(b, 3)
            continue
        words.append({"text": t, "start": round(a, 3), "end": round(b, 3)})
    del asr
    phrases = phrases_from_words(words, tc["phrase_gap"], tc["max_phrase_s"], tc["max_phrase_words"])
    english = str(lang).lower() in ("en", "english")
    translate = tc.get("translate_to_english")
    translate = (not english) if translate in (None, "auto") else bool(translate)
    fixes = tc.get("fixes") or []
    if translate:
        # translate sentence-sized windows (context matters for idioms), then lay the English words back onto
        # the window's real speech time (pauses skipped), so captions stay in sync with the voice
        windows, cur = [], []
        for w in words:
            if cur and ((w["start"] - cur[-1]["end"] >= tc["window_gap"] and w["end"] - cur[0]["start"] > 2.0)
                        or w["end"] - cur[0]["start"] > tc["max_window_s"]):
                windows.append(cur)
                cur = []
            cur.append(w)
        if cur:
            windows.append(cur)
        log.info("  translating %d windows with %s", len(windows), tc["translate_model"])
        tr = _pipe(tc["translate_model"], dev)
        cap_words, phrases = [], []
        for wi, win in enumerate(windows):
            a, b = max(0.0, win[0]["start"] - 0.1), win[-1]["end"] + 0.15
            res = tr({"raw": y[int(a * SR): int(b * SR)], "sampling_rate": SR},
                     generate_kwargs={"task": "translate", "language": lang, "temperature": 0.0})
            text = fix_text(res["text"].strip(), fixes)
            phrases.append({"start": win[0]["start"], "end": win[-1]["end"], "orig": " ".join(x["text"] for x in win), "text": text})
            for w in spread_on_speech(text, win):
                cap_words.append({**w, "phrase": wi})
        del tr
    else:
        cap_words = []
        for i, ph in enumerate(phrases):
            ph["text"] = fix_text(ph["orig"], fixes)
            for w in ph["words"]:
                cap_words.append({**w, "phrase": i})
    data = {"language": lang, "translated": translate, "source": str(src), "words": words,
            "phrases": [{k: v for k, v in ph.items() if k != "words"} for ph in phrases], "caption_words": cap_words}
    write_json(out / "transcript.json", data)
    for ph in phrases:
        log.info("    %6.2f-%6.2f  %s", ph["start"], ph["end"], ph["text"][:90])
    log.info("  %d words, %d phrases (%s%s)", len(words), len(phrases), lang, " -> English" if translate else "")
    return {"transcript": str(out / "transcript.json"), "language": lang, "phrases": len(phrases)}
