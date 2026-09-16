from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field

import httpx

from .adf import text_to_adf
from .config import Section, load_jira_cli_config


class JiraConfigError(RuntimeError):
    pass


@dataclass
class Issue:
    key: str
    summary: str
    status: str
    issuetype: str
    priority: str
    assignee: str
    updated: str
    raw: dict = field(repr=False)
    done: bool = False
    extra: dict[str, str] = field(default_factory=dict)
    updated_at: str = ""


BUILTIN_FIELDS = {
    "key": None,
    "type": "issuetype",
    "priority": "priority",
    "status": "status",
    "assignee": "assignee",
    "reporter": "reporter",
    "summary": "summary",
    "updated": "updated",
    "created": "created",
    "labels": "labels",
    "project": None,
}


def render_value(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return ", ".join(render_value(x) for x in v)
    if isinstance(v, dict):
        for k in ("displayName", "value", "name", "key"):
            if v.get(k):
                return str(v[k])
        return ""
    if isinstance(v, str):
        return v[:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}T.*", v) else v
    return str(v)


def resolve_connection(cfg: dict) -> dict:
    block = cfg.get("jira") or {}
    cli = load_jira_cli_config()
    server = os.environ.get("JIRA_SERVER") or block.get("server") or cli.get("server")
    login = os.environ.get("JIRA_LOGIN") or block.get("login") or cli.get("login")
    token = os.environ.get("JIRA_API_TOKEN")
    if not token and block.get("token_command"):
        token = subprocess.run(block["token_command"], shell=True, capture_output=True, text=True).stdout.strip()
    project = block.get("project") or (cli.get("project") or {}).get("key") or ""
    board_id = block.get("board_id") or (cli.get("board") or {}).get("id")
    missing = [n for n, v in (("server", server), ("login", login), ("token", token)) if not v]
    if missing:
        raise JiraConfigError(
            "missing Jira "
            + ", ".join(missing)
            + ". Set JIRA_SERVER / JIRA_LOGIN / JIRA_API_TOKEN, fill the `jira:` block in the config,"
            " or run `jira init`."
        )
    return {"server": server.rstrip("/"), "login": login, "token": token, "project": project, "board_id": board_id}


def pick_sprint(sprints: list[dict], team: str) -> tuple[int, str]:
    match = [s for s in sprints if team.lower() in s.get("name", "").lower()] if team else list(sprints)
    active = [s for s in match if s.get("state") == "active"]
    if active:
        s = max(active, key=lambda x: x.get("startDate", ""))
        return s["id"], s["name"]
    future = [s for s in match if s.get("state") == "future"]
    if future:
        s = min(future, key=lambda x: (x.get("startDate") or "9999", x["id"]))
        return s["id"], f"{s['name']} (not started)"
    names = ", ".join(s["name"] for s in sprints if s.get("state") == "active") or "none"
    raise RuntimeError(f"no active or future sprint matching '{team}' (active: {names})")


class Jira:
    def __init__(self, cfg: dict) -> None:
        conn = resolve_connection(cfg)
        self.server: str = conn["server"]
        self.project: str = conn["project"]
        self.board_id = conn["board_id"]
        self.http = httpx.Client(base_url=self.server + "/rest/api/3", auth=(conn["login"], conn["token"]), timeout=30)
        self.account_id: str | None = None
        self._field_ids: dict[str, str] | None = None

    @staticmethod
    def _check(r: httpx.Response) -> httpx.Response:
        if r.status_code >= 400:
            try:
                body = r.json()
                msg = "; ".join(body.get("errorMessages", [])) or str(body.get("errors", ""))
            except Exception:
                msg = r.text[:200]
            raise RuntimeError(f"{r.status_code}: {msg}")
        return r

    def myself(self) -> str:
        if not self.account_id:
            self.account_id = self._check(self.http.get("/myself")).json()["accountId"]
        return self.account_id

    def field_id(self, name: str) -> str | None:
        if name.startswith("customfield_"):
            return name
        if self._field_ids is None:
            fields = self._check(self.http.get("/field")).json()
            self._field_ids = {f["name"].lower(): f["id"] for f in fields if f.get("custom")}
        return self._field_ids.get(name.lower())

    def search(self, jql: str, limit: int, extra_fields: dict[str, str] | None = None) -> list[Issue]:
        fields = ["summary", "status", "issuetype", "priority", "assignee", "updated"]
        extra_fields = extra_fields or {}
        fields += [fid for fid in extra_fields.values() if fid not in fields]
        params = {"jql": jql, "maxResults": limit, "fields": ",".join(fields)}
        r = self._check(self.http.get("/search/jql", params=params))
        out = []
        for it in r.json().get("issues", []):
            f = it["fields"]
            status = f.get("status") or {}
            out.append(
                Issue(
                    key=it["key"],
                    summary=f.get("summary") or "",
                    status=status.get("name", ""),
                    issuetype=(f.get("issuetype") or {}).get("name", ""),
                    priority=(f.get("priority") or {}).get("name", ""),
                    assignee=(f.get("assignee") or {}).get("displayName", "") or "Unassigned",
                    updated=(f.get("updated") or "")[:10],
                    updated_at=f.get("updated") or "",
                    raw=it,
                    done=(status.get("statusCategory") or {}).get("key") == "done",
                    extra={name: render_value(f.get(fid)) for name, fid in extra_fields.items()},
                )
            )
        return out

    def issue(self, key: str) -> dict:
        return self._check(self.http.get(f"/issue/{key}", params={"fields": "*all"})).json()

    def comments(self, key: str) -> list[dict]:
        r = self._check(self.http.get(f"/issue/{key}/comment", params={"orderBy": "-created", "maxResults": 20}))
        return r.json().get("comments", [])

    def add_comment(self, key: str, text: str, mentions: dict[str, tuple[str, str]] | None = None) -> None:
        self._check(self.http.post(f"/issue/{key}/comment", json={"body": text_to_adf(text, mentions)}))

    def search_users(self, query: str) -> list[tuple[str, str]]:
        r = self._check(self.http.get("/user/search", params={"query": query, "maxResults": 10}))
        return [
            (u["accountId"], u.get("displayName", ""))
            for u in r.json()
            if u.get("accountType", "atlassian") == "atlassian"
        ]

    def transitions(self, key: str) -> list[dict]:
        return self._check(self.http.get(f"/issue/{key}/transitions")).json().get("transitions", [])

    def transition(self, key: str, transition_id: str) -> None:
        self._check(self.http.post(f"/issue/{key}/transitions", json={"transition": {"id": transition_id}}))

    def assign(self, key: str, account_id: str | None) -> None:
        self._check(self.http.put(f"/issue/{key}/assignee", json={"accountId": account_id}))

    def active_sprint(self, team: str) -> tuple[int, str]:
        if not self.board_id:
            raise RuntimeError("{sprint} needs jira.board_id in the config (or a board picked in `jira init`)")
        url = f"{self.server}/rest/agile/1.0/board/{self.board_id}/sprint"
        sprints = self._check(self.http.get(url, params={"state": "active,future"})).json().get("values", [])
        return pick_sprint(sprints, team)

    def favourite_filters(self) -> list[Section]:
        r = self._check(self.http.get("/filter/favourite"))
        return [Section(name=f["name"], jql=f"filter = {f['id']}") for f in r.json()]

    def browse_url(self, key: str) -> str:
        return f"{self.server}/browse/{key}"
