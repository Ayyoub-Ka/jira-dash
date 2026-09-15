from __future__ import annotations

import pytest

from jira_dash.config import Section
from jira_dash.jira import Issue


def PARA(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


class FakeJira:
    def __init__(self) -> None:
        self.server = "https://example.atlassian.net"
        self.project = "PROJ"
        self.board_id = 1
        self.calls: list[tuple] = []
        self.issues = [
            Issue(
                key=f"PROJ-{i}",
                summary=f"Summary {i}",
                status="Done" if i == 0 else "In Progress",
                issuetype="Bug",
                priority="High",
                assignee="Ann Bee",
                updated="2026-01-01",
                raw={},
                done=(i == 0),
            )
            for i in range(4)
        ]

    def myself(self) -> str:
        return "acct"

    def field_id(self, name: str) -> str | None:
        return {"server(s)": "customfield_10090"}.get(name.lower())

    def search(self, jql: str, limit: int, extra_fields: dict[str, str] | None = None) -> list[Issue]:
        self.calls.append(("search", jql, extra_fields or {}))
        out = []
        for i in self.issues:
            i.extra = {name: f"srv-{i.key[-1]}" for name in (extra_fields or {})}
            i.raw = {"fields": {"reporter": {"displayName": "Rae"}, "labels": ["x", "y"]}}
            out.append(i)
        return out

    def issue(self, key: str) -> dict:
        self.calls.append(("issue", key))
        return {
            "fields": {
                "summary": "S",
                "issuetype": {"name": "Bug"},
                "status": {"name": "In Progress"},
                "priority": None,
                "assignee": None,
                "reporter": {"displayName": "R"},
                "created": "2026-01-01",
                "updated": "2026-01-02",
                "labels": ["a"],
                "attachment": [
                    {"filename": "shot.png", "size": 2048, "content": "https://x/att/1", "author": {"displayName": "R"}}
                ],
                "description": {
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "hello "},
                                {"type": "text", "text": "bold", "marks": [{"type": "strong"}]},
                            ],
                        },
                        {"type": "bulletList", "content": [{"type": "listItem", "content": [PARA("item")]}]},
                    ],
                },
            }
        }

    def comments(self, key: str) -> list[dict]:
        body = {"type": "doc", "content": [PARA("nice")]}
        return [{"author": {"displayName": "Bob"}, "created": "2026-01-01T10:00", "body": body}]

    def add_comment(self, key: str, text: str) -> None:
        self.calls.append(("comment", key, text))

    def transitions(self, key: str) -> list[dict]:
        return [{"id": "1", "name": "Review", "to": {"name": "In Review"}}]

    def transition(self, key: str, tid: str) -> None:
        self.calls.append(("transition", key, tid))

    def assign(self, key: str, account_id: str | None) -> None:
        self.calls.append(("assign", key, account_id))

    def active_sprint(self, team: str) -> tuple[int, str]:
        return 42, "Sprint 42"

    def favourite_filters(self) -> list[Section]:
        return [Section("Fav", "filter = 9")]

    def browse_url(self, key: str) -> str:
        return f"{self.server}/browse/{key}"


@pytest.fixture
def cfg() -> dict:
    return {
        "team": "",
        "pr_reviews": False,
        "refresh_seconds": 0,
        "cache_seconds": 120,
        "page_size": 50,
        "hide_statuses": ["Done"],
        "status_order": ["In Progress", "Done"],
        "sections": [
            {"name": "Mine", "jql": "{mine} ORDER BY updated DESC"},
            {"name": "Sprint", "jql": "sprint = {sprint} ORDER BY Rank", "hide_done": False},
            {"name": "Project", "jql": "project = {project}"},
        ],
    }


@pytest.fixture
def fake() -> FakeJira:
    return FakeJira()
