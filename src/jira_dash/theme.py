from __future__ import annotations

import os
from pathlib import Path

from textual.color import Color, ColorParseError
from textual.theme import Theme

DEFAULT_FALLBACK = "textual-dark"


def _xdg() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "ghostty"


def ghostty_config_paths() -> list[Path]:
    support = Path.home() / "Library/Application Support/com.mitchellh.ghostty"
    return [_xdg() / "config", _xdg() / "config.ghostty", support / "config", support / "config.ghostty"]


def ghostty_theme_dirs() -> list[Path]:
    bundled = "Contents/Resources/ghostty/themes"
    return [
        _xdg() / "themes",
        Path.home() / "Applications/Ghostty.app" / bundled,
        Path("/Applications/Ghostty.app") / bundled,
        Path("/usr/share/ghostty/themes"),
    ]


def _pairs(text: str):
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and not line.lstrip().startswith("#"):
            yield key.strip(), value.strip()


def ghostty_theme_name(configs: list[Path] | None = None) -> str | None:
    name = None
    for path in configs if configs is not None else ghostty_config_paths():
        if path.is_file():
            for key, value in _pairs(path.read_text()):
                if key == "theme":
                    name = value
    if not name or "light:" in name or "dark:" in name:
        return None
    return name


def read_ghostty_theme(name: str, dirs: list[Path] | None = None) -> dict[str, str] | None:
    candidate = Path(name).expanduser()
    paths = [candidate] if candidate.is_absolute() else [d / name for d in (dirs or ghostty_theme_dirs())]
    for path in paths:
        if path.is_file():
            colors = {}
            for key, value in _pairs(path.read_text()):
                if key == "palette":
                    index, _, color = value.partition("=")
                    colors[f"palette.{index.strip()}"] = color.strip()
                else:
                    colors[key] = value
            return colors if "background" in colors and "foreground" in colors else None
    return None


def textual_theme(colors: dict[str, str], name: str = "ghostty") -> Theme:
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


def ghostty_signature(configs: list[Path] | None = None, dirs: list[Path] | None = None) -> tuple:
    name = ghostty_theme_name(configs)
    stamps = []
    for path in [
        *(configs if configs is not None else ghostty_config_paths()),
        *((d / name) for d in (dirs or ghostty_theme_dirs()) if name),
    ]:
        stamps.append(path.stat().st_mtime_ns if path.is_file() else 0)
    return name, tuple(stamps)


def load_ghostty_theme(name: str, configs: list[Path] | None = None, dirs: list[Path] | None = None) -> Theme | None:
    theme_name = ghostty_theme_name(configs)
    colors = read_ghostty_theme(theme_name, dirs) if theme_name else None
    return textual_theme(colors, name) if colors else None
