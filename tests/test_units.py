"""Fast unit tests (no rendering): python -m unittest discover -s tests -v"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reelforge.config import load_project  # noqa: E402
from reelforge.stages.compose import caption_phrases, split_words  # noqa: E402
from reelforge.util import PipelineError, num  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class Words(unittest.TestCase):
    def test_accent(self):
        self.assertEqual(split_words("Pay only for [finished work.]"),
                         [("Pay", False), ("only", False), ("for", False), ("finished work.", True)])

    def test_no_accent_and_only_accent(self):
        self.assertEqual(split_words("Order in"), [("Order", False), ("in", False)])
        self.assertEqual(split_words("[plain words.]"), [("plain words.", True)])

    def test_num(self):
        self.assertEqual(num(28.0), "28")
        self.assertEqual(num(1.6), "1.6")


class Config(unittest.TestCase):
    def test_samples_load(self):
        p = load_project(ROOT / "projects" / "reel-talk")
        self.assertEqual(p.cfg["scenes"], "auto")

    def test_overrides(self):
        p = load_project(ROOT / "projects" / "reel-talk", ["render.resolution=portrait-4k", "canvas.fps=60"])
        self.assertEqual(p.cfg["render"]["resolution"], "portrait-4k")
        self.assertEqual(p.fps, 60)

    def test_aspect_mismatch_rejected(self):
        with self.assertRaises(PipelineError):
            load_project(ROOT / "projects" / "reel-talk", ["render.resolution=landscape"])

    def test_bad_scene_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "project.yaml").write_text("name: x\nscenes:\n  - {id: a, type: nope, duration: 1}\n", encoding="utf-8")
            with self.assertRaises(PipelineError):
                load_project(d)


class Captions(unittest.TestCase):
    def test_phrases(self):
        words = [{"text": t, "start": i * 0.3, "end": i * 0.3 + 0.25} for i, t in enumerate("Pay only for finished work. Today.".split())]
        P = caption_phrases(words, 4)
        self.assertEqual([len(p["words"]) for p in P], [4, 1, 1])
        for a, b in zip(P, P[1:]):
            self.assertLess(a["end"], b["start"])



# ---------------------------------------------------------------- auto-edit / transcription / music loop
from reelforge.stages.autoedit import find_list, hook_from, speech_spans, split_span, stat_label  # noqa: E402
from reelforge.stages.transcribe import fix_text, spread_on_speech  # noqa: E402


def W(text, a, b):
    return {"text": text, "start": a, "end": b}


class AutoEdit(unittest.TestCase):
    def test_spans_drop_long_pauses(self):
        ws = [W("a", 0.0, 0.5), W("b", 0.6, 1.0), W("c", 2.0, 2.4)]
        got = speech_spans(ws, 0.32, 0.05, 10)
        self.assertEqual(len(got), 2)
        for g, e in zip(got, [[0.0, 1.05], [1.95, 2.45]]):
            self.assertAlmostEqual(g[0], e[0])
            self.assertAlmostEqual(g[1], e[1])

    def test_split_respects_shot_lengths(self):
        ws = [W(str(i), i * 0.5, i * 0.5 + 0.4) for i in range(20)]
        shots = split_span(0.0, 10.0, ws, 1.3, 4.2)
        self.assertEqual(shots[0][0], 0.0)
        self.assertEqual(shots[-1][1], 10.0)
        for a, b in shots:
            self.assertLessEqual(b - a, 4.2 + 1e-6)
            self.assertGreaterEqual(b - a, 1.3 - 1e-6)

    def test_list_detection(self):
        self.assertEqual(find_list("Money. You need a good camera, a good mic, good lighting, a good setup, etc. etc."),
                         ["Good camera", "Good mic", "Good lighting", "Good setup"])
        self.assertIsNone(find_list("So it's a very long journey and you do it step by step."))

    def test_hook_and_stat(self):
        lines = hook_from("It's very easy to become a content creator and influencer.")
        self.assertTrue(any("[" in t for t, _ in lines))
        ws = [W("100%", 0, 1), W("true.", 1, 2), W("But", 2, 3)]
        self.assertEqual(stat_label(ws[0], ws), "TRUE")


class Transcribe(unittest.TestCase):
    def test_spread_skips_pauses(self):
        win = [W("x", 0.0, 1.0), W("y", 3.0, 4.0)]          # 2 s pause in the middle
        out = spread_on_speech("one two three four", win)
        self.assertEqual(len(out), 4)
        for w in out:
            self.assertFalse(1.0 + 1e-3 < w["start"] < 3.0 - 1e-3, w)   # no word starts inside the pause

    def test_fixes(self):
        self.assertEqual(fix_text("The difference between land and sky.", [["land and sky", "night and day"]]),
                         "The difference between night and day.")


class MusicLoop(unittest.TestCase):
    def test_loop_reaches_length_on_grid(self):
        import numpy as np
        import soundfile as sf
        from reelforge.stages.music import arrange
        import yaml
        a = yaml.safe_load((ROOT / "config" / "defaults.yaml").read_text(encoding="utf-8"))["music"]["arrange"]
        a.update({"bpm": 120, "drop": 0, "intro_lowpass": False})
        sr = 48000
        t = np.arange(int(8 * sr)) / sr                       # 8 s click track at 120 BPM
        y = np.zeros_like(t)
        for k in range(16):
            i = int(k * 0.5 * sr)
            y[i:i + 400] = 0.8
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "take.wav"
            sf.write(src, np.stack([y, y], 1), sr)
            out = Path(d) / "bed.wav"
            arrange(src, out, 20.0, a, Path(d) / "w")
            z, _ = sf.read(out)
            self.assertAlmostEqual(len(z) / sr, 20.0, places=2)



# ---------------------------------------------------------------- reference style, themes, jobs, security
from reelforge.stages.autoedit import pick_transition  # noqa: E402
from reelforge.stages.compose import esc  # noqa: E402
from reelforge.stages.style import derive_captions, derive_edit, derive_grade, derive_theme  # noqa: E402
from reelforge.theme import DEFAULT_THEME, contrast  # noqa: E402


class StyleAndTheme(unittest.TestCase):
    def test_theme_from_palette_is_readable(self):
        pal = [{"hex": "#0b0d12", "share": 0.5, "L": 5, "chroma": 3}, {"hex": "#fbf7f2", "share": 0.3, "L": 97, "chroma": 4},
               {"hex": "#ff6a1a", "share": 0.02, "L": 62, "chroma": 70}]
        T = derive_theme(pal, {"letter_aspect": 0.38, "stroke_fill": 0.35, "upper_ratio": 0.9}, {})
        self.assertEqual(T["accent"], "#ff6a1a")
        self.assertGreaterEqual(contrast(T["on_accent"], T["accent"]), 2.5)
        self.assertGreaterEqual(contrast(T["on_dark"], T["dark1"]), 7)
        self.assertGreaterEqual(contrast(T["on_light"], T["light1"]), 7)
        self.assertIn("League Gothic", T["font_display"])
        self.assertTrue(T["display_upper"])

    def test_default_theme_untouched(self):
        T = derive_theme([], {}, {})
        self.assertEqual(T["accent"], DEFAULT_THEME["accent"])

    def test_edit_follows_pacing(self):
        fast = derive_edit({"median_shot": 0.9, "cuts_per_min": 60}, {"weights": {"flash": 0.5}}, {"energy": 0.6})
        slow = derive_edit({"median_shot": 4.0, "cuts_per_min": 10}, {"weights": {}}, {"energy": 0.1})
        self.assertLess(fast["max_shot"], slow["max_shot"])
        self.assertEqual(fast["punch_every"], 3)

    def test_grade_is_bounded(self):
        ref = {"luma": 90, "contrast": 60, "saturation": 250, "warmth": 40, "flat_ratio": 0.0, "vignette": 0.9,
               "shadow_tint": {"hue": 200.0, "amount": 50}, "highlight_tint": {"hue": float("nan"), "amount": 50}}
        foot = {"luma": 20, "contrast": 10, "saturation": 10, "warmth": -20}
        g = derive_grade(ref, foot)
        for v in g["adjust"].values():
            self.assertLessEqual(abs(v), 0.35)
        self.assertNotIn("highlights", g.get("wheels", {}))       # NaN hue skipped
        self.assertLessEqual(g["details"]["vignette"], 0.3)

    def test_caption_style_choice(self):
        self.assertEqual(derive_captions({"has_text": True, "captions": True, "words_per_line": 1}, 0.5)["style"], "stroke")
        self.assertEqual(derive_captions({"has_text": True, "captions": True, "words_per_line": 3, "highlight_color": "#ff0000"}, 0.5)["style"], "highlight")

    def test_transition_mix(self):
        self.assertEqual(pick_transition({"transition_weights": {"flash": 0.0, "zoom-blur": 0.0, "punch": 0.0}}, 5, True), "punch")
        self.assertEqual(pick_transition({"transition_weights": {"flash": 0.5}}, 1, True), "flash")
        self.assertEqual(pick_transition({}, 1, False), "cut")
        self.assertEqual(pick_transition({}, 4, False, into_graphic=True), "zoom-blur")


class Security(unittest.TestCase):
    def test_text_is_escaped_paths_are_not(self):
        out = esc({"type": "kinetic", "video": "a&b", "lines": [{"text": "<img src=x onerror=alert(1)>"}]})
        self.assertNotIn("<img", out["lines"][0]["text"])
        self.assertEqual(out["video"], "a&b")

    def test_job_inputs(self):
        from reelforge import jobs
        with self.assertRaises(PipelineError):
            jobs.job_dir("../../windows")
        with self.assertRaises(PipelineError):
            jobs._check_options({**jobs.DEFAULT_OPTIONS, "music": "steal-reference-audio"})
        with self.assertRaises(PipelineError):
            jobs._check_options({**jobs.DEFAULT_OPTIONS, "transcript_fixes": [["(", "x"]]})
        jobs._check_options(dict(jobs.DEFAULT_OPTIONS))


if __name__ == "__main__":
    unittest.main()
