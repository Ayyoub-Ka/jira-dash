import subprocess

import pytest

from jira_dash import addons, terminal
from jira_dash.addons import herdr


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
    monkeypatch.setattr(herdr, "herdr", fake)
    monkeypatch.setattr(herdr, "available", lambda: True)
    where = terminal.launch("cap beta rails:console", "/repo", "herdr", key="PROJ-1", name="rails", title="Fix login")
    assert where == "workspace PROJ-1"
    assert ("tab", "create", "--workspace", "ws-1", "--cwd", "/repo", "--label", "rails") in fake.calls
    assert ("workspace", "focus", "ws-1") in fake.calls
    assert fake.calls[-1] == ("pane", "run", "pane-2", "cap beta rails:console")


def test_herdr_creates_workspace_when_missing(monkeypatch):
    fake = FakeHerdr([{"label": "PROJ-10", "workspace_id": "ws-10"}])
    monkeypatch.setattr(herdr, "herdr", fake)
    monkeypatch.setattr(herdr, "available", lambda: True)
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
    monkeypatch.setattr(herdr, "available", lambda: False)
    monkeypatch.setenv("TERM_PROGRAM", "ghostty")
    monkeypatch.setenv("HERDR_PANE_ID", "p1")
    label = terminal.launch("ls", "/repo", "auto", key="PROJ-1", name="x")
    assert label == "ghostty (no herdr server)"
    assert calls[-1][:3] == ["open", "-na", "Ghostty"]


def test_herdr_without_card_key_opens_a_window(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: calls.append(args))
    monkeypatch.setattr(herdr, "available", lambda: True)
    monkeypatch.setenv("TERM_PROGRAM", "ghostty")
    assert terminal.launch("ls", None, "herdr") == "ghostty"
    assert calls[-1][:3] == ["open", "-na", "Ghostty"]


def test_herdr_is_found_and_detected_as_a_terminal_addon():
    assert addons.find("terminal", "herdr") is herdr
    assert addons.detect("terminal", {"HERDR_PANE_ID": "p1"}) is herdr
    assert addons.detect("terminal", {"TERM_PROGRAM": "ghostty"}) is None
    assert terminal.detect({"TERM_PROGRAM": "ghostty", "HERDR_PANE_ID": "p1"}) == "ghostty"


def test_unknown_terminal_lists_addons():
    with pytest.raises(ValueError, match="kitty, herdr"):
        terminal.build_args("nope", "ls", "/bin/sh")
