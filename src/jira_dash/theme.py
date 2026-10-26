from __future__ import annotations

from textual.color import Color, ColorParseError
from textual.theme import Theme

DEFAULT_FALLBACK = "textual-dark"


def textual_theme(colors: dict[str, str], name: str) -> Theme:
    bg, fg = Color.parse(colors["background"]), Color.parse(colors["foreground"])

    def pick(key: str, fallback: Color) -> str:
        try:
            return Color.parse(colors[key]).hex
        except (KeyError, ColorParseError):
            return fallback.hex

    mid = bg.blend(fg, 0.5)
    selection = pick("selection-background", bg.blend(fg, 0.18))
    accent = pick("cursor-color", mid)
    return Theme(
        name=name,
        primary=pick("palette.4", mid),
        secondary=pick("palette.6", mid),
        accent=accent,
        warning=pick("palette.3", mid),
        error=pick("palette.1", mid),
        success=pick("palette.2", mid),
        foreground=fg.hex,
        background=bg.hex,
        surface=bg.hex,
        panel=bg.blend(fg, 0.07).hex,
        dark=bg.brightness < 0.5,
        variables={
            "block-cursor-background": selection,
            "block-cursor-foreground": fg.hex,
            "block-cursor-text-style": "none",
            "block-cursor-blurred-background": bg.blend(fg, 0.1).hex,
            "block-cursor-blurred-foreground": fg.hex,
            "input-selection-background": selection,
            "footer-key-foreground": accent,
            "scrollbar": bg.blend(fg, 0.2).hex,
            "scrollbar-hover": bg.blend(fg, 0.3).hex,
            "scrollbar-active": accent,
            "scrollbar-background": bg.hex,
        },
    )
