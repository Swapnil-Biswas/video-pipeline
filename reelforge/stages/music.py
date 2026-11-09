"""Stage 3 · music: generate takes with MusicGen (GPU), score them objectively, arrange the best one to the film.

Ported from the original scripts: scratchpad/music/batch_reel2.py (generation), score.py (take scoring)
and the original arranger (stretch to BPM, beat on the drop, low-passed intro, master)."""
from __future__ import annotations

import json
from pathlib import Path

from ..util import PipelineError, log, read_json, run, write_json


# ---------- generation (MusicGen via transformers) ----------
def generate(p, out_dir: Path) -> list[Path]:
    g = p.cfg["music"]["generate"]
    prompts = g.get("prompts") or p.prompts["musicgen"][g["prompts_key"]]
    out_dir.mkdir(parents=True, exist_ok=True)
    expected = [out_dir / f"take_{seed}_p{i % len(prompts)}.wav" for i, seed in enumerate(g["seeds"])]
    if all(x.exists() for x in expected):
        log.info("  %d takes cached", len(expected))
        return expected
    try:
        import numpy as np
        import soundfile as sf
        import torch
        from transformers import AutoProcessor, MusicgenForConditionalGeneration
    except ImportError as e:
        raise PipelineError(f"music.mode=generate needs torch + transformers ({e}); see README") from e
    if not torch.cuda.is_available():
        log.warning("  CUDA not available: MusicGen will run on CPU (slow)")
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if dev == "cuda" else torch.float32
    log.info("  loading %s on %s", g["model"], dev)
    proc = AutoProcessor.from_pretrained(g["model"])
    model = MusicgenForConditionalGeneration.from_pretrained(g["model"], torch_dtype=dtype, low_cpu_mem_usage=True).to(dev)
    sr = model.config.audio_encoder.sampling_rate
    for i, (seed, dst) in enumerate(zip(g["seeds"], expected)):
        if dst.exists():
            continue
        prompt = prompts[i % len(prompts)]
        torch.manual_seed(seed)
        inp = proc(text=[prompt], padding=True, return_tensors="pt").to(dev)
        a = model.generate(**inp, do_sample=True, guidance_scale=g["guidance_scale"],
                           max_new_tokens=g["max_new_tokens"])[0].float().cpu().numpy()
        a = a / max(1e-6, float(np.abs(a).max())) * 0.89
        sf.write(dst, a.T, sr)
        log.info("  wrote %s (%.1fs)", dst.name, a.shape[-1] / sr)
    del model
    return expected


# ---------- scoring (score.py) ----------
def _bands(y, sr):
    import librosa
    import numpy as np
    S = np.abs(librosa.stft(y, n_fft=4096)) ** 2
    f = librosa.fft_frequencies(sr=sr, n_fft=4096)
    tot = S.sum()
    edges = [20, 60, 150, 400, 1000, 2500, 6000, 12000]
    return np.array([S[(f >= a) & (f < b)].sum() / tot for a, b in zip(edges[:-1], edges[1:])])


