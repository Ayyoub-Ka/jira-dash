"""`theme: ghostty` copies the active Ghostty theme and follows it live."""

from __future__ import annotations

import os
from pathlib import Path

from textual.theme import Theme

from ..theme import textual_theme

NAME = "ghostty"
KIND = "theme"


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


def signature(configs: list[Path] | None = None, dirs: list[Path] | None = None) -> tuple:
    name = ghostty_theme_name(configs)
    stamps = []
    for path in [
        *(configs if configs is not None else ghostty_config_paths()),
        *((d / name) for d in (dirs or ghostty_theme_dirs()) if name),
    ]:
        stamps.append(path.stat().st_mtime_ns if path.is_file() else 0)
    return name, tuple(stamps)


def load(name: str, configs: list[Path] | None = None, dirs: list[Path] | None = None) -> Theme | None:
    theme_name = ghostty_theme_name(configs)
    colors = read_ghostty_theme(theme_name, dirs) if theme_name else None
    return textual_theme(colors, name) if colors else None
