import asyncio
import contextlib

from textual.widgets import DataTable, Static

from jira_dash import app as app_module
from jira_dash.app import JiraDash


def run(coro):
    return asyncio.run(coro)


def detail_text(app) -> str:
    widget = app.query_one("#detail", Static)
    content = getattr(widget, "content", None) or getattr(widget, "renderable", "")
    return content.plain if hasattr(content, "plain") else str(content)


def test_load_navigate_and_actions(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.5)
            table = app.query_one(DataTable)
            assert table.row_count == 4
            assert str(table.get_row_at(3)[0].plain) == "PROJ-0"  # done card sorted last
            detail = detail_text(app)
            assert "**bold**" in detail and "- item" in detail and "Bob" in detail and "shot.png" in detail

            await pilot.press("l")
            await pilot.pause(0.3)
            assert app.current_index == 1
            assert any(c[0] == "search" and "sprint = 42" in c[1] for c in fake.calls)

            await pilot.press("m")
            await pilot.pause(0.3)
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert ("transition", "PROJ-1", "1") in fake.calls

            await pilot.press("c")
            await pilot.pause(0.3)
            await pilot.press("h", "i")
            await pilot.press("ctrl+s")
            await pilot.pause(0.3)
            assert ("comment", "PROJ-1", "hi") in fake.calls

            await pilot.press("a")
            await pilot.pause(0.3)
            assert ("assign", "PROJ-1", "acct") in fake.calls
            await pilot.press("u")
            await pilot.pause(0.3)
            assert ("assign", "PROJ-1", None) in fake.calls

            await pilot.press("slash")
            await pilot.press("2")
            await pilot.pause(0.3)
            assert table.row_count == 1
            await pilot.press("escape")
            await pilot.pause(0.2)
            assert table.row_count == 4

    run(scenario())


def test_list_read_focus_toggle(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    para = {"type": "paragraph", "content": [{"type": "text", "text": "line\n" * 120}]}
    long_desc = {"type": "doc", "content": [para]}
    base_issue = fake.issue
    fake.issue = lambda key: {**base_issue(key), "fields": {**base_issue(key)["fields"], "description": long_desc}}

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.5)
            table = app.query_one(DataTable)
            await pilot.press("v")
            await pilot.pause(0.2)
            assert app._reading()
            await pilot.press("j", "j", "j")
            await pilot.pause(0.2)
            assert app.preview.scroll_y > 0 and table.cursor_row == 0
            await pilot.press("escape")
            await pilot.pause(0.2)
            assert not app._reading()
            await pilot.press("j")
            await pilot.pause(0.2)
            assert table.cursor_row == 1
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert app._reading()
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert not app._reading()

    run(scenario())


def test_preview_debounce_cache_and_refresh_keeps_cursor(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    cfg["refresh_seconds"] = 1

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.6)
            await pilot.press("j", "j")
            await pilot.pause(0.6)
            fetched = [c[1] for c in fake.calls if c[0] == "issue"]
            assert "PROJ-1" in fetched and "PROJ-3" in fetched and "PROJ-2" not in fetched
            assert app.selected_key() == "PROJ-3"

            searches = sum(1 for c in fake.calls if c[0] == "search")
            await pilot.pause(1.5)
            assert sum(1 for c in fake.calls if c[0] == "search") > searches
            assert app.selected_key() == "PROJ-3"

            before = len(fake.calls)
            await pilot.press("k", "k")
            await pilot.pause(0.5)
            assert ("issue", "PROJ-1") not in fake.calls[before:]

    run(scenario())


def test_focus_issue_tab(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    app = JiraDash(cfg=cfg, jira=fake, focus_issue="PROJ-7")
    assert app.sections[0].jql == "key = PROJ-7"
    assert app.sections[0].hide_done is False


def test_custom_keybinding_runs_command_with_card_fields(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    cfg["keybindings"] = [{"key": "C", "name": "Claude", "command": "echo {key} {summary} {url}", "cwd": "~"}]
    runs = []
    monkeypatch.setattr(app_module.subprocess, "run", lambda cmd, **kw: runs.append((cmd, kw)))

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        app.suspend = contextlib.nullcontext
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.5)
            await pilot.press("j")
            await pilot.pause(0.3)
            await pilot.press("C")
            await pilot.pause(0.3)
            assert runs, "command did not run"
            cmd, kw = runs[0]
            assert cmd == "echo PROJ-2 'Summary 2' https://example.atlassian.net/browse/PROJ-2"
            assert kw["shell"] is True and kw["cwd"].endswith(app_module.os.path.expanduser("~"))

    run(scenario())


def test_per_tab_columns_with_custom_field(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    cfg["columns"] = ["key", "status", "reporter", "labels"]
    cfg["sections"].append(
        {
            "name": "DR",
            "jql": "project = DR",
            "columns": ["key", {"field": "Server(s)", "title": "Server", "width": 10}],
        }
    )

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.5)
            table = app.query_one(DataTable)
            assert [c.label.plain for c in table.columns.values()] == ["Key", "Status", "Reporter", "Labels"]
            row = [c.plain for c in table.get_row_at(0)]
            assert row[2] == "Rae" and row[3] == "x, y"

            await pilot.press("h")
            await pilot.pause(0.4)
            assert app.current_section.name == "DR"
            assert [c.label.plain for c in table.columns.values()] == ["Key", "Server"]
            assert table.get_row_at(0)[1].plain.startswith("srv-")
            assert any(c[0] == "search" and c[2] == {"Server(s)": "customfield_10090"} for c in fake.calls)

    run(scenario())
