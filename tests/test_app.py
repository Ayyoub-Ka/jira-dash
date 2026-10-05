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
            assert ("comment", "PROJ-1", "hi", {}) in fake.calls

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
            "columns": ["key", {"field": "Environment", "title": "Env", "width": 10}],
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
            assert [c.label.plain for c in table.columns.values()] == ["Key", "Env"]
            assert table.get_row_at(0)[1].plain.startswith("env-")
            await pilot.pause(0.4)
            assert "Env staging" in detail_text(app)
            assert any(c[0] == "search" and c[2] == {"Environment": "customfield_12345"} for c in fake.calls)
            assert any(c[0] == "search" and c[3] == ["status", "reporter", "labels"] for c in fake.calls)

    run(scenario())


def test_gh_dash_style_paging_and_tab_keys(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    from jira_dash.jira import Issue

    fake.issues = [
        Issue(f"PROJ-{i}", f"S{i}", "In Progress", "Bug", "High", "Ann", "2026-01-01", {}) for i in range(60)
    ]

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 24)) as pilot:
            await pilot.pause(0.5)
            table = app.query_one(DataTable)
            await pilot.press("shift+down")
            await pilot.pause(0.2)
            assert table.cursor_row > 3
            await pilot.press("shift+up")
            await pilot.pause(0.2)
            assert table.cursor_row == 0
            await pilot.press("shift+right")
            await pilot.pause(0.3)
            assert app.current_index == 1
            await pilot.press("shift+left")
            await pilot.pause(0.3)
            assert app.current_index == 0

    run(scenario())


def test_detached_keybinding_uses_custom_column_value(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    cfg["sections"] = [
        {"name": "Ops", "jql": "project = OPS", "columns": ["key", {"field": "Environment", "title": "Env"}]}
    ]
    cfg["keybindings"] = [{"key": "T", "name": "console", "suspend": False, "command": "echo {env} {jira_server}"}]
    started = []
    monkeypatch.setattr(app_module.subprocess, "Popen", lambda cmd, **kw: started.append((cmd, kw)))

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.5)
            await pilot.press("T")
            await pilot.pause(0.3)
            assert started and started[0][0] == "echo env-1 https://example.atlassian.net"
            assert started[0][1]["start_new_session"] is True

    run(scenario())


def test_comment_mentions_resolve_and_pick(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.5)
            await pilot.press("c")
            await pilot.pause(0.3)
            editor = app.screen.query_one("#body")
            editor.text = 'thanks @ann and @bo and @"Bob Cee" and @nobody, mail me@example.com'
            await pilot.press("ctrl+s")
            await pilot.pause(0.5)
            assert isinstance(app.screen, app_module.Picker)
            assert "@bo" in app.screen.title_text
            await pilot.press("down", "enter")
            await pilot.pause(0.5)
            call = next(c for c in fake.calls if c[0] == "comment")
            assert call[3] == {
                "ann": ("acc-ann", "Ann Bee"),
                "bo": ("acc-bo", "Bo Dee"),
                "Bob Cee": ("acc-bob", "Bob Cee"),
            }

    run(scenario())


def test_activity_tab_unread_marks_and_persists(cfg, fake, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    state = tmp_path / "seen.json"
    from jira_dash.state import SeenStore

    monkeypatch.setattr(app_module, "SeenStore", lambda: SeenStore(state))
    cfg["activity_tab"] = True
    cfg["sections"] = []

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.6)
            table = app.query_one(DataTable)
            tab = app.tab_for(app.sections[0])
            assert str(tab.label) == "Activity (4)"
            assert table.get_row_at(0)[0].plain.startswith("● PROJ-")
            assert app.selected_key() == "PROJ-1"
            await pilot.press("j")
            await pilot.pause(0.6)
            assert str(tab.label) == "Activity (3)"
            assert not table.get_row_at(1)[0].plain.startswith("●")
            assert table.get_row_at(0)[0].plain.startswith("●")
            assert state.exists() and "PROJ-2" in state.read_text()
            await pilot.press("k")
            await pilot.pause(0.6)
            assert str(tab.label) == "Activity (2)"
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert app._reading()

    run(scenario())


def test_pr_list_fetched_only_after_dwell(cfg, fake, monkeypatch):
    calls = []
    monkeypatch.setattr(
        app_module, "prs_for_issue", lambda key: calls.append(key) or [{"number": 1, "title": "t", "state": "open"}]
    )
    cfg["pr_reviews"] = True
    cfg["pr_dwell_seconds"] = 0.6
    monkeypatch.setattr(app_module, "my_pr_keys", lambda days: set())

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.3)
            await pilot.press("j", "j")
            await pilot.pause(0.3)
            assert calls == []
            await pilot.pause(0.9)
            assert calls == ["PROJ-3"]
            assert "Pull requests" in detail_text(app)

    run(scenario())


