"""Optional integrations with other tools. Each module declares NAME and KIND ("terminal" or "theme")."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Mapping
from types import ModuleType


def all_addons(kind: str) -> list[ModuleType]:
    mods = (importlib.import_module(f"{__name__}.{m.name}") for m in pkgutil.iter_modules(__path__))
    return [m for m in mods if getattr(m, "KIND", None) == kind]


def find(kind: str, name: str) -> ModuleType | None:
    return next((m for m in all_addons(kind) if m.NAME == name), None)


def detect(kind: str, env: Mapping[str, str]) -> ModuleType | None:
    return next((m for m in all_addons(kind) if hasattr(m, "detect") and m.detect(env)), None)
