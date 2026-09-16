import pytest
import yaml

from jira_dash import config, jira
from jira_dash.config import DEFAULT_CONFIG, load_config, sections_from
from jira_dash.jira import pick_sprint


def test_default_config_is_valid_yaml_and_written(tmp_path):
    path = tmp_path / "config.yml"
    cfg = load_config(path)
    assert path.exists()
    assert cfg == yaml.safe_load(DEFAULT_CONFIG)
    assert [s.name for s in sections_from(cfg)] == ["Mine", "Sprint", "Review", "Done", "Activity"]
    assert sections_from(cfg)[4].activity and "-3d" in sections_from(cfg)[4].jql
    assert [s.name for s in sections_from({**cfg, "activity_tab": False})] == ["Mine", "Sprint", "Review", "Done"]
    assert sections_from(cfg)[3].hide_done is False


def test_resolve_connection_env_beats_config_beats_jira_cli(monkeypatch, tmp_path):
    cli = tmp_path / "cli.yml"
    cli.write_text("server: https://cli.example\nlogin: cli@x\nproject:\n  key: CLI\nboard:\n  id: 7\n")
    monkeypatch.setattr(config, "JIRA_CLI_CONFIG", cli)
    monkeypatch.setattr(jira, "load_jira_cli_config", lambda: config.load_jira_cli_config(cli))
    monkeypatch.setenv("JIRA_API_TOKEN", "tok")
    monkeypatch.delenv("JIRA_SERVER", raising=False)
    monkeypatch.delenv("JIRA_LOGIN", raising=False)

    conn = jira.resolve_connection({})
    assert conn["server"] == "https://cli.example" and conn["project"] == "CLI" and conn["board_id"] == 7

    conn = jira.resolve_connection({"jira": {"server": "https://cfg.example/", "board_id": 3}})
    assert conn["server"] == "https://cfg.example" and conn["board_id"] == 3 and conn["login"] == "cli@x"

    monkeypatch.setenv("JIRA_SERVER", "https://env.example")
    assert jira.resolve_connection({"jira": {"server": "https://cfg.example"}})["server"] == "https://env.example"


def test_resolve_connection_token_command(monkeypatch):
    monkeypatch.setattr(jira, "load_jira_cli_config", lambda: {})
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    conn = jira.resolve_connection({"jira": {"server": "https://s", "login": "l", "token_command": "echo secret"}})
    assert conn["token"] == "secret"


def test_resolve_connection_missing(monkeypatch):
    monkeypatch.setattr(jira, "load_jira_cli_config", lambda: {})
    for v in ("JIRA_API_TOKEN", "JIRA_SERVER", "JIRA_LOGIN"):
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(jira.JiraConfigError, match="server, login, token"):
        jira.resolve_connection({})


def test_pick_sprint_prefers_active_then_next_future():
    sprints = [
        {"id": 1, "name": "S52 - Tactical", "state": "active", "startDate": "2026-09-01"},
        {"id": 2, "name": "S53 - Strategic", "state": "future"},
        {"id": 3, "name": "S54 - Strategic", "state": "future"},
        {"id": 4, "name": "S52 - Strategic", "state": "active", "startDate": "2026-09-02"},
    ]
    assert pick_sprint(sprints, "strategic") == (4, "S52 - Strategic")
    assert pick_sprint(sprints[:3], "strategic") == (2, "S53 - Strategic (not started)")
    assert pick_sprint(sprints, "") == (4, "S52 - Strategic")
    with pytest.raises(RuntimeError, match="active: S52 - Tactical"):
        pick_sprint(sprints[:1], "strategic")


def test_token_command_failure_is_reported(monkeypatch):
    monkeypatch.setattr(jira, "load_jira_cli_config", lambda: {})
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    with pytest.raises(jira.JiraConfigError, match="token_command failed"):
        jira.resolve_connection(
            {"jira": {"server": "https://s", "login": "l", "token_command": "echo nope >&2; exit 3"}}
        )