def test_stale_preview_is_dropped_on_refresh(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.6)
            assert "PROJ-1" in app.preview_cache
            fetched = sum(1 for c in fake.calls if c == ("issue", "PROJ-1"))
            fake.issues[1].updated_at = "2027-01-01T00:00:00.000+0000"
            app.load_section(app.sections[0])
            await pilot.pause(0.6)
            assert sum(1 for c in fake.calls if c == ("issue", "PROJ-1")) == fetched + 1
            app.load_section(app.sections[0])
            await pilot.pause(0.6)
            assert sum(1 for c in fake.calls if c == ("issue", "PROJ-1")) == fetched + 2

    run(scenario())


def test_favourites_are_inserted_before_activity(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    cfg["activity_tab"] = True
    cfg["import_favourite_filters"] = True

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.6)
            assert [s.name for s in app.sections][-2:] == ["Fav", "Activity"]
            assert app.sections[-1].activity
            ids = [t.id for t in app.tabs.query(app_module.Tab)]
            assert ids == [app._tab_ids[s] for s in app.sections]
            assert app.sections[-1] in app.issues or app.sections[-1] in app._loading

    run(scenario())


def test_startup_searches_each_tab_once(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.8)
            assert sum(1 for c in fake.calls if c[0] == "search") == 1

    run(scenario())


def test_mention_single_fuzzy_hit_needs_word_prefix(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    fake.search_users = lambda q: [("acc-tab", "Bobby Tables")] if q == "tab" else []

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.5)
            await pilot.press("c")
            await pilot.pause(0.3)
            app.screen.query_one("#body").text = "cc @tab"
            await pilot.press("ctrl+s")
            await pilot.pause(0.5)
            call = next(c for c in fake.calls if c[0] == "comment")
            assert call[3] == {"tab": ("acc-tab", "Bobby Tables")}

    run(scenario())


def test_slow_earlier_search_does_not_overwrite_newer(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.6)
            stale = [app_module.Issue("PROJ-9", "old", "In Progress", "Bug", "High", "A", "2026", {})]
            sec = app.sections[0]
            app.load_section(sec)
            app._store_result(sec, app._load_seq[sec] - 1, stale, {})
            await pilot.pause(0.5)
            assert [i.key for i in app.issues[sec]] != ["PROJ-9"]

    run(scenario())


def test_background_refresh_resolves_pr_keys_once(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    calls = []
    monkeypatch.setattr(app_module, "my_pr_keys", lambda days: calls.append(1) or (set(), set()))
    cfg["pr_reviews"] = True
    cfg["activity_tab"] = True
    cfg["pr_refresh_every"] = 1
    cfg["refresh_seconds"] = 1

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.6)
            assert len(calls) == 1
            await pilot.pause(1.0)
            assert len(calls) == 2
            assert "loading" not in str(app.status_bar.render())

    run(scenario())


def test_favourites_do_not_disturb_activity_load(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    cfg["activity_tab"] = True
    cfg["import_favourite_filters"] = True
    cfg["sections"] = []

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.8)
            assert [s.name for s in app.sections] == ["Fav", "Activity"]
            assert app.current_section.activity
            assert {i.key for i in app.issues[app.sections[1]]} == {"PROJ-0", "PROJ-1", "PROJ-2", "PROJ-3"}
            assert "Activity" in str(app.tab_for(app.sections[1]).label)

    run(scenario())


def test_slow_preview_does_not_overwrite_current_card(cfg, fake, monkeypatch):
    import time as _time

    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    base = fake.issue

    def slow_issue(key):
        if key == "PROJ-1":
            _time.sleep(0.8)
        return base(key)

    fake.issue = slow_issue

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.4)
            await pilot.press("j")
            await pilot.pause(1.2)
            assert app.selected_key() == "PROJ-2"
            assert detail_text(app).startswith("PROJ-2")

    run(scenario())


def test_arrow_keys_mark_read_like_vim_keys(cfg, fake, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    from jira_dash.state import SeenStore

    monkeypatch.setattr(app_module, "SeenStore", lambda: SeenStore(tmp_path / "seen.json"))
    cfg["activity_tab"] = True
    cfg["sections"] = []

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.6)
            tab = app.tab_for(app.sections[0])
            assert str(tab.label) == "Activity (4)"
            await pilot.press("down")
            await pilot.pause(0.6)
            await pilot.press("up")
            await pilot.pause(0.6)
            assert str(tab.label) == "Activity (2)"

    run(scenario())


def test_refresh_drops_other_tabs_results(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.5)
            await pilot.press("l")
            await pilot.pause(0.5)
            assert app.sections[0] in app.issues and app.sections[1] in app.issues
            await pilot.press("r")
            await pilot.pause(0.5)
            assert app.sections[0] not in app.issues
            await pilot.press("h")
            await pilot.pause(0.5)
            assert app.sections[0] in app.issues

    run(scenario())


