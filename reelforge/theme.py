"""Themes: every colour, font and caption look the templates use, as one dict.

DEFAULT_THEME is a neutral social-video look: white captions, black outline, one strong accent.
A reference video's style profile produces a different theme (stages/style.py -> derive_theme)."""
from __future__ import annotations

import colorsys

# fonts HyperFrames bundles (resolve by name, no font files needed) + the brand font shipped in assets/fonts
BUNDLED_FONTS = ["Inter", "Montserrat", "Outfit", "Nunito", "Oswald", "League Gothic", "Archivo Black", "Space Mono",
                 "IBM Plex Mono", "JetBrains Mono", "EB Garamond", "Playfair Display", "Source Code Pro", "Roboto",
                 "Open Sans", "Lato", "Poppins"]

DEFAULT_THEME = {
    "name": "reel-default",
    "dark0": "#0a0a0b", "dark1": "#111113", "dark2": "#1d1d20",
    "light0": "#fafafa", "light1": "#ececee", "light2": "#e1e1e3",
    "on_dark": "#f2f2f3", "on_dark_2": "#9a9a9e", "on_light": "#151515", "on_light_2": "#6a6a6e",
    "card_dark": "#232326", "card_dark_2": "#1a1a1c", "card_dark_3": "#3a3a3e", "light_row": "#efeff0", "paper": "#f4f4f4",
    "accent": "#ffd60a", "on_accent": "#111111",              # pill on light worlds
    "accent_light": "#ffd60a", "on_accent_light": "#111111",  # pill on dark worlds / footage
    "cap_fg": "#ffffff", "cap_hl_bg": "#ffd60a", "cap_hl_fg": "#111111", "cap_box": "rgba(10,10,11,.42)",
    "cap_shadow": "0 0 2px rgba(0,0,0,.9), 0 3px 0 rgba(0,0,0,.55), 0 8px 26px rgba(0,0,0,.55)",
    "font_body": '"Inter", sans-serif', "font_display": '"Montserrat", sans-serif',
    "display_weight": 800, "display_tracking": "-0.04em", "display_upper": False,
    "radius": 1.0,                                            # corner roundness multiplier
}


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(r, g, b) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(round(v)))) for v in (r, g, b)))


def luminance(h: str) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = hex_to_rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def shade(h: str, l_delta: float = 0.0, s_mul: float = 1.0) -> str:
    """Lightness shift in HLS space (l_delta in 0..1 units)."""
    r, g, b = (c / 255 for c in hex_to_rgb(h))
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    ll = max(0.0, min(1.0, ll + l_delta))
    ss = max(0.0, min(1.0, ss * s_mul))
    r, g, b = colorsys.hls_to_rgb(hh, ll, ss)
    return rgb_to_hex(r * 255, g * 255, b * 255)


def readable_on(bg: str, light="#ffffff", dark="#151515") -> str:
    return light if contrast(bg, light) >= contrast(bg, dark) else dark


def theme_css(T: dict) -> str:
    """CSS that re-skins the shared brand classes (worlds, pills, panel, chips, states, buttons, ticks)."""
    up = "text-transform: uppercase;" if T.get("display_upper") else ""
    r = float(T.get("radius", 1.0))
    return f"""
      /* ---- reelforge theme: {T.get('name', 'custom')} ---- */
      body {{ font-family: {T['font_body']}; color: {T['on_light']}; }}
      .world-dark {{ background: radial-gradient(ellipse 80% 70% at 50% 45%, {T['dark2']} 0%, {T['dark1']} 60%, {T['dark0']} 100%); }}
      .world-light {{ background: radial-gradient(ellipse 75% 70% at 50% 42%, {T['light0']} 0%, {T['light1']} 65%, {T['light2']} 100%); }}
      .acc {{ background: {T['accent']}; color: {T['on_accent']}; border-radius: {999 if r >= 0.5 else int(18 * r)}px; }}
      .acc--light {{ background: {T['accent_light']}; color: {T['on_accent_light']}; }}
      .panel--dark {{ background: {T['card_dark']}; color: {T['on_dark']}; }}
      .panel--surface {{ background: {T['paper']}; }}
      .state--released, .state--dark {{ background: {T['accent']}; color: {T['on_accent']}; }}
      .btn--dark {{ background: {T['accent']}; color: {T['on_accent']}; }}
      .tick {{ background: {T['accent']}; }}
      .tick::after {{ border-color: {T['on_accent']}; }}
      .tick--light {{ background: {T['accent_light']}; }}
      .tick--light::after {{ border-color: {T['on_accent_light']}; }}
      .rf-display, .kl, .kt {{ font-family: {T['font_display']}; font-weight: {T['display_weight']}; letter-spacing: {T['display_tracking']}; {up} }}
"""
