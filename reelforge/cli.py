"""reelforge command line.

  python -m reelforge doctor                          check tools, GPU, Python packages
  python -m reelforge new <name> [--aspect portrait]  scaffold projects/<name>/project.yaml
  python -m reelforge run <project> [--from S] [--to S] [--only S] [--force] [--yes] [--verbose]
  python -m reelforge approve <project> [gate] [--note "..."]   approve the preview checkpoint
  python -m reelforge status <project>
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

from .config import ROOT, load_project
from .util import PipelineError, State, log, run, setup_logging, sha1, which

STAGES = ["ingest", "analyze", "style", "transcribe", "autoedit", "music", "voice", "compose", "sfx", "check", "preview", "render", "master", "audit"]
# which config keys each stage depends on (for skip-if-unchanged)
DEPENDS = {
    "ingest": ["references", "footage", "canvas"],
    "analyze": ["analyze"],
    "style": ["style", "references", "aroll", "footage"],
    "transcribe": ["aroll", "transcribe"],
    "autoedit": ["aroll", "autoedit", "scenes", "canvas", "captions"],
    "music": ["music", "scenes", "duration"],
    "voice": ["voice", "duration"],
    "compose": ["scenes", "canvas", "style", "assets", "captions", "music", "voice", "duration"],
    "sfx": ["sfx", "music", "voice"],
    "check": [], "preview": ["preview"], "render": ["render", "canvas"], "master": ["master"], "audit": ["audit", "master"],
}
ALWAYS_RUN = {"check", "preview", "render", "master", "audit"}


def fingerprint(p, stage: str, prev: str) -> str:
    cfg = {k: p.cfg.get(k) for k in DEPENDS[stage]}
    h = hashlib.sha1((json.dumps(cfg, sort_keys=True, default=str) + prev).encode())
    h.update(sha1(Path(__file__).parent / "stages" / f"{stage}.py").encode())   # engine code is part of the fingerprint
    if stage in ("compose",):
        h.update(sha1(p.root / "templates").encode())
        for s in (p.cfg["scenes"] if isinstance(p.cfg["scenes"], list) else []):
            if s.get("type") == "file":
                h.update(sha1(p.path(s["src"])).encode())
    return h.hexdigest()[:16]


def cmd_run(a) -> int:
    p = load_project(a.project, a.set)
    p.state = State(p.build / "state.json")
    logf = setup_logging(p.build / "logs", a.verbose)
    log.info("reelforge · %s · %dx%d @ %d fps · %.2fs · log %s", p.name, p.W, p.H, p.fps, p.duration, logf)
    stages = STAGES
    if a.only:
        stages = [a.only]
    else:
        i0 = STAGES.index(a.from_) if a.from_ else 0
        i1 = STAGES.index(a.to) if a.to else len(STAGES) - 1
        stages = STAGES[i0:i1 + 1]
    prev = ""
    for name in STAGES:
        fp = fingerprint(p, name, prev)
        if name not in stages:
            prev = p.state.stage(name).get("fingerprint", fp)
            continue
        done = p.state.stage(name)
        if not a.force and name not in ALWAYS_RUN and done.get("done") and done.get("fingerprint") == fp:
            log.info("[%s] unchanged, skipped", name)
            prev = fp
            continue
        log.info("[%s]", name)
        t0 = time.time()
        mod = importlib.import_module(f".stages.{name}", __package__)
        try:
            info = mod.run_stage(p, assume_yes=a.yes) if name == "render" else mod.run_stage(p)
        except PipelineError as e:
            log.error("[%s] FAILED: %s", name, e)
            p.state.invalidate_from(STAGES[STAGES.index(name):])
            return 2
        except Exception:
            log.error("[%s] crashed:\n%s", name, traceback.format_exc())
            p.state.invalidate_from(STAGES[STAGES.index(name):])
            return 3
        p.state.mark(name, fp, seconds=round(time.time() - t0, 1), **{k: v for k, v in (info or {}).items() if isinstance(v, (str, int, float, bool, type(None))) and k not in ('fingerprint', 'done', 'at')})
        log.info("[%s] done in %.1fs", name, time.time() - t0)
        prev = fp
        if name == "style":
            p.reload()                     # reference-derived settings now apply to every later stage
        if name == "preview" and "render" in stages and not a.yes and p.cfg["preview"].get("require_approval", True):
            if p.state.approval("preview").get("status") != "approved":
                log.info("stopped at the preview checkpoint (approve, then run again with --from render)")
                return 0
    final = p.state.stage("master").get("final")
    if final and "master" in stages:
        log.info("final: %s", final)
    return 0


def cmd_approve(a) -> int:
    p = load_project(a.project)
    st = State(p.build / "state.json")
    cur = st.approval(a.gate)
    if not cur:
        print(f"no pending '{a.gate}' checkpoint: run the {a.gate} stage first")
        return 1
    fp = sha1(p.hf / "compositions") + sha1(p.hf / "index.html")
    if cur.get("fingerprint") != fp:
        print("the project changed since the preview was made: run the preview stage again before approving")
        return 1
    st.set_approval(a.gate, "approved", fp, a.note or "")
    print(f"approved '{a.gate}' for {p.name}. Next: python -m reelforge run {a.project} --from render")
    return 0


def cmd_status(a) -> int:
    p = load_project(a.project)
    st = State(p.build / "state.json")
    print(f"{p.name}: {p.W}x{p.H} @ {p.fps} fps, {p.duration:.2f}s, {len(p.cfg['scenes'])} scenes, build {p.build}")
    for s in STAGES:
        d = st.stage(s)
        print(f"  {s:8s} {'done ' + d.get('at', '') if d.get('done') else '-'}")
    for g, v in st.data.get("approvals", {}).items():
        print(f"  checkpoint {g}: {v['status']} ({v['at']})")
    return 0


def cmd_doctor(a) -> int:
    ok = True

    def line(name, good, detail=""):
        nonlocal ok
        ok &= bool(good) or name.startswith("(optional)")
        print(f"  [{'ok' if good else '--'}] {name} {detail}")
    for t in ("node", "ffmpeg", "ffprobe"):
        line(t, which(t), which(t) or "not on PATH")
    from .util import npx as _npx
    try:
        r = _npx(["--version"], cwd=ROOT, check=False, timeout=180)
    except PipelineError as e:
        r = type("R", (), {"returncode": 1, "stdout": str(e)})()
    line("hyperframes (npx)", r.returncode == 0, (r.stdout.strip().splitlines() or ["?"])[-1])
    for mod in ("yaml", "jinja2", "numpy", "librosa", "soundfile"):
        try:
            importlib.import_module(mod)
            line(f"python: {mod}", True)
        except ImportError:
            line(f"python: {mod}", False, "pip install -r requirements.txt")
    try:
        import torch
        line("(optional) torch + CUDA for MusicGen", torch.cuda.is_available(), f"torch {torch.__version__}, cuda={torch.cuda.is_available()}")
        import transformers  # noqa
        line("(optional) transformers", True)
    except ImportError:
        line("(optional) torch/transformers for MusicGen", False, "only needed for music.mode=generate")
    try:
        import yt_dlp  # noqa
        line("(optional) yt-dlp", True)
    except ImportError:
        line("(optional) yt-dlp", False, "only needed for reference URLs")
    if which("nvidia-smi"):
        g = run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], check=False)
        line("(optional) NVIDIA GPU", g.returncode == 0, g.stdout.strip())
    heygen = Path(os.path.expanduser("~/.claude/skills/media-use/audio/scripts/heygen-tts.mjs"))
    line("(optional) HeyGen TTS script", heygen.exists(), str(heygen))
    print("environment OK" if ok else "environment has missing requirements")
    return 0 if ok else 1


def cmd_new(a) -> int:
    d = ROOT / "projects" / a.name
    if (d / "project.yaml").exists():
        print(f"{d / 'project.yaml'} already exists")
        return 1
    tpl = (ROOT / "projects" / "_template" / "project.yaml").read_text(encoding="utf-8")
    w, h, res = {"landscape": (1920, 1080, "landscape"), "portrait": (1080, 1920, "portrait"), "square": (1080, 1080, "square")}[a.aspect]
    tpl = tpl.replace("{{name}}", a.name).replace("{{w}}", str(w)).replace("{{h}}", str(h)).replace("{{res}}", res)
    d.mkdir(parents=True, exist_ok=True)
    (d / "assets").mkdir(exist_ok=True)
    (d / "project.yaml").write_text(tpl, encoding="utf-8")
    print(f"created {d / 'project.yaml'}")
    return 0


def cmd_edit(a) -> int:
    """One command: footage + reference in, edited video out (a job under jobs/)."""
    from pathlib import Path as P
    from . import jobs
    opts = json.loads(a.options) if a.options else {}
    if a.yes:
        opts["auto_approve"] = True
    j = jobs.create([P(f).resolve() for f in a.footage], P(a.reference).resolve(), opts)
    print(f"job {j['id']}  ({jobs.job_dir(j['id'])})")
    j = jobs.process(j["id"])
    return _report_job(j)


def _report_job(j) -> int:
    from . import jobs
    d = jobs.job_dir(j["id"])
    if j["state"] == "awaiting_approval":
        print(f"preview ready: {d / 'build' / 'preview'}")
        print(f"approve with: python -m reelforge job-approve {j['id']}")
        return 0
    if j["state"] == "done":
        print(f"done: {d / j['result']['video']}")
        return 0
    print(f"{j['state']}: {j.get('error')}")
    print(f"log: {d / 'pipeline.log'}")
    return 2


def cmd_job_status(a) -> int:
    from . import jobs
    j = jobs.load(a.id)
    print(json.dumps({**{k: j.get(k) for k in ("id", "state", "stage", "error", "result")}, "progress": jobs.progress(j)}, indent=2))
    return 0


def cmd_job_approve(a) -> int:
    from . import jobs
    jobs.approve(a.id, a.note or "")
    return _report_job(jobs.process(a.id))


def cmd_fetch(a) -> int:
    """Download licence-clear media into assets/broll/<category>/ or assets/sfx/fetched/."""
    from . import fetch
    from .config import ROOT
    if a.kind == "broll":
        out = ROOT / "assets" / "broll" / a.category
        got = fetch.broll(a.query, out, a.count, a.source, a.orientation)
    elif a.kind == "image":
        out = ROOT / "assets" / "broll" / a.category
        got = fetch.image(a.query, out, a.count)
    else:
        out = ROOT / "assets" / "sfx" / "fetched"
        got = fetch.sfx(a.query, out, a.count)
    print(f"fetched {len(got)} {a.kind} file(s) -> {out}")
    for g in got:
        print("  ", Path(g).name)
    if a.kind in ("sfx", "image") and got:
        print("  (Creative-Commons: see the .attrib.txt sidecars for required attribution before publishing)")
    return 0 if got else 1


def cmd_serve(a) -> int:
    import uvicorn
    uvicorn.run("reelforge.server:app", host=a.host, port=a.port, log_level="info", workers=1)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reelforge", description="HireCrew-style motion-graphics video pipeline (HyperFrames)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("project")
    r.add_argument("--from", dest="from_", choices=STAGES)
    r.add_argument("--to", choices=STAGES)
    r.add_argument("--only", choices=STAGES)
    r.add_argument("--force", action="store_true", help="re-run stages even if unchanged")
    r.add_argument("--yes", action="store_true", help="skip the preview approval checkpoint")
    r.add_argument("--verbose", action="store_true")
    r.add_argument("--set", action="append", metavar="KEY=VALUE", help="override a config value, e.g. render.resolution=landscape")
    ap_ = sub.add_parser("approve")
    ap_.add_argument("project")
    ap_.add_argument("gate", nargs="?", default="preview")
    ap_.add_argument("--note")
    s = sub.add_parser("status")
    s.add_argument("project")
    sub.add_parser("doctor")
    n = sub.add_parser("new")
    n.add_argument("name")
    n.add_argument("--aspect", choices=["landscape", "portrait", "square"], default="landscape")
    e = sub.add_parser("edit", help="edit footage in the style of a reference video (creates a job)")
    e.add_argument("--reference", required=True)
    e.add_argument("--footage", required=True, action="append")
    e.add_argument("--options", help='JSON object, e.g. {"aspect": "9:16", "outro_text": "Follow for [more]"}')
    e.add_argument("--yes", action="store_true", help="skip the preview checkpoint")
    js = sub.add_parser("job-status")
    js.add_argument("id")
    ja = sub.add_parser("job-approve")
    ja.add_argument("id")
    ja.add_argument("--note")
    sv = sub.add_parser("serve", help="run the HTTP API")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8088)
    f = sub.add_parser("fetch", help="download licence-clear media into the asset library (Pexels/Pixabay video, Openverse SFX/images)")
    f.add_argument("kind", choices=["broll", "sfx", "image"])
    f.add_argument("query")
    f.add_argument("-n", "--count", type=int, default=5)
    f.add_argument("--category", default="misc", help="broll/image subfolder under assets/broll/")
    f.add_argument("--source", choices=["pexels", "pixabay"], default="pexels", help="B-roll video source")
    f.add_argument("--orientation", choices=["portrait", "landscape", "square"], default="portrait")
    a = ap.parse_args(argv)
    try:
        return {"run": cmd_run, "approve": cmd_approve, "status": cmd_status, "doctor": cmd_doctor, "new": cmd_new,
                "edit": cmd_edit, "job-status": cmd_job_status, "job-approve": cmd_job_approve, "serve": cmd_serve,
                "fetch": cmd_fetch}[a.cmd](a)
    except PipelineError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
