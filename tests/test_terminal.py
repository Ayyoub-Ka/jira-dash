import subprocess

import pytest

from jira_dash import terminal


def test_detect_from_environment():
    assert terminal.detect({"TERM_PROGRAM": "ghostty"}) == "ghostty"
    assert terminal.detect({"TERM_PROGRAM": "iTerm.app"}) == "iterm"
    assert terminal.detect({"TERM_PROGRAM": "Apple_Terminal"}) == "terminal"
    assert terminal.detect({"TERM_PROGRAM": "WezTerm"}) == "wezterm"
    assert terminal.detect({"TERM": "xterm-kitty"}) == "kitty"
    assert terminal.detect({"TERMINAL_EMULATOR": "JetBrains-JediTerm"}) is None


def test_build_args_quotes_applescript_strings():
    args = terminal.build_args("terminal", 'echo "hi" \\ there', "/bin/zsh")
    assert args[2] == 'tell application "Terminal" to do script "echo \\"hi\\" \\\\ there"'
    assert terminal.build_args("ghostty", "ls", "/bin/zsh") == [
        "open",
        "-na",
        "Ghostty",
        "--args",
        "-e",
        "/bin/zsh",
        "-ic",
        "ls",
    ]
    with pytest.raises(ValueError, match="unknown terminal"):
        terminal.build_args("xterm", "ls", "/bin/zsh")


def test_launch_uses_template_and_cwd(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: calls.append((args, kw)))
    monkeypatch.setenv("SHELL", "/bin/zsh")
    label = terminal.launch("claude 'x y'", "/tmp/repo", None, "open -na Ghostty --args -e {shell} -ic {script}")
    assert label == "open"
    assert calls[0][0] == ["open", "-na", "Ghostty", "--args", "-e", "/bin/zsh", "-ic", "cd /tmp/repo && claude 'x y'"]
    assert calls[0][1]["start_new_session"] is True


def test_launch_prefers_explicit_kind_then_detection(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: calls.append(args))
    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    assert terminal.launch("ls", None, "ghostty") == "ghostty"
    assert calls[-1][:3] == ["open", "-na", "Ghostty"]
    assert terminal.launch("ls", None, "auto") == "iterm"
    assert calls[-1][0] == "osascript"


def test_launch_without_any_terminal_raises(monkeypatch):
    monkeypatch.setattr(terminal, "detect", lambda env=None: None)
    monkeypatch.setattr(terminal, "fallback", lambda: None)
    with pytest.raises(RuntimeError, match="no terminal app found"):
        terminal.launch("ls")
