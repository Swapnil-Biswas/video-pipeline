"""Stage 9 · render: HyperFrames render on the GPU.

Original command: npx hyperframes render --quality delivery --resolution landscape-4k --fps 60 --gpu -o renders/x_raw.mp4 --quiet
On Windows hybrid-GPU laptops the headless Chrome is pinned to the high-performance GPU first
(HKCU\\Software\\Microsoft\\DirectX\\UserGpuPreferences -> GpuPreference=2), as in the original session."""
from __future__ import annotations

import os
import re
from pathlib import Path

from ..util import PipelineError, log, npx, run, sha1


def ensure_gpu_preference() -> list[str]:
    if os.name != "nt":
        return []
    root = Path.home() / ".cache" / "hyperframes" / "chrome"
    exes = [str(x) for x in root.rglob("chrome-headless-shell.exe")] if root.exists() else []
    done = []
    for exe in exes:
        q = run(["reg", "query", r"HKCU\Software\Microsoft\DirectX\UserGpuPreferences", "/v", exe], check=False)
        if "GpuPreference=2;" in q.stdout:
            done.append(exe)
            continue
        run(["reg", "add", r"HKCU\Software\Microsoft\DirectX\UserGpuPreferences", "/v", exe, "/t", "REG_SZ", "/d", "GpuPreference=2;", "/f"])
        log.info("  set GpuPreference=2 for %s", exe)
        done.append(exe)
    if not exes:
        log.info("  headless Chrome not downloaded yet; GPU preference will be set on the next run")
    return done


def run_stage(p, assume_yes: bool = False) -> dict:
    r = p.cfg["render"]
    fp = sha1(p.hf / "compositions") + sha1(p.hf / "index.html")
    if p.cfg["preview"].get("require_approval", True) and not assume_yes:
        a = p.state.approval("preview")
        if a.get("status") != "approved" or a.get("fingerprint") != fp:
            raise PipelineError("render needs the preview approved for this exact build: run the preview stage, review it, then\n"
                                f"    python -m reelforge approve {p.dir} preview\n(or pass --yes to skip the checkpoint)")
    if r.get("set_gpu_preference", True):
        ensure_gpu_preference()
    out = p.build / "render"
    out.mkdir(parents=True, exist_ok=True)
    raw = out / "raw.mp4"
    args = ["render", "--quality", r["quality"], "--resolution", r["resolution"], "--fps", str(p.fps), "-o", str(raw)]
    if r.get("gpu"):
        args.append("--gpu")
    if r.get("workers") and r["workers"] != "auto":
        args += ["--workers", str(r["workers"])]
    log.info("  rendering %s @ %d fps (%s)...", r["resolution"], p.fps, "GPU encode" if r.get("gpu") else "CPU encode")
    res = npx(args, cwd=p.hf, timeout=float(r.get("timeout", 7200)))
    text = res.stdout + res.stderr
    (out / "render.log").write_text(text, encoding="utf-8")
    gpu = re.search(r'renderer="([^"]+)"', text)
    if gpu:
        log.info("  capture GPU: %s", gpu.group(1))
    if "Audio lowered" in text:
        log.info("  note: HyperFrames lowered the mix to its delivery ceiling; the master stage restores loudness")
    if not raw.exists() or raw.stat().st_size < 10000:
        raise PipelineError(f"render produced no file; see {out / 'render.log'}")
    return {"raw": str(raw), "capture_gpu": gpu.group(1) if gpu else None}
