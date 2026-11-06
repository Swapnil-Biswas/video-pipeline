"""Stage 7 · check: HyperFrames lint + layout + audio checks. Errors stop the pipeline; warnings are logged."""
from __future__ import annotations

import re

from ..util import PipelineError, log, npx, write_json


def run_stage(p) -> dict:
    r = npx(["check"], cwd=p.hf, check=False, timeout=600)
    out = r.stdout + r.stderr
    (p.build / "check").mkdir(parents=True, exist_ok=True)
    (p.build / "check" / "check.txt").write_text(out, encoding="utf-8")
    errors = sum(int(x) for x in re.findall(r"(\d+) error\(s\)", out))
    warnings = sum(int(x) for x in re.findall(r"(\d+) warning\(s\)", out))
    for line in out.splitlines():
        if re.search(r"✗|error:", line) and "0 error" not in line:
            log.info("  %s", line.strip()[:220])
    write_json(p.build / "check" / "check.json", {"errors": errors, "warnings": warnings, "exit": r.returncode})
    log.info("  %d error(s), %d warning(s) - full report build/%s/check/check.txt", errors, warnings, p.name)
    if errors or ("Check passed" not in out and r.returncode != 0):
        raise PipelineError(f"hyperframes check failed ({errors} errors); see {p.build / 'check' / 'check.txt'}")
    return {"errors": errors, "warnings": warnings}
