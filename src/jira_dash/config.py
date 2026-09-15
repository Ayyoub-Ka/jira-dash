from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

XDG_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
CONFIG_PATH = Path(os.environ.get("JIRA_DASH_CONFIG", XDG_CONFIG / "jira-dash/config.yml"))
JIRA_CLI_CONFIG = XDG_CONFIG / ".jira/.config.yml"
GH_DASH_CONFIG = XDG_CONFIG / "gh-dash/config.yml"

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

# {mine} = assignee = currentUser() OR key in (cards named in the title of my GitHub PRs).
# Needs the `gh` CLI logged in. Set pr_reviews: false to disable all GitHub lookups.
pr_reviews: true
pr_days: 30            # include PRs I authored that were updated in the last N days
pr_refresh_every: 5    # re-query my PR keys every N tab refreshes (GitHub search is rate limited)

refresh_seconds: 180   # auto-refresh the current tab; 0 disables
cache_seconds: 120     # card previews are cached this long
page_size: 50
import_favourite_filters: false   # add every starred Jira filter as a tab

# Appended to every tab as `AND status not in (...)`. Add `hide_done: false` to a tab to keep them.
hide_statuses: [Done, Closed]

# Cards are sorted by this list (board column order). Unknown statuses go last. Empty = server order.
status_order: []

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
"""


@dataclass
class Section:
    name: str
    jql: str
    hide_done: bool = True


def load_config(path: Path = CONFIG_PATH) -> dict:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG)
    return yaml.safe_load(path.read_text()) or {}


def load_jira_cli_config(path: Path = JIRA_CLI_CONFIG) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def sections_from(cfg: dict) -> list[Section]:
    return [Section(**s) for s in cfg.get("sections") or []]
