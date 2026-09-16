import httpx
import pytest

from jira_dash import jira


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(jira, "load_jira_cli_config", lambda: {})
    monkeypatch.setenv("JIRA_API_TOKEN", "t")

    def make(handler):
        c = jira.Jira({"jira": {"server": "https://x.atlassian.net", "login": "me", "board_id": 2}})
        c.http = httpx.Client(base_url="https://x.atlassian.net/rest/api/3", transport=httpx.MockTransport(handler))
        return c

    return make


def test_check_reports_jira_error_messages_and_auth_hint(client):
    c = client(lambda req: httpx.Response(400, json={"errorMessages": ["bad jql"]}))
    with pytest.raises(RuntimeError, match="400: bad jql"):
        c.search("x", 5)
    c = client(lambda req: httpx.Response(401, text=""))
    with pytest.raises(RuntimeError, match="401: check JIRA_LOGIN"):
        c.myself()


def test_active_sprint_uses_agile_api_and_picks_team(client):
    seen = []

    def handler(req):
        seen.append(str(req.url))
        return httpx.Response(
            200,
            json={
                "values": [
                    {"id": 1, "name": "S9 - Other", "state": "active", "startDate": "2026-09-01"},
                    {"id": 2, "name": "S9 - Core", "state": "active", "startDate": "2026-09-02"},
                ]
            },
        )

    c = client(handler)
    assert c.active_sprint("core") == (2, "S9 - Core")
    assert seen[0].startswith("https://x.atlassian.net/rest/agile/1.0/board/2/sprint")


def test_search_parses_issue_fields(client):
    issue = {
        "key": "P-1",
        "fields": {
            "summary": "s",
            "status": {"name": "Done", "statusCategory": {"key": "done"}},
            "issuetype": {"name": "Bug"},
            "priority": {"name": "High"},
            "assignee": None,
            "updated": "2026-09-16T10:00:00.000+0000",
            "customfield_1": [{"value": "prod"}],
        },
    }
    c = client(lambda req: httpx.Response(200, json={"issues": [issue], "isLast": True}))
    [i] = c.search("x", 5, {"Env": "customfield_1"}, ["labels"])
    assert (i.key, i.status, i.assignee, i.done, i.updated, i.extra) == (
        "P-1",
        "Done",
        "Unassigned",
        True,
        "2026-09-16",
        {"Env": "prod"},
    )