def score(takes: list[Path], refs: list[Path]) -> list[dict]:
    import librosa
    import numpy as np
    ref_b = np.mean([_bands(*librosa.load(str(r), sr=32000)) for r in refs], axis=0) if refs else None
    rows = []
    for t in takes:
        y, sr = librosa.load(str(t), sr=32000, mono=True)
        dur = len(y) / sr
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
        bt = librosa.frames_to_time(beats, sr=sr)
        ibi = np.diff(bt)
        reg = float(np.std(ibi) / np.mean(ibi)) if len(ibi) > 4 else 9.0
        rms = librosa.feature.rms(y=y, hop_length=1024)[0]
        db = 20 * np.log10(rms + 1e-9)
        dropout = float(np.mean(db < (np.median(db) - 15)))           # near-silent share (take 303 failed on this)
        seg = np.array([d.mean() for d in np.array_split(db, max(1, int(dur // 5)))])
        spread = float(np.std(seg))
        dist = float(np.sum(np.abs(np.log((_bands(y, sr) + 1e-6) / (ref_b + 1e-6))))) if ref_b is not None else 0.0
        # lower is better; weights favour no dropouts, steady beat, steady energy, closeness to the reference
        total = dropout * 40 + reg * 10 + spread * 0.5 + dist * 0.3
        rows.append({"take": str(t), "duration": round(dur, 2), "tempo": round(float(np.atleast_1d(tempo)[0]), 1),
                     "beat_irregularity": round(reg, 3), "dropout_share": round(dropout, 3), "energy_spread_db": round(spread, 2),
                     "spectral_distance": round(dist, 2), "score": round(total, 3)})
    rows.sort(key=lambda r: r["score"])
    return rows


# ---------- arrangement (tools/music.py) ----------
def arrange(src: Path, out: Path, film: float, a: dict, work: Path) -> dict:
    import librosa
    import numpy as np
    import soundfile as sf
    SR = 48000
    work.mkdir(parents=True, exist_ok=True)
    y, sr = librosa.load(str(src), sr=SR, mono=False)
    y = np.atleast_2d(y)
    tempo, _ = librosa.beat.beat_track(y=librosa.to_mono(y), sr=sr)
    src_bpm = float(np.atleast_1d(tempo)[0])
    ratio = (a["bpm"] / src_bpm) if a.get("bpm") else 1.0
    sf.write(work / "in.wav", y.T, sr)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(work / "in.wav"), "-af", f"atempo={ratio:.6f}", str(work / "st.wav")])
    y, sr = sf.read(work / "st.wav", always_2d=True)
    y = y.T
    mono = y.mean(axis=0).astype(np.float32)
    drop = float(a.get("drop") or 0.0)
    _, beats = librosa.beat.beat_track(y=mono, sr=sr, start_bpm=a.get("bpm") or src_bpm, tightness=600)
    bt = librosa.frames_to_time(beats, sr=sr)
    dur = y.shape[1] / sr
    onset = librosa.onset.onset_strength(y=mono, sr=sr)
    ot = librosa.times_like(onset, sr=sr)
    cands = [b - drop for b in bt if b - drop >= 0 and b - drop + film <= dur]
    looped = 0
    if cands:
        s0 = max(cands, key=lambda s: onset[np.argmin(np.abs(ot - (s + drop)))])
        seg = y[:, int(s0 * sr): int((s0 + film) * sr)]
    else:
        # the take is shorter than the film: loop whole bars, crossfading on the downbeat
        bpm_eff = a.get("bpm") or src_bpm
        bar = 4 * 60.0 / bpm_eff
        early = [b for b in bt if b < min(dur * 0.25, 4 * bar)] or [0.0]
        s0 = float(max(early, key=lambda b: onset[np.argmin(np.abs(ot - b))]))
        n_bars = int((dur - s0 - 0.25) // bar)
        if n_bars < 2:
            raise PipelineError(f"music take {src.name} is too short to loop ({dur:.1f}s)")
        n_bars -= n_bars % 2                      # loop an even number of bars (phrases stay square)
        L = int(n_bars * bar * sr)
        xf = int(float(a.get("loop_crossfade", 0.04)) * sr)
        piece = y[:, int(s0 * sr): int(s0 * sr) + L + xf]
        need = int(film * sr) + xf
        out_ = piece[:, :L].copy()
        fade_in = np.linspace(0, 1, xf) if xf else None
        while out_.shape[1] < need:
            # at each loop point the natural run-out (piece[L:L+xf]) fades under the loop start (piece[:xf]);
            # every repeat is exactly L samples, so the bar grid never drifts
            if xf:
                joint = piece[:, L:L + xf] * (1 - fade_in) + piece[:, :xf] * fade_in
                out_ = np.concatenate([out_, joint, piece[:, xf:L]], axis=1)
            else:
                out_ = np.concatenate([out_, piece[:, :L]], axis=1)
            looped += 1
        seg = out_[:, :int(film * sr)]
        log.info("  take is %.1fs, film %.1fs: looping %d bars (%.2fs) x%d with %d ms crossfades", dur, film, n_bars,
                 n_bars * bar, looped + 1, int(xf / sr * 1000))
    sf.write(work / "seg.wav", seg.T, sr)
    if a.get("intro_lowpass") and drop > 0:
        def lp(name, cut, vol):
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(work / "seg.wav"), "-af",
                 f"lowpass=f={cut}:p=2,volume={vol}", str(work / name)])
            return sf.read(work / name, always_2d=True)[0].T
        dark, mid = lp("d.wav", a["dark_cut"], a["dark_gain"]), lp("m.wav", a["mid_cut"], a["mid_gain"])
        n = min(seg.shape[1], dark.shape[1], mid.shape[1])
        t = np.arange(n) / sr
        # original: opens from 2.0 s before the drop over 1.9 s (about the last bar at 124 BPM)
        w_mid = np.clip((t - (drop - a.get("open_s", 2.0))) / a.get("open_len", 1.9), 0, 1) ** 2
        w_full = (t >= drop).astype(float)
        xf, i = int(0.02 * sr), int(drop * sr)
        w_full[max(0, i - xf):i] = np.linspace(0, 1, min(xf, i))
        bed = (dark[:, :n] * (1 - w_mid) + mid[:, :n] * w_mid) * (1 - w_full) + seg[:, :n] * w_full
    else:
        bed = seg
    need = int(film * sr)
    if bed.shape[1] < need:
        log.warning("  take is %.1fs after stretch, film needs %.1fs: padding with silence before the fade", bed.shape[1] / sr, film)
        bed = np.pad(bed, ((0, 0), (0, need - bed.shape[1])))
    sf.write(work / "arr.wav", bed.T, sr)
    chain = (a["master_chain"] + f",afade=t=in:st=0:d=0.08,afade=t=out:st={max(0.0, film - a['fade_out'])}:d={a['fade_out']}"
             f",loudnorm=I={a['lufs']}:TP=-1.5:LRA=8")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(work / "arr.wav"), "-af", chain, "-ar", str(SR),
         "-t", f"{film}", str(out)])
    info = {"source": str(src), "source_bpm": round(src_bpm, 2), "stretch": round(ratio, 4), "start_offset": round(float(s0), 3),
            "beat_on": round(float(s0 + drop), 3), "film": film}
    log.info("  arranged %s: %.1f BPM x%.4f, start %.3fs, beat on drop %.2fs", src.name, src_bpm, ratio, s0, drop)
    return info


