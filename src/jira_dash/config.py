from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

XDG_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
CONFIG_PATH = Path(os.environ.get("JIRA_DASH_CONFIG", XDG_CONFIG / "jira-dash/config.yml"))
JIRA_CLI_CONFIG = XDG_CONFIG / ".jira/.config.yml"
GH_DASH_CONFIG = XDG_CONFIG / "gh-dash/config.yml"
STATE_PATH = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "jira-dash/seen.json"

ACTIVITY_JQL = (
    "(assignee = currentUser() OR reporter = currentUser() OR watcher = currentUser() OR {mine_authored})"
    " AND updated >= -{activity_days}d ORDER BY updated DESC"
)

DEFAULT_CONFIG = """\
# jira-dash configuration. Full reference: https://github.com/Ayyoub-Ka/jira-dash#configuration
#
# Connection. Every key is optional: env vars JIRA_SERVER / JIRA_LOGIN / JIRA_API_TOKEN win,
# then this block, then jira-cli's ~/.config/.jira/.config.yml if you have it.
jira:
  # server: https://your-site.atlassian.net
  # login: you@example.com
  # token_command: security find-generic-password -a "$USER" -s jira-api-token -w
  # project: PROJ
  # board_id: 1          # scrum board used to resolve {sprint}

# {sprint} resolves to the active sprint on board_id whose name contains `team` (any active sprint when empty)
team: ""

# {mine} = assignee = currentUser() OR key in (cards named in the title of my GitHub PRs:
#   PRs I authored plus open PRs where my review is requested). {mine_authored} leaves out
#   the review requests, which are often team-wide and pull in other teams' cards.
# Needs the `gh` CLI logged in. Set pr_reviews: false to disable all GitHub lookups.
pr_reviews: true
pr_days: 30            # include PRs I authored that were updated in the last N days
pr_refresh_every: 5    # re-query my PR keys every N tab refreshes (GitHub search is rate limited)
gh_per_minute: 15      # hard cap on GitHub searches per minute; beyond it PR lists are skipped
pr_dwell_seconds: 1.5  # fetch a card's PR list only after resting on it this long

refresh_seconds: 180   # auto-refresh the current tab; 0 disables
cache_seconds: 120     # card previews are cached this long
page_size: 50
import_favourite_filters: false   # add every starred Jira filter as a tab

# Activity tab (last tab): cards you are involved in that changed recently; unread ones are marked
# until you open them. Set activity_tab: false to remove it, activity_jql to change the query.
activity_tab: true
activity_days: 3

# Appended to every tab as `AND status not in (...)`. Add `hide_done: false` to a tab to keep them.
hide_statuses: [Done, Closed]

# Cards are sorted by this list (board column order). Unknown statuses go last. Empty = server order.
status_order: []

# Columns, global default and per-tab override. Built-ins: key type priority status assignee
# reporter summary updated created labels project. Anything else is a custom field, by display
# name or customfield_NNNNN id. Object form allows a title and width: {field: "Environment", title: Env, width: 14}
# columns: [key, type, priority, status, assignee, summary, updated]

# Custom keys, gh-dash style. The command runs in your shell with the TUI suspended;
# `suspend: false` launches it detached instead (e.g. to open a new terminal window).
# Fields: {key} {summary} {status} {assignee} {type} {url} {jira_server} {project}, plus every
# custom column of the current tab by its lower-cased title (e.g. {environment}). All shell-quoted.
# keybindings:
#   - key: C
#     name: Claude
#     command: claude "Look at Jira card {key} and propose a plan"
#     cwd: ~/code/my-repo
#   - key: b
#     name: branch
#     command: git switch -c {key}

# Each tab is a JQL query. Placeholders: {sprint} {mine} {project}
sections:
  - name: Mine
    jql: "{mine} AND statusCategory != Done ORDER BY updated DESC"
  - name: Sprint
    jql: project = {project} AND sprint in openSprints() ORDER BY Rank
  - name: Review
    jql: project = {project} AND status ~ Review ORDER BY updated DESC
  - name: Done
    jql: project = {project} AND statusCategory = Done AND updated >= -14d ORDER BY updated DESC
    hide_done: false
    columns: [key, status, summary, assignee, updated]
"""


DEFAULT_COLUMNS = ["key", "type", "priority", "status", "assignee", "summary", "updated"]


@dataclass(eq=False)
class Section:
    name: str
    jql: str
    hide_done: bool = True
    columns: list | None = None
    activity: bool = False


def load_config(path: Path = CONFIG_PATH) -> dict:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG)
    return yaml.safe_load(path.read_text()) or {}


def load_jira_cli_config(path: Path = JIRA_CLI_CONFIG) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


class ConfigError(RuntimeError):
    pass


SECTION_KEYS = {"name", "jql", "hide_done", "columns"}


def sections_from(cfg: dict) -> list[Section]:
    sections: list[Section] = []
    for n, raw in enumerate(cfg.get("sections") or [], start=1):
        if not isinstance(raw, dict):
            raise ConfigError(f"sections[{n}] must be a mapping with name and jql")
        label = raw.get("name") or f"#{n}"
        unknown = set(raw) - SECTION_KEYS
        if unknown:
            allowed = ", ".join(sorted(SECTION_KEYS))
            raise ConfigError(f"section '{label}': unknown key(s) {', '.join(sorted(unknown))}; allowed: {allowed}")
        if not raw.get("name") or not raw.get("jql"):
            raise ConfigError(f"section '{label}': name and jql are required")
        sections.append(Section(**raw))
    if cfg.get("activity_tab", True):
        days = int(cfg.get("activity_days") or 3)
        jql = str(cfg.get("activity_jql") or ACTIVITY_JQL).replace("{activity_days}", str(days))
        sections.append(Section("Activity", jql, hide_done=False, activity=True))
    return sections