def test_bad_placeholder_in_keybinding_is_reported(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    cfg["keybindings"] = [{"key": "W", "name": "awk", "command": "awk '{print $1}' {key}"}]
    ran = []
    monkeypatch.setattr(app_module.subprocess, "run", lambda *a, **k: ran.append(a))

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.5)
            await pilot.press("W")
            await pilot.pause(0.3)
            assert ran == [] and app.is_running

    run(scenario())


def test_yank_attachments_and_gh_dash_actions(cfg, fake, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    copied = []
    monkeypatch.setattr(app_module.clipboard, "copy", lambda text: copied.append(text) or True)
    opened = []
    monkeypatch.setattr(app_module.webbrowser, "open", lambda url: opened.append(url))
    ran = []
    monkeypatch.setattr(app_module.subprocess, "run", lambda cmd, **kw: ran.append(cmd))
    monkeypatch.setattr(app_module, "gh_dash_config_for", lambda key: str(tmp_path / "gh.yml"))

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        app.suspend = contextlib.nullcontext
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.5)
            await pilot.press("y")
            assert copied == ["PROJ-1"]
            await pilot.press("Y")
            assert copied[-1] == "https://example.atlassian.net/browse/PROJ-1"
            await pilot.press("x")
            await pilot.pause(0.3)
            assert isinstance(app.screen, app_module.Picker)
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert opened == ["https://x/att/1"]
            await pilot.press("g")
            await pilot.pause(0.3)
            assert ran and ran[0][:2] == ["gh", "dash"]

    run(scenario())


def test_new_terminal_keybinding_launches_window(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    cfg["keybindings"] = [{"key": "C", "name": "Claude", "new_terminal": True, "command": "claude {key}", "cwd": "~"}]
    cfg["terminal"] = "ghostty"
    launched = []
    monkeypatch.setattr(app_module.terminal, "launch", lambda *a: launched.append(a) or "ghostty")

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.5)
            await pilot.press("C")
            await pilot.pause(0.3)
            assert launched and launched[0][0] == "claude PROJ-1" and launched[0][2] == "ghostty"
            assert "opened Claude in ghostty" in str(app.status_bar.render())

    run(scenario())


def test_transition_options_put_specific_first_and_show_target():
    trs = [
        {"id": "2", "name": "Code Owner Review", "to": {"name": "Code Owner Review"}, "isGlobal": True},
        {"id": "361", "name": "Deployed", "to": {"name": "Deployed"}, "isGlobal": True},
        {"id": "151", "name": "To Stuck", "to": {"name": "Stuck"}, "isGlobal": False},
        {"id": "81", "name": "To Code Review", "to": {"name": "Code Review"}, "isGlobal": False},
        {"id": "9", "name": "Pass to Ready for Staging", "to": {"name": "Ready to deploy"}, "isGlobal": False},
    ]
    opts = app_module.transition_options(trs)
    assert [o[0] for o in opts] == ["81", "9", "151", "2", "361"]
    assert opts[0][1].plain == "Code Review"
    assert opts[1][1].plain == "Ready to deploy  (Pass to Ready for Staging)"
    assert opts[3][1].style == "dim"


def test_pick_choices_accept_pairs_strings_and_mappings():
    pick = {"options": [["web", "~/code/web"], "plain", {"label": "API", "value": "/srv/api"}, ["solo"]]}
    assert app_module.pick_choices(pick) == [
        ("web", "~/code/web"),
        ("plain", "plain"),
        ("API", "/srv/api"),
        ("solo", "solo"),
    ]


def test_pick_keybinding_asks_then_runs_with_choice(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    cfg["keybindings"] = [
        {
            "key": "S",
            "name": "start",
            "suspend": False,
            "pick": {"title": "Repo", "options": [["web", "~/code/web"], ["api", "~/code/api"]]},
            "command": "start {pick} {pick_label} {key}",
        }
    ]
    started = []
    monkeypatch.setattr(app_module.subprocess, "Popen", lambda cmd, **kw: started.append(cmd))

    async def scenario():
        app = JiraDash(cfg=cfg, jira=fake)
        async with app.run_test(size=(140, 30)) as pilot:
            await pilot.pause(0.5)
            await pilot.press("S")
            await pilot.pause(0.3)
            assert isinstance(app.screen, app_module.Picker) and app.screen.title_text == "Repo"
            await pilot.press("escape")
            await pilot.pause(0.3)
            assert started == []
            await pilot.press("S")
            await pilot.pause(0.3)
            await pilot.press("down", "enter")
            await pilot.pause(0.3)
            home = app_module.os.path.expanduser("~")
            assert started == [f"start {home}/code/api api PROJ-1"]

    run(scenario())


def test_expand_home_only_touches_home_paths():
    home = app_module.os.path.expanduser("~")
    assert app_module.expand_home("~/code") == f"{home}/code"
    assert app_module.expand_home("~") == home
    assert app_module.expand_home("~alias") == "~alias"
    assert app_module.expand_home("prod") == "prod"