def run_stage(p) -> dict:
    m = p.cfg["music"]
    out = p.build / "music"
    out.mkdir(parents=True, exist_ok=True)
    bed = out / "bed.wav"
    film = p.duration
    if m["mode"] == "none":
        if bed.exists():
            bed.unlink()
        return {"bed": None}
    if m["mode"] == "file":
        src = p.path(m["file"])
        if not src.exists():
            raise PipelineError(f"music.file not found: {src}")
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-af",
             f"apad,afade=t=out:st={max(0, film - 2)}:d=2,loudnorm=I={m['arrange']['lufs']}:TP=-1.5", "-ar", "48000", "-t", str(film), str(bed)])
        return {"bed": str(bed)}
    refs = [Path(r["path"]) for r in (read_json(p.build / "ingest" / "manifest.json", {}) or {}).get("references", [])]
    ref_wavs = sorted((p.build / "analyze").glob("ref*.wav"))
    if m["mode"] == "generate":
        takes = generate(p, out / "takes")
    else:  # take
        if m.get("take"):
            takes = [p.path(m["take"])]
        elif m.get("takes_dir"):
            takes = sorted(p.path(m["takes_dir"]).glob("*.wav"))
        else:
            raise PipelineError("music.mode=take needs music.take or music.takes_dir")
    for t in takes:
        if not t.exists():
            raise PipelineError(f"music take not found: {t}")
    if len(takes) > 1:
        rows = score(takes, ref_wavs)
        write_json(out / "scores.json", rows)
        for r in rows:
            log.info("  %-44s score %.2f  dropout %.3f  irregularity %.3f  dist %.2f", Path(r["take"]).name, r["score"],
                     r["dropout_share"], r["beat_irregularity"], r["spectral_distance"])
        chosen = Path(rows[0]["take"])
    else:
        chosen = takes[0]
    info = arrange(chosen, bed, film, m["arrange"], out / "work")
    write_json(out / "music.json", info)
    return {"bed": str(bed), **info, "refs": [str(r) for r in refs]}
