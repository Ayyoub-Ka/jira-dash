from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Mapping

KINDS = ("ghostty", "iterm", "terminal", "wezterm", "kitty")


def detect(env: Mapping[str, str] | None = None) -> str | None:
    env = os.environ if env is None else env
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


def launch(command: str, cwd: str | None = None, kind: str | None = None, template: str | None = None) -> str:
    shell = os.environ.get("SHELL") or "/bin/sh"
    script = f"cd {shlex.quote(cwd)} && {command}" if cwd else command
    if template:
        args = [a.format(shell=shell, script=script, cwd=cwd or "") for a in shlex.split(template)]
        label = args[0]
    else:
        resolved = (kind if kind and kind != "auto" else None) or detect() or fallback()
        if not resolved:
            raise RuntimeError("no terminal app found; set `terminal` or `terminal_command` in the config")
        args = build_args(resolved, script, shell)
        label = resolved
    subprocess.Popen(
        args, start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return label
