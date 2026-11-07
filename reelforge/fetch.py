"""Fetch free, licence-clear media into the asset library.

  B-roll video : Pexels / Pixabay          (free API key: PEXELS_API_KEY / PIXABAY_API_KEY)
  SFX & music  : Openverse  /v1/audio/      (Creative-Commons; anonymous, no key)
  CC images    : Openverse  /v1/images/     (Creative-Commons; anonymous, no key)

Everything is filtered to commercial-use licences where the source supports it, and every
Openverse download gets a <file>.attrib.txt sidecar with the required attribution — check it
before publishing. Pexels and Pixabay are licence-free (no attribution needed)."""
from __future__ import annotations

import os
import re
from pathlib import Path

from .util import PipelineError, log

TIMEOUT = 40.0
UA = "reelforge/1.0 (video pipeline; contact: configured by the user)"


def _slug(s: str, n: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (s or "clip").strip().lower()).strip("-")
    return (s or "clip")[:n]


def _client():
    try:
        import httpx
    except ImportError as e:                                    # pragma: no cover
        raise PipelineError("fetch needs httpx (pip install -r requirements.txt)") from e
    return httpx.Client(timeout=TIMEOUT, headers={"User-Agent": UA}, follow_redirects=True)


def _download(client, url: str, dst: Path) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        with client.stream("GET", url) as r:
            if r.status_code != 200:
                log.warning("  skip (%s): %s", r.status_code, url[:80])
                return False
            with open(dst, "wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
    except Exception as e:                                      # network / write errors are per-item, not fatal
        log.warning("  skip (%s): %s", type(e).__name__, url[:80])
        return False
    if dst.exists() and dst.stat().st_size > 2048:
        return True
    dst.unlink(missing_ok=True)
    return False


# ---------------------------------------------------------------- B-roll video
def _pexels_video(client, query: str, out: Path, n: int, orientation: str) -> list[str]:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        raise PipelineError("set PEXELS_API_KEY (free at pexels.com/api) to fetch B-roll from Pexels")
    r = client.get("https://api.pexels.com/videos/search", headers={"Authorization": key},
                   params={"query": query, "per_page": n, "orientation": orientation, "size": "large"})
    if r.status_code != 200:
        raise PipelineError(f"Pexels API {r.status_code}: {r.text[:140]}")
    got = []
    for v in r.json().get("videos", [])[:n]:
        files = sorted((f for f in v.get("video_files", []) if f.get("width")), key=lambda f: -f["width"])
        hd = next((f for f in files if f["width"] >= 1080), files[0] if files else None)
        if not hd:
            continue
        dst = out / f"{_slug(query)}-pexels-{v['id']}.mp4"
        if dst.exists() or _download(client, hd["link"], dst):
            got.append(str(dst))
    return got


def _pixabay_video(client, query: str, out: Path, n: int) -> list[str]:
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        raise PipelineError("set PIXABAY_API_KEY (free at pixabay.com/api/docs) to fetch B-roll from Pixabay")
    r = client.get("https://pixabay.com/api/videos/",
                   params={"key": key, "q": query, "per_page": max(3, n), "safesearch": "true"})
    if r.status_code != 200:
        raise PipelineError(f"Pixabay API {r.status_code}: {r.text[:140]}")
    got = []
    for v in r.json().get("hits", [])[:n]:
        streams = v.get("videos", {})
        pick = streams.get("large") or streams.get("medium") or next(iter(streams.values()), None)
        if not pick or not pick.get("url"):
            continue
        dst = out / f"{_slug(query)}-pixabay-{v['id']}.mp4"
        if dst.exists() or _download(client, pick["url"], dst):
            got.append(str(dst))
    return got


def broll(query: str, out: Path, n: int, source: str, orientation: str) -> list[str]:
    with _client() as c:
        return _pexels_video(c, query, out, n, orientation) if source == "pexels" else _pixabay_video(c, query, out, n)


# ---------------------------------------------------------------- Openverse (CC)
def _openverse(kind: str, query: str, out: Path, n: int, exts: tuple[str, ...]) -> list[str]:
    token = os.environ.get("OPENVERSE_TOKEN")                  # optional; raises rate limits
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    got = []
    with _client() as c:
        r = c.get(f"https://api.openverse.org/v1/{kind}/", headers=headers,
                  params={"q": query, "page_size": min(n, 20), "license_type": "commercial", "mature": "false"})
        if r.status_code != 200:
            raise PipelineError(f"Openverse API {r.status_code}: {r.text[:140]}")
        for it in r.json().get("results", [])[:n]:
            url = it.get("url")
            if not url:
                continue
            ext = next((e for e in exts if url.lower().split("?")[0].endswith(e)), it.get("filetype") or exts[0].lstrip("."))
            ext = ext if ext.startswith(".") else "." + ext
            dst = out / f"{_slug(it.get('title') or query)}-ov-{it.get('id', '')[:8]}{ext}"
            if dst.exists() or _download(c, url, dst):
                got.append(str(dst))
                attrib = it.get("attribution") or f"{it.get('title', '')} by {it.get('creator', '')} — {it.get('license', '')} {it.get('license_version', '')} ({it.get('license_url') or it.get('foreign_landing_url', '')})"
                (dst.with_suffix(dst.suffix + ".attrib.txt")).write_text(attrib.strip() + "\n", encoding="utf-8")
    return got


def sfx(query: str, out: Path, n: int) -> list[str]:
    return _openverse("audio", query, out, n, (".mp3", ".wav", ".ogg", ".flac"))


def image(query: str, out: Path, n: int) -> list[str]:
    return _openverse("images", query, out, n, (".jpg", ".jpeg", ".png", ".webp"))
