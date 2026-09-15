from __future__ import annotations

import os
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


class Jira:
    def __init__(self, cfg: dict) -> None:
        conn = resolve_connection(cfg)
        self.server: str = conn["server"]
        self.project: str = conn["project"]
        self.board_id = conn["board_id"]
        self.http = httpx.Client(base_url=self.server + "/rest/api/3", auth=(conn["login"], conn["token"]), timeout=30)
        self.account_id: str | None = None

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

    def search(self, jql: str, limit: int) -> list[Issue]:
        fields = "summary,status,issuetype,priority,assignee,updated"
        r = self._check(self.http.get("/search/jql", params={"jql": jql, "maxResults": limit, "fields": fields}))
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
                    raw=it,
                    done=(status.get("statusCategory") or {}).get("key") == "done",
                )
            )
        return out

    def issue(self, key: str) -> dict:
        return self._check(self.http.get(f"/issue/{key}", params={"fields": "*all"})).json()

    def comments(self, key: str) -> list[dict]:
        r = self._check(self.http.get(f"/issue/{key}/comment", params={"orderBy": "-created", "maxResults": 20}))
        return r.json().get("comments", [])

    def add_comment(self, key: str, text: str) -> None:
        self._check(self.http.post(f"/issue/{key}/comment", json={"body": text_to_adf(text)}))

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
        sprints = self._check(self.http.get(url, params={"state": "active"})).json().get("values", [])
        match = [s for s in sprints if team.lower() in s["name"].lower()] if team else sprints
        if not match:
            names = ", ".join(s["name"] for s in sprints) or "none"
            raise RuntimeError(f"no active sprint matching '{team}' (active: {names})")
        s = max(match, key=lambda x: x.get("startDate", ""))
        return s["id"], s["name"]

    def favourite_filters(self) -> list[Section]:
        r = self._check(self.http.get("/filter/favourite"))
        return [Section(name=f["name"], jql=f"filter = {f['id']}") for f in r.json()]

    def browse_url(self, key: str) -> str:
        return f"{self.server}/browse/{key}"
