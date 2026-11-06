"""HTTP API for HireCrew: upload footage + a reference video, get the footage edited in the reference's style.

    python -m reelforge serve --host 0.0.0.0 --port 8088

Auth: every /v1 call needs header  X-API-Key: $REELFORGE_API_KEY  (set REELFORGE_DEV=1 to run without a key locally).

  POST   /v1/jobs                  multipart: reference=<file>, footage=<file> (repeatable), options=<JSON string>
  GET    /v1/jobs/{id}             state, stage, progress, queue position, preview images, result, error
  GET    /v1/jobs/{id}/files/{p}   a preview image, the thumbnail or the final video of that job
  POST   /v1/jobs/{id}/approve     approve the preview checkpoint -> render
  POST   /v1/jobs/{id}/cancel
  GET    /v1/health                tools + GPU + queue (no key needed)
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from . import jobs
from .util import PipelineError

app = FastAPI(title="reelforge", version="1.1.0", docs_url="/docs")
worker = jobs.Worker()
CHUNK = 1 << 20


def require_key(x_api_key: str | None = Header(default=None)):
    want = os.environ.get("REELFORGE_API_KEY")
    if not want:
        if os.environ.get("REELFORGE_DEV") == "1":
            return
        raise HTTPException(503, "server misconfigured: REELFORGE_API_KEY is not set")
    if not x_api_key or not secrets.compare_digest(x_api_key, want):
        raise HTTPException(401, "missing or wrong X-API-Key")


@app.on_event("startup")
def _start():
    worker.start()


@app.exception_handler(PipelineError)
def _pipeline_error(_: Request, e: PipelineError):
    return JSONResponse(status_code=400, content={"error": str(e)})


async def _save_upload(up: UploadFile, folder: Path, name: str) -> Path:
    ext = Path(up.filename or "").suffix.lower()
    if ext not in jobs.VIDEO_EXT:
        raise PipelineError(f"{name}: unsupported file type {ext or '(none)'}")
    dst = folder / f"{name}{ext}"
    limit = jobs.LIMITS["max_upload_mb"] * 2**20
    n = 0
    with open(dst, "wb") as f:
        while True:
            chunk = await up.read(CHUNK)
            if not chunk:
                break
            n += len(chunk)
            if n > limit:
                raise PipelineError(f"{name}: larger than {jobs.LIMITS['max_upload_mb']:.0f} MB")
            f.write(chunk)
    return dst


def _public(j: dict) -> dict:
    out = {k: j.get(k) for k in ("id", "state", "stage", "created_at", "updated_at", "options", "error", "result")}
    out["inputs"] = j.get("inputs")
    out["progress"] = jobs.progress(j)
    out["queue_position"] = worker.position(j["id"])
    out["preview"] = [f"/v1/jobs/{j['id']}/files/{p}" for p in j.get("preview", [])]
    if j.get("result"):
        out["result"] = {**j["result"], "video_url": f"/v1/jobs/{j['id']}/files/{j['result']['video']}",
                         "thumbnail_url": f"/v1/jobs/{j['id']}/files/{j['result']['thumbnail']}" if j["result"].get("thumbnail") else None}
    return out


@app.post("/v1/jobs", dependencies=[Depends(require_key)], status_code=201)
async def create_job(reference: UploadFile = File(...), footage: list[UploadFile] = File(...), options: str = Form("{}")):
    try:
        opts = json.loads(options or "{}")
        if not isinstance(opts, dict):
            raise ValueError
    except ValueError:
        raise PipelineError("options must be a JSON object")
    unknown = set(opts) - set(jobs.DEFAULT_OPTIONS)
    if unknown:
        raise PipelineError(f"unknown options: {sorted(unknown)}")
    tmp = Path(tempfile.mkdtemp(prefix="reelforge-up-"))
    try:
        ref = await _save_upload(reference, tmp, "reference")
        fs = [await _save_upload(f, tmp, f"footage{i + 1}") for i, f in enumerate(footage)]
        j = jobs.create(fs, ref, opts, move=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    worker.submit(j["id"])
    return _public(j)


@app.get("/v1/jobs/{job_id}", dependencies=[Depends(require_key)])
def get_job(job_id: str):
    return _public(jobs.load(job_id))


@app.get("/v1/jobs/{job_id}/files/{path:path}", dependencies=[Depends(require_key)])
def get_file(job_id: str, path: str):
    d = jobs.job_dir(job_id).resolve()
    f = (d / path).resolve()
    allowed = [d / "build" / "preview", d / "build" / "final", d / "build" / "audit"]
    if not any(str(f).startswith(str(a.resolve()) + os.sep) for a in allowed) or not f.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(f)


@app.post("/v1/jobs/{job_id}/approve", dependencies=[Depends(require_key)])
def approve_job(job_id: str):
    j = jobs.approve(job_id)
    worker.submit(job_id)
    return _public(j)


@app.post("/v1/jobs/{job_id}/cancel", dependencies=[Depends(require_key)])
def cancel_job(job_id: str):
    return _public(jobs.cancel(job_id))


@app.get("/v1/health")
def health():
    import shutil as sh
    gpu = None
    try:
        import torch
        gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    except Exception:
        pass
    return {"ok": all(sh.which(t) for t in ("ffmpeg", "ffprobe")), "gpu": gpu, "queue": len(worker.q),
            "limits": jobs.LIMITS, "auth": bool(os.environ.get("REELFORGE_API_KEY"))}
