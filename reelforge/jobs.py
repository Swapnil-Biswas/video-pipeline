"""Production jobs: "edit my footage in the style of this reference video".

A job is a folder (jobs/<id>/) holding the validated inputs, a generated project.yaml, the build, logs and a
job.json state file. Each pipeline run is a separate process (crash isolation, GPU memory freed, killable).

States: queued -> running -> awaiting_approval -> rendering -> done   (or failed / cancelled)
With auto_approve the job goes straight from running to rendering."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import yaml

from .config import ROOT
from .util import PipelineError, ffprobe_json, read_json, write_json

JOBS_DIR = Path(os.environ.get("REELFORGE_JOBS_DIR") or (ROOT / "jobs"))
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
LIMITS = {
    "max_upload_mb": float(os.environ.get("REELFORGE_MAX_UPLOAD_MB", 1024)),
    "max_footage_s": float(os.environ.get("REELFORGE_MAX_FOOTAGE_S", 600)),
    "max_reference_s": float(os.environ.get("REELFORGE_MAX_REFERENCE_S", 300)),
    "max_footage_files": int(os.environ.get("REELFORGE_MAX_FOOTAGE_FILES", 10)),
    "stage_timeout_s": float(os.environ.get("REELFORGE_JOB_TIMEOUT_S", 3 * 3600)),
}
DEFAULT_OPTIONS = {
    "aspect": "footage",          # footage | reference | 9:16 | 16:9 | 1:1
    "resolution": "1080",         # 1080 | 4k
    "fps": "auto",                # auto (reference: 60 if >= 50 else 30) | 24 | 25 | 30 | 60
    "mode": "auto",               # auto | talk | montage
    "captions": True,
    "caption_language": "english",  # english (translate if needed) | original
    "hook_text": None,            # "Want to be a [creator?]"  ([..] = accent pill); talk mode derives one if None
    "outro_text": None,           # "Follow for [more]"
    "music": "library",           # library | generate (MusicGen; non-commercial weights) | none
    "music_volume": 0.5,
    "max_duration": 60,           # montage cap / safety cap (s)
    "grade": True,                # match the reference's colour grade
    "auto_approve": False,
    "transcript_fixes": [],       # [[regex, replacement], ...]
}


def new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]


def safe_name(name: str, fallback: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name or fallback).name)[:80].strip("._") or fallback
    return stem


def job_dir(job_id: str) -> Path:
    if not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{8}", job_id or ""):
        raise PipelineError("invalid job id")
    return JOBS_DIR / job_id


def load(job_id: str) -> dict:
    j = read_json(job_dir(job_id) / "job.json")
    if j is None:
        raise PipelineError("job not found")
    return j


def save(j: dict) -> None:
    j["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    write_json(job_dir(j["id"]) / "job.json", j)


def validate_video(path: Path, max_s: float, what: str) -> dict:
    if path.suffix.lower() not in VIDEO_EXT:
        raise PipelineError(f"{what}: unsupported file type {path.suffix or '(none)'}; use one of {sorted(VIDEO_EXT)}")
    if path.stat().st_size > LIMITS["max_upload_mb"] * 2**20:
        raise PipelineError(f"{what}: larger than {LIMITS['max_upload_mb']:.0f} MB")
    try:
        info = ffprobe_json(path)
    except PipelineError as e:
        raise PipelineError(f"{what}: not a readable video ({e})") from e
    v = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    if not v:
        raise PipelineError(f"{what}: has no video stream")
    dur = float(info.get("format", {}).get("duration") or 0)
    if dur <= 0.5:
        raise PipelineError(f"{what}: too short ({dur:.2f}s)")
    if dur > max_s:
        raise PipelineError(f"{what}: {dur:.0f}s is longer than the {max_s:.0f}s limit")
    w, h = v[0].get("width") or 0, v[0].get("height") or 0
    if w < 160 or h < 160:
        raise PipelineError(f"{what}: resolution {w}x{h} is too small")
    return {"duration": dur, "width": w, "height": h, "rotation": _rotation(v[0]), "has_audio": any(s.get("codec_type") == "audio" for s in info["streams"])}


def _rotation(stream: dict) -> int:
    for sd in stream.get("side_data_list") or []:
        if "rotation" in sd:
            return int(sd["rotation"]) % 360
    return int((stream.get("tags") or {}).get("rotate", 0)) % 360


def create(footage: list[Path], reference: Path, options: dict | None = None, move: bool = False) -> dict:
    """Validate inputs, copy them into a new job folder, write its project.yaml. Returns the job dict."""
    opts = {**DEFAULT_OPTIONS, **(options or {})}
    _check_options(opts)
    if not footage:
        raise PipelineError("at least one footage file is required")
    if len(footage) > LIMITS["max_footage_files"]:
        raise PipelineError(f"at most {LIMITS['max_footage_files']} footage files")
    jid = new_id()
    d = JOBS_DIR / jid
    (d / "inputs").mkdir(parents=True)
    try:
        ref_dst = d / "inputs" / ("reference" + reference.suffix.lower())
        (shutil.move if move else shutil.copy2)(str(reference), ref_dst)
        rinfo = validate_video(ref_dst, LIMITS["max_reference_s"], "reference")
        finfo, fpaths = [], []
        for i, f in enumerate(footage):
            dst = d / "inputs" / f"footage{i + 1}{f.suffix.lower()}"
            (shutil.move if move else shutil.copy2)(str(f), dst)
            finfo.append(validate_video(dst, LIMITS["max_footage_s"], f"footage {i + 1}"))
            fpaths.append(dst)
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise
    project = build_project(jid, fpaths, finfo, ref_dst, rinfo, opts)
    (d / "project.yaml").write_text(yaml.safe_dump(project, sort_keys=False, allow_unicode=True), encoding="utf-8")
    j = {"id": jid, "state": "queued", "stage": None, "options": opts, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "inputs": {"reference": {"file": ref_dst.name, **rinfo}, "footage": [{"file": p.name, **x} for p, x in zip(fpaths, finfo)]},
         "error": None, "result": None}
    save(j)
    return j


def _check_options(o: dict) -> None:
    errs = []
    if o["aspect"] not in ("footage", "reference", "9:16", "16:9", "1:1"):
        errs.append("aspect must be footage | reference | 9:16 | 16:9 | 1:1")
    if str(o["resolution"]) not in ("1080", "4k"):
        errs.append("resolution must be 1080 | 4k")
    if str(o["fps"]) not in ("auto", "24", "25", "30", "60"):
        errs.append("fps must be auto | 24 | 25 | 30 | 60")
    if o["mode"] not in ("auto", "talk", "montage"):
        errs.append("mode must be auto | talk | montage")
    if o["music"] not in ("library", "generate", "none"):
        errs.append("music must be library | generate | none")
    if o["caption_language"] not in ("english", "original"):
        errs.append("caption_language must be english | original")
    for k in ("hook_text", "outro_text"):
        if o.get(k) is not None and (not isinstance(o[k], str) or len(o[k]) > 120):
            errs.append(f"{k} must be a string of at most 120 characters")
    if not (5 <= float(o["max_duration"]) <= 600):
        errs.append("max_duration must be between 5 and 600 seconds")
    if not isinstance(o.get("transcript_fixes"), list) or any(not isinstance(x, list) or len(x) != 2 for x in o["transcript_fixes"]):
        errs.append("transcript_fixes must be a list of [regex, replacement] pairs")
    else:
        for pat, _ in o["transcript_fixes"]:
            try:
                re.compile(pat)
            except re.error:
                errs.append(f"transcript_fixes: bad regex {pat!r}")
    if errs:
        raise PipelineError("invalid options: " + "; ".join(errs))


def _display_wh(info: dict) -> tuple[int, int]:
    w, h = info["width"], info["height"]
    return (h, w) if info.get("rotation") in (90, 270) else (w, h)


def build_project(jid, fpaths, finfo, ref, rinfo, o) -> dict:
    fw, fh = _display_wh(finfo[0])
    rw, rh = _display_wh(rinfo)
    asp = o["aspect"]
    if asp == "footage":
        r = fw / fh
    elif asp == "reference":
        r = rw / rh
    else:
        a, b = asp.split(":")
        r = int(a) / int(b)
    if r < 0.85:
        W, H, res = 1080, 1920, "portrait"
    elif r > 1.18:
        W, H, res = 1920, 1080, "landscape"
    else:
        W, H, res = 1080, 1080, "square"
    if str(o["resolution"]) == "4k":
        res += "-4k"
    if str(o["fps"]) == "auto":
        ref_fps = 30
        try:
            st = next(s for s in ffprobe_json(ref)["streams"] if s["codec_type"] == "video")
            n, dn = st["r_frame_rate"].split("/")
            ref_fps = 60 if float(n) / float(dn or 1) >= 50 else 30
        except Exception:
            pass
        fps = ref_fps
    else:
        fps = int(o["fps"])
    speech_clip = fpaths[0]
    lines = lambda t: [{"text": t, "size": 130}] if t else None
    proj = {
        "name": f"job-{jid}",
        "build_dir": "build",
        "canvas": {"width": W, "height": H, "fps": fps, "motion_blur": True},
        "references": [{"src": str(ref)}],
        "footage": [{"id": f"clip{i + 1}", "src": str(p)} for i, p in enumerate(fpaths)],
        "aroll": {"video": "clip1"} if o["mode"] != "montage" and finfo[0]["has_audio"] else {"video": None},
        "style": {"from_reference": True, "grade": bool(o["grade"])},
        "transcribe": {"enabled": o["mode"] != "montage" and finfo[0]["has_audio"],
                       "translate_to_english": o["caption_language"] == "english" and "auto" or False,
                       "fixes": o.get("transcript_fixes") or []},
        "scenes": "auto",
        "autoedit": {"mode": o["mode"], "max_duration": float(o["max_duration"]),
                     "hook_text": [[o["hook_text"], 96]] if o.get("hook_text") else None,
                     "outro": ({"type": "kinetic", "duration": 2.6, "entry": "whip-left", "lines": lines(o["outro_text"])}
                               if o.get("outro_text") else None)},
        "captions": {"enabled": bool(o["captions"])},
        "music": ({"mode": "none"} if o["music"] == "none" else
                  {"mode": "generate", "arrange": {"drop": 0, "intro_lowpass": False}, "volume": float(o["music_volume"]),
                   "generate": {"seeds": [11, 22]}} if o["music"] == "generate" else
                  {"mode": "take", "takes_dir": str(ROOT / "assets" / "music" / "library"),
                   "arrange": {"drop": 0, "intro_lowpass": False}, "volume": float(o["music_volume"])}),
        "voice": {"mode": "none"},
        "render": {"resolution": res, "quality": "delivery", "gpu": True},
    }
    if speech_clip and not finfo[0]["has_audio"]:
        proj["autoedit"]["mode"] = "montage"
    return proj


# ---------------------------------------------------------------- running
def _run_cli(j: dict, args: list[str]) -> int:
    d = job_dir(j["id"])
    log = open(d / "pipeline.log", "a", encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "HF_HUB_DISABLE_SYMLINKS_WARNING": "1"}
    p = subprocess.Popen([sys.executable, "-m", "reelforge", "run", str(d), *args], cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT, env=env)
    _PROCS[j["id"]] = p
    try:
        return p.wait(timeout=LIMITS["stage_timeout_s"])
    except subprocess.TimeoutExpired:
        p.kill()
        return 124
    finally:
        _PROCS.pop(j["id"], None)
        log.close()


_PROCS: dict[str, subprocess.Popen] = {}


def _last_error(d: Path) -> str:
    try:
        lines = (d / "pipeline.log").read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return "pipeline failed"
    fails = [l for l in lines if "FAILED" in l or "crashed" in l or l.startswith("error:")]
    return (fails[-1] if fails else (lines[-1] if lines else "pipeline failed")).strip()[:500]


def progress(j: dict) -> dict:
    st = read_json(job_dir(j["id"]) / "build" / "state.json", {}) or {}
    from .cli import STAGES
    done = [s for s in STAGES if (st.get("stages") or {}).get(s, {}).get("done")]
    return {"stages_done": done, "stages_total": len(STAGES), "percent": round(100 * len(done) / len(STAGES))}


def process(job_id: str) -> dict:
    """Run one job as far as it can go (to the preview checkpoint, or to the end when approved / auto_approve)."""
    j = load(job_id)
    if j["state"] in ("done", "failed", "cancelled", "awaiting_approval"):
        return j
    d = job_dir(job_id)
    if j["state"] in ("queued", "running"):
        j["state"], j["stage"] = "running", "edit"
        save(j)
        args = ["--yes"] if j["options"].get("auto_approve") else []
        rc = _run_cli(j, args)
        j = load(job_id)
        if j["state"] == "cancelled":
            return j
        if rc != 0:
            j.update(state="failed", error=_last_error(d))
            save(j)
            return j
        if not j["options"].get("auto_approve"):
            pv = read_json(d / "build" / "preview" / "preview.json", {}) or {}
            j.update(state="awaiting_approval", stage="preview",
                     preview=[str(Path(x).relative_to(d)).replace("\\", "/") for x in pv.get("sheets", []) if "review-" in x])
            save(j)
            return j
        return _finish(j, d)
    if j["state"] == "rendering":
        rc = _run_cli(j, ["--from", "render"])
        j = load(job_id)
        if rc != 0:
            j.update(state="failed", error=_last_error(d))
            save(j)
            return j
        return _finish(j, d)
    return j


def _finish(j, d):
    finals = sorted((d / "build" / "final").glob("*.mp4"))
    audit = read_json(d / "build" / "audit" / "audit.json", {}) or {}
    if not finals:
        j.update(state="failed", error="no final video was produced")
    else:
        j.update(state="done", stage="audit", result={"video": str(finals[-1].relative_to(d)).replace("\\", "/"),
                 "thumbnail": str(Path(audit["thumbnail"]).relative_to(d)).replace("\\", "/") if audit.get("thumbnail") else None,
                 "audit": {k: audit.get(k) for k in ("width", "height", "fps", "duration", "lufs", "true_peak_dbfs", "size_mb")}})
    save(j)
    return j


def approve(job_id: str, note: str = "") -> dict:
    j = load(job_id)
    if j["state"] != "awaiting_approval":
        raise PipelineError(f"job is {j['state']}, not awaiting approval")
    r = subprocess.run([sys.executable, "-m", "reelforge", "approve", str(job_dir(job_id)), "preview", "--note", note or "approved via API"],
                       cwd=str(ROOT), capture_output=True, text=True)
    if r.returncode != 0:
        raise PipelineError((r.stdout + r.stderr).strip()[-300:])
    j.update(state="rendering", stage="render")
    save(j)
    return j


def cancel(job_id: str) -> dict:
    j = load(job_id)
    if j["state"] in ("done", "failed", "cancelled"):
        return j
    j["state"] = "cancelled"
    save(j)
    p = _PROCS.get(job_id)
    if p and p.poll() is None:
        p.kill()
    return j


class Worker:
    """A single GPU worker thread with a FIFO queue; survives restarts by rescanning the jobs folder."""

    def __init__(self):
        self.q: list[str] = []
        self.lock = threading.Condition()
        self.t = threading.Thread(target=self._loop, daemon=True, name="reelforge-worker")

    def start(self):
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        for d in sorted(JOBS_DIR.iterdir()):
            j = read_json(d / "job.json")
            if j and j.get("state") in ("queued", "running", "rendering"):
                self.submit(j["id"])               # resumes from the last finished stage
        self.t.start()

    def submit(self, job_id: str):
        with self.lock:
            if job_id not in self.q:
                self.q.append(job_id)
            self.lock.notify()

    def position(self, job_id: str) -> int | None:
        with self.lock:
            return self.q.index(job_id) if job_id in self.q else None

    def _loop(self):
        while True:
            with self.lock:
                while not self.q:
                    self.lock.wait()
                jid = self.q[0]
            try:
                process(jid)
            except Exception as e:  # never kill the worker
                try:
                    j = load(jid)
                    j.update(state="failed", error=f"internal error: {e}")
                    save(j)
                except Exception:
                    pass
            with self.lock:
                if self.q and self.q[0] == jid:
                    self.q.pop(0)
