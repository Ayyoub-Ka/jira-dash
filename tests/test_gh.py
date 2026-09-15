import subprocess

import pytest
import yaml

from jira_dash import gh


class Result:
    def __init__(self, code, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def test_pr_keys_take_first_key_per_title(monkeypatch):
    monkeypatch.setattr(gh, "_backoff_until", 0.0)
    titles = "PROJ-1 fix (relates PROJ-2)\nno key here\nOTHER-9 thing\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Result(0, titles))
    assert gh._pr_title_keys("--author=@me") == {"PROJ-1", "OTHER-9"}


def test_rate_limit_sets_backoff(monkeypatch):
    monkeypatch.setattr(gh, "_backoff_until", 0.0)
    err = "HTTP 403: You have exceeded a secondary rate limit"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Result(1, "", err))
    with pytest.raises(gh.GhError, match="rate limited"):
        gh.gh_search("x")
    assert gh._backoff_until > 0
    with pytest.raises(gh.GhError, match="retrying later"):
        gh.gh_search("x")


def test_missing_gh(monkeypatch):
    monkeypatch.setattr(gh, "_backoff_until", 0.0)

    def missing(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(gh.GhError, match="not installed"):
        gh.gh_search("x")


def test_gh_dash_config_for(monkeypatch, tmp_path):
    base = tmp_path / "config.yml"
    base.write_text("keybindings:\n  prs:\n    - key: J\n      command: echo\n")
    monkeypatch.setattr(gh, "GH_DASH_CONFIG", base)
    path = gh.gh_dash_config_for("PROJ-5")
    out = yaml.safe_load(open(path))
    assert out["prSections"][0]["filters"] == "is:open PROJ-5 in:title"
    assert out["defaults"]["view"] == "prs"
    assert out["smartFilteringAtLaunch"] is False
    assert out["keybindings"]["prs"][0]["key"] == "J"
