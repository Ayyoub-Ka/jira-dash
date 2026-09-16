from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from collections import deque
from datetime import date, timedelta

import yaml

from .config import GH_DASH_CONFIG

ISSUE_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


class GhError(RuntimeError):
    pass


_backoff_until = 0.0
_calls: deque[float] = deque()
per_minute = 15


def set_budget(n: int) -> None:
    global per_minute
    per_minute = max(1, int(n))


def gh_search(*args: str) -> str:
    global _backoff_until
    if time.monotonic() < _backoff_until:
        raise GhError("gh rate limited, retrying later")
    now = time.monotonic()
    while _calls and now - _calls[0] > 60:
        _calls.popleft()
    if len(_calls) >= per_minute:
        raise GhError(f"gh budget of {per_minute}/min used, PRs not loaded")
    _calls.append(now)
    try:
        r = subprocess.run(["gh", "search", "prs", *args], capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        raise GhError("gh not installed") from None
    except subprocess.TimeoutExpired:
        raise GhError("gh timed out") from None
    if r.returncode != 0:
        lines = (r.stderr or r.stdout).strip().splitlines()
        msg = lines[0] if lines else f"gh exit {r.returncode}"
        if "rate limit" in msg.lower() or "403" in msg:
            _backoff_until = time.monotonic() + 300
            msg = "gh rate limited, pausing PR lookups for 5 min"
        raise GhError(msg)
    return r.stdout


def _pr_title_keys(*args: str) -> set[str]:
    out = gh_search(*args, "--limit=100", "--json", "title", "--jq", ".[].title")
    return {k for line in out.splitlines() for k in ISSUE_KEY_RE.findall(line)[:1]}


def my_pr_keys(days: int) -> set[str]:
    since = (date.today() - timedelta(days=days)).isoformat()
    return _pr_title_keys("--author=@me", f"--updated=>={since}") | _pr_title_keys(
        "--review-requested=@me", "--state=open"
    )


def prs_for_issue(key: str) -> list[dict]:
    out = gh_search(key, "--match=title", "--limit=20", "--json", "number,title,state,url,isDraft,repository,updatedAt")
    return sorted(json.loads(out), key=lambda p: p.get("updatedAt", ""), reverse=True)


def gh_dash_config_for(key: str) -> str:
    base = yaml.safe_load(GH_DASH_CONFIG.read_text()) if GH_DASH_CONFIG.exists() else {}
    base = base or {}
    base["prSections"] = [
        {"title": f"{key} open", "filters": f"is:open {key} in:title"},
        {"title": f"{key} all", "filters": f"{key} in:title"},
    ]
    base.setdefault("defaults", {})["view"] = "prs"
    base["smartFilteringAtLaunch"] = False
    fd, path = tempfile.mkstemp(prefix="jira-dash-", suffix=".yml")
    with os.fdopen(fd, "w") as fh:
        yaml.safe_dump(base, fh)
    return path
