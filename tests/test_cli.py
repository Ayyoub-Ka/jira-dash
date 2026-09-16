import pytest

from jira_dash import cli


def test_config_flag_prints_path(capsys):
    cli.main(["--config"])
    assert str(cli.CONFIG_PATH) in capsys.readouterr().out


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0
    assert "jira-dash" in capsys.readouterr().out


def test_bad_issue_key_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["not a key"])
    assert e.value.code == 2


def test_config_error_exits_with_message(monkeypatch, capsys):
    from jira_dash import app as app_module

    def boom(**kw):
        raise cli.ConfigError("section 'Mine': name and jql are required")

    monkeypatch.setattr(app_module, "JiraDash", boom)
    with pytest.raises(SystemExit) as e:
        cli.main([])
    assert "section 'Mine'" in str(e.value.code)
