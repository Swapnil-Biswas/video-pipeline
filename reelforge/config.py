"""Load config/defaults.yaml + projects/<name>/project.yaml into one validated Project."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .util import PipelineError

ROOT = Path(__file__).resolve().parent.parent          # video-pipeline/
SCENE_TYPES = {"file", "kinetic", "footage", "list"}
RES_PRESETS = {  # HyperFrames --resolution presets -> (w, h)
    "landscape": (1920, 1080), "portrait": (1080, 1920), "landscape-4k": (3840, 2160),
    "portrait-4k": (2160, 3840), "square": (1080, 1080), "square-4k": (2160, 2160),
}


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


@dataclass
class Project:
    cfg: dict
    dir: Path                       # projects/<name>
    root: Path = ROOT
    prompts: dict = field(default_factory=dict)
    layers: dict = field(default_factory=dict)    # defaults / user / sets, kept to rebuild cfg after the style stage

    def reload(self) -> None:
        """Re-layer config: defaults < reference-derived style < project.yaml < --set."""
        derived = style_overrides(self)
        cfg = deep_merge(deep_merge(self.layers["defaults"], derived), self.layers["user"])
        self.cfg = apply_overrides(cfg, self.layers["sets"])

    @property
    def name(self) -> str:
        return self.cfg["name"]

    @property
    def build(self) -> Path:
        b = Path(self.cfg.get("build_dir") or (self.root / "build" / self.name))
        return b if b.is_absolute() else (self.dir / b).resolve()

    @property
    def hf(self) -> Path:          # generated HyperFrames project
        return self.build / "hf"

    @property
    def W(self) -> int:
        return int(self.cfg["canvas"]["width"])

    @property
    def H(self) -> int:
        return int(self.cfg["canvas"]["height"])

    @property
    def fps(self) -> int:
        return int(self.cfg["canvas"]["fps"])

    def path(self, p: str | Path) -> Path:
        """Resolve a config path: absolute, else relative to the project dir, else to the pipeline root."""
        p = Path(p)
        if p.is_absolute():
            return p
        cand = (self.dir / p).resolve()
        if cand.exists():
            return cand
        alt = (self.root / p).resolve()
        return alt if alt.exists() else cand

    @property
    def auto(self) -> bool:
        return self.cfg.get("scenes") == "auto"

    def plan(self) -> dict:
        import json
        f = self.build / "autoedit" / "plan.json"
        if not f.exists():
            raise PipelineError("scenes: auto - run the transcribe and autoedit stages first")
        return json.loads(f.read_text(encoding="utf-8"))

    def scenes(self) -> list[dict]:
        """Scenes with resolved absolute start times (cumulative unless 'start' is given)."""
        t, out = 0.0, []
        for s in (self.plan()["scenes"] if self.auto else self.cfg["scenes"]):
            s = dict(s)
            s["start"] = round(float(s.get("start", t)), 4)
            s["duration"] = round(float(s["duration"]), 4)
            t = s["start"] + s["duration"]
            out.append(s)
        return out

    @property
    def duration(self) -> float:
        d = self.cfg.get("duration")
        if d:
            return float(d)
        if self.auto and not (self.build / "autoedit" / "plan.json").exists():
            return 0.0
        return max(s["start"] + s["duration"] for s in self.scenes())


def apply_overrides(cfg: dict, sets: list[str] | None) -> dict:
    """--set render.resolution=landscape --set canvas.fps=30  (values parsed as YAML)."""
    for item in sets or []:
        if "=" not in item:
            raise PipelineError(f"--set expects key=value, got {item!r}")
        key, val = item.split("=", 1)
        node = cfg
        parts = key.split(".")
        for k in parts[:-1]:
            node = node.setdefault(k, {})
        node[parts[-1]] = yaml.safe_load(val)
    return cfg


def load_project(project_file: str | Path, sets: list[str] | None = None) -> Project:
    pf = Path(project_file).resolve()
    if pf.is_dir():
        pf = pf / "project.yaml"
    if not pf.exists():
        raise PipelineError(f"project file not found: {pf}")
    defaults = yaml.safe_load((ROOT / "config" / "defaults.yaml").read_text(encoding="utf-8"))
    try:
        user = yaml.safe_load(pf.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise PipelineError(f"{pf.name} is not valid YAML: {e}") from e
    if not isinstance(user, dict):
        raise PipelineError(f"{pf.name} must be a YAML mapping")
    cfg = deep_merge(defaults, user)
    cfg = apply_overrides(cfg, sets)
    prompts = yaml.safe_load((ROOT / "config" / "prompts.yaml").read_text(encoding="utf-8"))
    proj = Project(cfg=cfg, dir=pf.parent, prompts=prompts, layers={"defaults": defaults, "user": user, "sets": sets or []})
    proj.reload()
    validate(proj)
    return proj


def style_overrides(p: "Project") -> dict:
    """Settings learned from the reference (build/<name>/style/style.json), shaped like project.yaml."""
    if not p.cfg.get("style", {}).get("from_reference"):
        return {}
    f = p.build / "style" / "style.json"
    if not f.exists():
        return {}
    import json
    s = json.loads(f.read_text(encoding="utf-8"))
    e, c, m = s.get("edit", {}), s.get("captions", {}), s.get("music", {})
    out = {"theme": s.get("theme", {}),
           "autoedit": {k: e[k] for k in ("min_shot", "max_shot", "punch", "punch_hi", "punch_every", "keyword_spacing", "transition_weights") if k in e},
           "captions": {k: c[k] for k in ("style", "reel_y", "upper", "box", "max_words", "reel_size") if k in c}}
    if s.get("grade"):
        out["grade"] = s["grade"]
    if m.get("bpm"):
        out["music"] = {"arrange": {"bpm": m["bpm"]}, "generate": {"prompts": [m["prompt"]]}}
    return out


def validate(p: Project) -> None:
    c, errs = p.cfg, []
    if not c.get("name"):
        errs.append("name is required")
    for k in ("width", "height", "fps"):
        if not c.get("canvas", {}).get(k):
            errs.append(f"canvas.{k} is required")
    if not c.get("scenes"):
        errs.append("scenes: at least one scene is required (or scenes: auto with aroll.video)")
    if c.get("scenes") == "auto" and not (c.get("aroll") or {}).get("video") and not c.get("footage"):
        errs.append("scenes: auto needs footage (and aroll.video for talking-head editing)")
    ids = set()
    for i, s in enumerate(c.get("scenes") if isinstance(c.get("scenes"), list) else []):
        where = f"scenes[{i}]"
        if not s.get("id"):
            errs.append(f"{where}.id is required")
        elif s["id"] in ids:
            errs.append(f"{where}.id '{s['id']}' is duplicated")
        ids.add(s.get("id"))
        if s.get("type") not in SCENE_TYPES:
            errs.append(f"{where}.type must be one of {sorted(SCENE_TYPES)}")
        if not s.get("duration") or float(s["duration"]) <= 0:
            errs.append(f"{where}.duration must be > 0")
        if s.get("type") == "file" and not s.get("src"):
            errs.append(f"{where}.src is required for type 'file'")
        if s.get("type") == "footage" and not s.get("video"):
            errs.append(f"{where}.video is required for type 'footage'")
    r = c.get("render", {})
    res = r.get("resolution")
    if res not in RES_PRESETS:
        errs.append(f"render.resolution must be one of {sorted(RES_PRESETS)}")
    elif c.get("canvas"):
        rw, rh = RES_PRESETS[res]
        cw, ch = c["canvas"].get("width", 1), c["canvas"].get("height", 1)
        if abs(rw / rh - cw / ch) > 0.01:
            errs.append(f"render.resolution {res} ({rw}x{rh}) does not match the canvas aspect {cw}x{ch}")
    if c.get("music", {}).get("mode") not in ("none", "file", "take", "generate"):
        errs.append("music.mode must be none | file | take | generate")
    if c.get("voice", {}).get("mode") not in ("none", "file", "heygen"):
        errs.append("voice.mode must be none | file | heygen")
    if errs:
        raise PipelineError("invalid project config:\n  - " + "\n  - ".join(errs))
