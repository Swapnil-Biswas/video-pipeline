"""Stage 8 · preview: stills for the human approval checkpoint.

Runs `hyperframes snapshot --review` (each scene at start+0.3 s and middle, a 5-frame strip around every cut,
phone-width beats) plus any extra times, then marks the 'preview' gate as pending for this exact build."""
from __future__ import annotations

import shutil

from ..util import log, npx, sha1, write_json


def run_stage(p) -> dict:
    out = p.build / "preview"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)   # a locked folder on Windows can survive rmtree
    if p.cfg["preview"].get("seams", True):
        npx(["snapshot", "--review", "-o", str(out / "review")], cwd=p.hf, timeout=1800)
    extra = p.cfg["preview"].get("extra_at") or []
    if extra:
        npx(["snapshot", "--at", ",".join(str(x) for x in extra), "--no-end", "-o", str(out / "extra")], cwd=p.hf, timeout=1800)
    sheets = sorted(str(x) for x in out.rglob("*.jpg"))
    (out / "QA_PROMPT.md").write_text(p.prompts["review"]["qa_review"], encoding="utf-8")
    fp = sha1(p.hf / "compositions") + sha1(p.hf / "index.html")
    st = p.state
    if st.approval("preview").get("fingerprint") != fp or st.approval("preview").get("status") != "approved":
        st.set_approval("preview", "pending", fp)
    write_json(out / "preview.json", {"sheets": sheets, "fingerprint": fp})
    log.info("  %d review images in %s", len(sheets), out)
    log.info("  CHECKPOINT: look at the sheets (QA prompt in preview/QA_PROMPT.md), then run:")
    log.info("      python -m reelforge approve %s preview", p.dir)
    return {"sheets": len(sheets), "fingerprint": fp}
