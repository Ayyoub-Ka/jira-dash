from jira_dash import app as app_module
from jira_dash.app import JiraDash, split_order_by
from jira_dash.config import Section


def test_split_order_by():
    assert split_order_by("a = 1 order by Rank") == ("a = 1", "Rank")
    assert split_order_by("a = 1") == ("a = 1", "")


def test_build_jql_placeholders(cfg, fake, monkeypatch):
    cfg["pr_reviews"] = True
    monkeypatch.setattr(app_module, "my_pr_keys", lambda days: ({"PROJ-9"}, {"PROJ-8"}))
    app = JiraDash(cfg=cfg, jira=fake)
    app.call_from_thread = lambda f, *a, **k: f(*a, **k)

    mine = app.build_jql(app.sections[0])
    assert mine == (
        '((assignee = currentUser() OR key in (PROJ-8, PROJ-9))) AND status not in ("Done") ORDER BY updated DESC'
    )

    sprint = app.build_jql(app.sections[1])
    assert sprint == "sprint = 42 ORDER BY Rank"
    assert app.sub_title == "Sprint 42"

    project = app.build_jql(app.sections[2])
    assert project == '(project = PROJ) AND status not in ("Done")'

    authored = app.build_jql(Section("x", "{mine_authored}"))
    assert authored == '((assignee = currentUser() OR key in (PROJ-9))) AND status not in ("Done")'

    reviews = app.build_jql(Section("x", "{review_requested}"))
    assert reviews == '((key in (PROJ-8))) AND status not in ("Done")'


def test_review_requested_is_false_when_no_requests(cfg, fake, monkeypatch):
    cfg["pr_reviews"] = True
    monkeypatch.setattr(app_module, "my_pr_keys", lambda days: ({"PROJ-9"}, set()))
    app = JiraDash(cfg=cfg, jira=fake)
    app.call_from_thread = lambda f, *a, **k: None
    assert app.build_jql(Section("x", "{review_requested}", hide_done=False)) == '(created < "1970-01-02")'


def test_build_jql_keeps_last_keys_on_gh_error(cfg, fake, monkeypatch):
    cfg["pr_reviews"] = True

    def boom(days):
        raise app_module.GhError("rate limited")

    monkeypatch.setattr(app_module, "my_pr_keys", boom)
    app = JiraDash(cfg=cfg, jira=fake)
    app.call_from_thread = lambda f, *a, **k: None
    app.last_pr_keys = ({"PROJ-1"}, set())
    assert "PROJ-1" in app.build_jql(Section("x", "{mine}"))
