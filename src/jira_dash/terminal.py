from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Mapping

KINDS = ("herdr", "ghostty", "iterm", "terminal", "wezterm", "kitty")


def detect(env: Mapping[str, str] | None = None) -> str | None:
    env = os.environ if env is None else env
    if env.get("HERDR_PANE_ID") or env.get("HERDR_WORKSPACE_ID"):
        return "herdr"
    prog = env.get("TERM_PROGRAM", "").lower()
    if "ghostty" in prog:
        return "ghostty"
    if "iterm" in prog:
        return "iterm"
    if "apple_terminal" in prog:
        return "terminal"
    if "wezterm" in prog:
        return "wezterm"
    if env.get("KITTY_WINDOW_ID") or env.get("TERM") == "xterm-kitty":
        return "kitty"
    return None


def _mac_app_installed(name: str) -> bool:
    return subprocess.run(["open", "-Ra", name], capture_output=True).returncode == 0


def fallback() -> str | None:
    if sys.platform == "darwin":
        for kind, app in (("ghostty", "Ghostty"), ("iterm", "iTerm"), ("terminal", "Terminal")):
            if _mac_app_installed(app):
                return kind
    for kind, binary in (("wezterm", "wezterm"), ("kitty", "kitty")):
        if shutil.which(binary):
            return kind
    return None


def _applescript_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_args(kind: str, script: str, shell: str) -> list[str]:
    if kind == "herdr":
        raise ValueError("herdr opens a workspace tab, not a window; use launch()")
    if kind == "ghostty":
        return ["open", "-na", "Ghostty", "--args", "-e", shell, "-ic", script]
    if kind == "iterm":
        write = (
            f'tell current session of current window of application "iTerm" to write text {_applescript_str(script)}'
        )
        return ["osascript", "-e", 'tell application "iTerm" to create window with default profile', "-e", write]
    if kind == "terminal":
        return [
            "osascript",
            "-e",
            f'tell application "Terminal" to do script {_applescript_str(script)}',
            "-e",
            'tell application "Terminal" to activate',
        ]
    if kind == "wezterm":
        return ["wezterm", "start", "--", shell, "-ic", script]
    if kind == "kitty":
        return ["kitty", "--detach", shell, "-ic", script]
    raise ValueError(f"unknown terminal '{kind}', expected one of {', '.join(KINDS)}")


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


def herdr_running() -> bool:
    if not shutil.which("herdr"):
        return False
    try:
        return subprocess.run(["herdr", "status"], capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def herdr_find_workspace(key: str) -> str | None:
    for ws in (herdr("workspace", "list").get("result") or {}).get("workspaces") or []:
        label = ws.get("label") or ""
        if label == key or label.startswith(key + " "):
            return ws.get("workspace_id")
    return None


def herdr_open(command: str, cwd: str | None, key: str, name: str, title: str = "") -> str:
    """Run `command` in a tab of the Herdr workspace labelled `key`, creating the workspace if needed."""
    cwd = cwd or os.path.expanduser("~")
    ws = herdr_find_workspace(key)
    if ws:
        tab = (herdr("tab", "create", "--workspace", ws, "--cwd", cwd, "--label", name).get("result")) or {}
        pane = (tab.get("root_pane") or {}).get("pane_id")
        herdr("workspace", "focus", ws)
        where = f"workspace {key}"
    else:
        label = f"{key} {title[:40]}".strip()
        made = herdr("workspace", "create", "--cwd", cwd, "--label", label, "--focus").get("result") or {}
        ws = (made.get("workspace") or {}).get("workspace_id")
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


def launch(
    command: str,
    cwd: str | None = None,
    kind: str | None = None,
    template: str | None = None,
    key: str = "",
    name: str = "",
    title: str = "",
) -> str:
    shell = os.environ.get("SHELL") or "/bin/sh"
    script = f"cd {shlex.quote(cwd)} && {command}" if cwd else command
    if template:
        args = [a.format(shell=shell, script=script, cwd=cwd or "") for a in shlex.split(template)]
        label = args[0]
    else:
        resolved = (kind if kind and kind != "auto" else None) or detect() or fallback()
        if resolved == "herdr" and key:
            if herdr_running():
                return herdr_open(command, cwd, key, name or "command", title)
            resolved = (detect({k: v for k, v in os.environ.items() if not k.startswith("HERDR_")})) or fallback()
            if resolved:
                resolved_note = " (no herdr server)"
            else:
                raise RuntimeError("herdr is not running and no terminal app found")
        else:
            resolved_note = ""
        if not resolved:
            raise RuntimeError("no terminal app found; set `terminal` or `terminal_command` in the config")
        args = build_args(resolved, script, shell)
        label = resolved + resolved_note
    subprocess.Popen(
        args, start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return label
