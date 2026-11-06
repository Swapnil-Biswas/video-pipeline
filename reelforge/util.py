"""Shared helpers: logging, running external tools, JSON state, small math."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger("reelforge")


class PipelineError(RuntimeError):
    """A stage failed in a way the user must fix (bad config, tool missing, tool error)."""


def setup_logging(log_dir: Path, verbose: bool = False) -> Path:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"run_{time.strftime('%Y%m%d_%H%M%S')}.log"
    log.handlers.clear()
    log.setLevel(logging.DEBUG)
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.DEBUG if verbose else logging.INFO)
    sh.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(fh)
    log.addHandler(sh)
    return path


def which(name: str) -> str | None:
    return shutil.which(name)


def run(cmd: list[str] | str, cwd: Path | None = None, check: bool = True, env: dict | None = None,
        timeout: float | None = None, quiet: bool = False) -> subprocess.CompletedProcess:
    """Run a command, log it and its output; raise PipelineError on failure."""
    shown = cmd if isinstance(cmd, str) else " ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd)
    log.debug("$ %s%s", shown, f"   (cwd={cwd})" if cwd else "")
    e = os.environ.copy()
    e.setdefault("PYTHONIOENCODING", "utf-8")
    if env:
        e.update(env)
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, shell=isinstance(cmd, str))
    except FileNotFoundError as ex:
        raise PipelineError(f"tool not found: {shown.split()[0]} ({ex})") from ex
    except subprocess.TimeoutExpired as ex:
        raise PipelineError(f"timed out after {timeout}s: {shown}") from ex
    out = (p.stdout or "") + (p.stderr or "")
    if out.strip():
        log.debug(out.rstrip()[-20000:])
    log.debug("exit %s in %.1fs", p.returncode, time.time() - t0)
    if check and p.returncode != 0:
        tail = "\n".join(out.strip().splitlines()[-25:])
        raise PipelineError(f"command failed (exit {p.returncode}): {shown}\n{tail}")
    return p


def _ver(path: Path) -> tuple:
    m = re.search(r"v?(\d+)\.(\d+)\.(\d+)", str(path))
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


_NODE: tuple | None = None


def node_install() -> tuple[Path, Path]:
    """(node executable, npx-cli.js) of a real Node >= 22 install.

    Version-manager shims (nvm for Windows here) can refuse to run outside the shell that selected a version,
    so the real binary is resolved once: $REELFORGE_NODE, then `node -p process.execPath`, then known install dirs."""
    global _NODE
    if _NODE:
        return _NODE
    cands = []
    if os.environ.get("REELFORGE_NODE"):
        cands.append(Path(os.environ["REELFORGE_NODE"]))
    try:
        r = subprocess.run(["node", "-p", "process.execPath"], capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            cands.append(Path(r.stdout.strip()))
    except (OSError, subprocess.TimeoutExpired):
        pass
    roots = [Path(os.environ.get("LOCALAPPDATA", "")) / "Author Software" / "nvm" / "installs",
             Path(os.environ.get("NVM_HOME", "/nonexistent")), Path(os.environ.get("APPDATA", "")) / "nvm",
             Path.home() / ".nvm" / "versions" / "node", Path("C:/Program Files/nodejs").parent]
    found = []
    for r in roots:
        if r.exists():
            found += [x for x in r.glob("v*/node.exe")] + [x for x in r.glob("v*/bin/node")]
    cands += sorted(found, key=_ver, reverse=True)
    if Path("C:/Program Files/nodejs/node.exe").exists():
        cands.append(Path("C:/Program Files/nodejs/node.exe"))
    for node in cands:
        if not node.exists():
            continue
        for cli in (node.parent / "node_modules" / "npm" / "bin" / "npx-cli.js",
                    node.parent.parent / "lib" / "node_modules" / "npm" / "bin" / "npx-cli.js"):
            if cli.exists():
                _NODE = (node, cli)
                log.debug("node: %s  npx: %s", node, cli)
                return _NODE
    raise PipelineError("no usable Node.js 22+ install found (set REELFORGE_NODE to node.exe)")


def npx(args: list[str], cwd: Path, **kw) -> subprocess.CompletedProcess:
    node, cli = node_install()
    env = dict(kw.pop("env", None) or {})
    env["PATH"] = str(node.parent) + os.pathsep + os.environ.get("PATH", "")
    return run([str(node), str(cli), "--yes", "hyperframes", *args], cwd=cwd, env=env, **kw)


def npx_exe() -> str:
    return str(node_install()[0])


def ffprobe_json(path: Path) -> dict:
    p = run(["ffprobe", "-v", "error", "-show_entries",
             "stream=index,codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels:format=duration,size,bit_rate",
             "-of", "json", str(path)])
    return json.loads(p.stdout)


def media_duration(path: Path) -> float:
    return float(ffprobe_json(path)["format"]["duration"])


def sha1(path: Path, extra: str = "") -> str:
    h = hashlib.sha1(extra.encode())
    if path.is_dir():
        for f in sorted(path.rglob("*")):
            if f.is_file():
                h.update(str(f.relative_to(path)).encode())
                h.update(str(f.stat().st_size).encode())
                h.update(str(int(f.stat().st_mtime)).encode())
    elif path.exists():
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()[:16]


def num(x) -> str:
    """28.0 -> '28', 1.6 -> '1.6' (attribute values written like the original project)."""
    return f"{float(x):.4f}".rstrip("0").rstrip(".")


def read_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, data) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    return path


def copy_into(src: Path, dst: Path) -> None:
    """Copy a file or a directory tree (merging)."""
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


class State:
    """Per-project stage state (done / fingerprint / outputs) and approval gates in build/<name>/state.json."""

    def __init__(self, path: Path):
        self.path = path
        self.data = read_json(path, {"stages": {}, "approvals": {}})

    def save(self):
        write_json(self.path, self.data)

    def stage(self, name: str) -> dict:
        return self.data["stages"].get(name, {})

    def mark(self, name: str, fingerprint: str, **info):
        self.data["stages"][name] = {"done": True, "fingerprint": fingerprint, "at": time.strftime("%Y-%m-%d %H:%M:%S"), **info}
        self.save()

    def invalidate_from(self, names: list[str]):
        for n in names:
            self.data["stages"].pop(n, None)
        self.save()

    def approval(self, gate: str) -> dict:
        return self.data["approvals"].get(gate, {})

    def set_approval(self, gate: str, status: str, fingerprint: str, note: str = ""):
        self.data["approvals"][gate] = {"status": status, "fingerprint": fingerprint, "note": note,
                                        "at": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.save()
