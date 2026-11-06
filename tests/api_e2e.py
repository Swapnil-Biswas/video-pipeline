"""End-to-end API test (real GPU render): python tests/api_e2e.py <reference.mp4> <footage.mp4> [options-json]

Starts the server on a free port with an API key, checks auth, uploads, waits for the preview checkpoint,
approves, waits for the render, downloads the result and verifies it with ffprobe."""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    ref, foot = Path(sys.argv[1]), Path(sys.argv[2])
    opts = sys.argv[3] if len(sys.argv) > 3 else "{}"
    key = "test-" + os.urandom(8).hex()
    port = free_port()
    env = {**os.environ, "REELFORGE_API_KEY": key, "PYTHONIOENCODING": "utf-8"}
    log = open(ROOT / "build" / "api_e2e_server.log", "w", encoding="utf-8")
    srv = subprocess.Popen([sys.executable, "-m", "reelforge", "serve", "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                if httpx.get(base + "/v1/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        print("health:", httpx.get(base + "/v1/health").json())
        assert httpx.get(base + "/v1/jobs/20260101-000000-deadbeef").status_code == 401, "auth must be required"
        assert httpx.get(base + "/v1/jobs/20260101-000000-deadbeef", headers={"X-API-Key": "wrong"}).status_code == 401
        H = {"X-API-Key": key}
        bad = httpx.post(base + "/v1/jobs", headers=H, files={"reference": ("r.txt", b"nope"), "footage": ("f.mp4", b"x")}, data={"options": "{}"})
        assert bad.status_code == 400, bad.text
        print("rejects bad upload:", bad.json())
        with open(ref, "rb") as r, open(foot, "rb") as f:
            res = httpx.post(base + "/v1/jobs", headers=H, timeout=600,
                             files=[("reference", (ref.name, r, "video/mp4")), ("footage", (foot.name, f, "video/mp4"))], data={"options": opts})
        assert res.status_code == 201, res.text
        job = res.json()
        jid = job["id"]
        print("created job", jid, job["state"])
        t0 = time.time()
        last = None
        while True:
            j = httpx.get(f"{base}/v1/jobs/{jid}", headers=H).json()
            if (j["state"], j["progress"]["percent"]) != last:
                print(f"  {time.time() - t0:6.0f}s  {j['state']:<18} {j['progress']['percent']:3d}%  {j['progress']['stages_done'][-1:] }")
                last = (j["state"], j["progress"]["percent"])
            if j["state"] == "awaiting_approval":
                print("  preview images:", len(j["preview"]))
                img = httpx.get(base + j["preview"][0], headers=H)
                assert img.status_code == 200 and len(img.content) > 1000
                assert httpx.get(f"{base}/v1/jobs/{jid}/files/../job.json", headers=H).status_code == 404, "path traversal must be blocked"
                print("  approving")
                assert httpx.post(f"{base}/v1/jobs/{jid}/approve", headers=H).status_code == 200
            elif j["state"] in ("done", "failed", "cancelled"):
                break
            time.sleep(3)
        print("final state:", j["state"], j.get("error"))
        assert j["state"] == "done", j
        vid = httpx.get(base + j["result"]["video_url"], headers=H, timeout=600)
        out = ROOT / "build" / f"api_e2e_{jid}.mp4"
        out.write_bytes(vid.content)
        probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration", "-of", "json", str(out)],
                                          capture_output=True, text=True).stdout)
        print("downloaded", out, f"{len(vid.content) / 2**20:.1f} MB", probe["format"]["duration"], "s",
              [(s["codec_type"], s.get("width"), s.get("height")) for s in probe["streams"]])
        print("audit:", j["result"]["audit"])
        print(f"API E2E PASSED in {time.time() - t0:.0f}s")
    finally:
        srv.terminate()
        log.close()


if __name__ == "__main__":
    main()
