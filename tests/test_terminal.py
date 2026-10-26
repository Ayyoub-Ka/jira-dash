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
    assert terminal.detect({"TERM_PROGRAM": "ghostty", "HERDR_PANE_ID": "p1"}) == "herdr"


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


class FakeHerdr:
    def __init__(self, workspaces):
        self.workspaces = workspaces
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("workspace", "list"):
            return {"result": {"workspaces": self.workspaces}}
        if args[:2] == ("workspace", "create"):
            return {
                "result": {
                    "workspace": {"workspace_id": "ws-new"},
                    "tab": {"tab_id": "tab-new"},
                    "root_pane": {"pane_id": "pane-new"},
                }
            }
        if args[:2] == ("tab", "create"):
            return {"result": {"tab": {"tab_id": "tab-2"}, "root_pane": {"pane_id": "pane-2"}}}
        return {}


def test_herdr_joins_existing_workspace_by_card_label(monkeypatch):
    fake = FakeHerdr(
        [{"label": "PROJ-1 Fix login", "workspace_id": "ws-1"}, {"label": "PROJ-10", "workspace_id": "ws-10"}]
    )
    monkeypatch.setattr(terminal, "herdr", fake)
    monkeypatch.setattr(terminal, "herdr_running", lambda: True)
    where = terminal.launch("cap beta rails:console", "/repo", "herdr", key="PROJ-1", name="rails", title="Fix login")
    assert where == "workspace PROJ-1"
    assert ("tab", "create", "--workspace", "ws-1", "--cwd", "/repo", "--label", "rails") in fake.calls
    assert ("workspace", "focus", "ws-1") in fake.calls
    assert fake.calls[-1] == ("pane", "run", "pane-2", "cap beta rails:console")


def test_herdr_creates_workspace_when_missing(monkeypatch):
    fake = FakeHerdr([{"label": "PROJ-10", "workspace_id": "ws-10"}])
    monkeypatch.setattr(terminal, "herdr", fake)
    monkeypatch.setattr(terminal, "herdr_running", lambda: True)
    where = terminal.launch("claude x", "/repo", "herdr", key="PROJ-1", name="Claude", title="A very long summary " * 5)
    assert where == "new workspace PROJ-1"
    create = next(c for c in fake.calls if c[:2] == ("workspace", "create"))
    assert create[2:] == ("--cwd", "/repo", "--label", "PROJ-1 A very long summary A very long summary", "--focus")
    assert ("tab", "rename", "tab-new", "Claude") in fake.calls
    assert ("pane", "rename", "pane-new", "Claude") in fake.calls
    assert fake.calls[-1] == ("pane", "run", "pane-new", "claude x")


def test_herdr_falls_back_to_a_window_when_server_is_down(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: calls.append(args))
    monkeypatch.setattr(terminal, "herdr_running", lambda: False)
    monkeypatch.setenv("TERM_PROGRAM", "ghostty")
    monkeypatch.setenv("HERDR_PANE_ID", "p1")
    label = terminal.launch("ls", "/repo", "auto", key="PROJ-1", name="x")
    assert label == "ghostty (no herdr server)"
    assert calls[-1][:3] == ["open", "-na", "Ghostty"]


def test_herdr_without_card_key_is_a_window(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: calls.append(args))
    monkeypatch.setattr(terminal, "herdr_running", lambda: True)
    with pytest.raises(ValueError, match="herdr opens a workspace tab"):
        terminal.launch("ls", None, "herdr")
    assert calls == []
