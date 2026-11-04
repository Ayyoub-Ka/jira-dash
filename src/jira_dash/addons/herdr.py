"""Open `new_terminal` keybindings as a tab in the card's Herdr workspace (https://herdr.dev)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping

NAME = "herdr"
KIND = "terminal"


def detect(env: Mapping[str, str]) -> bool:
    return bool(env.get("HERDR_PANE_ID") or env.get("HERDR_WORKSPACE_ID"))


def available() -> bool:
    if not shutil.which("herdr"):
        return False
    try:
        r = subprocess.run(["herdr", "status", "server"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    # `herdr status` exits 0 even when the server is down
    return r.returncode == 0 and "status: running" in r.stdout.splitlines()


def herdr(*args: str) -> dict:
    try:
        r = subprocess.run(["herdr", *args], capture_output=True, text=True, timeout=15)
    except FileNotFoundError:
        raise RuntimeError("herdr is not installed") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"herdr {args[0]} timed out") from None
    if r.returncode != 0:
        err = (r.stderr or r.stdout).strip().splitlines()
        raise RuntimeError(f"herdr {' '.join(args[:2])}: {err[0] if err else r.returncode}")
    try:
        return json.loads(r.stdout) if r.stdout.strip() else {}
    except ValueError:
        return {}


def find_workspace(key: str) -> str | None:
    for ws in (herdr("workspace", "list").get("result") or {}).get("workspaces") or []:
        label = ws.get("label") or ""
        if label == key or label.startswith(key + " "):
            return ws.get("workspace_id")
    return None


def launch(command: str, cwd: str | None, key: str, name: str, title: str = "") -> str:
    """Run `command` in a tab of the Herdr workspace labelled `key`, creating the workspace if needed."""
    cwd = cwd or os.path.expanduser("~")
    ws = find_workspace(key)
    if ws:
        tab = (herdr("tab", "create", "--workspace", ws, "--cwd", cwd, "--label", name).get("result")) or {}
        pane = (tab.get("root_pane") or {}).get("pane_id")
        herdr("workspace", "focus", ws)
        where = f"workspace {key}"
    else:
        label = f"{key} {title[:40]}".strip()
        made = herdr("workspace", "create", "--cwd", cwd, "--label", label, "--focus").get("result") or {}
        pane = (made.get("root_pane") or {}).get("pane_id")
        tab_id = (made.get("tab") or {}).get("tab_id")
        if tab_id:
            herdr("tab", "rename", tab_id, name)
        where = f"new workspace {key}"
    if not pane:
        raise RuntimeError(f"herdr gave no pane for {key}")
    herdr("pane", "rename", pane, name)
    herdr("pane", "run", pane, command)
    return where
