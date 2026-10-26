import asyncio

from jira_dash import app as app_module
from jira_dash import theme as theme_module
from jira_dash.app import JiraDash

PAPER = "background = #ebe5dc\nforeground = #1d1a17\ncursor-color = #774738\nselection-background = #dacbb4\n"
PAPER += "palette = 1=#a0463c\npalette = 4=#3d5f8f\n"
NIGHT = "background = #221f1b\nforeground = #b7b0a5\n"


def setup_ghostty(tmp_path, monkeypatch, theme_line="theme = Paper"):
    config = tmp_path / "config"
    themes = tmp_path / "themes"
    themes.mkdir()
    (themes / "Paper").write_text(PAPER)
    (themes / "Night").write_text(NIGHT)
    config.write_text(f"font-size = 14\n{theme_line}\n")
    monkeypatch.setattr(theme_module, "ghostty_config_paths", lambda: [config])
    monkeypatch.setattr(theme_module, "ghostty_theme_dirs", lambda: [themes])
    return config


def test_reads_ghostty_theme_into_textual_theme(tmp_path, monkeypatch):
    setup_ghostty(tmp_path, monkeypatch)
    theme = theme_module.load_ghostty_theme("ghostty")
    assert theme.background == "#EBE5DC"
    assert theme.primary == "#3D5F8F"
    assert theme.accent == "#774738"
    assert theme.dark is False
    assert theme.variables["block-cursor-background"] == "#DACBB4"


def test_dark_background_marks_theme_dark(tmp_path, monkeypatch):
    setup_ghostty(tmp_path, monkeypatch, "theme = Night")
    assert theme_module.load_ghostty_theme("ghostty").dark is True


def test_last_theme_line_wins_and_pairs_are_unsupported(tmp_path):
    config = tmp_path / "config"
    config.write_text("theme = Paper\n# theme = Ignored\ntheme = Night\n")
    assert theme_module.ghostty_theme_name([config]) == "Night"
    config.write_text("theme = light:Paper,dark:Night\n")
    assert theme_module.ghostty_theme_name([config]) is None


def test_missing_ghostty_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(theme_module, "ghostty_config_paths", lambda: [tmp_path / "nope"])
    assert theme_module.load_ghostty_theme("ghostty") is None


def test_app_follows_ghostty_theme_changes(cfg, fake, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    config = setup_ghostty(tmp_path, monkeypatch)

    async def scenario():
        app = JiraDash(cfg={**cfg, "theme": "ghostty"}, jira=fake)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.2)
            assert app.current_theme.background == "#EBE5DC"
            config.write_text("theme = Night\n")
            app._ghostty_sig = None
            app.sync_ghostty_theme()
            await pilot.pause(0.1)
            assert app.current_theme.background == "#221F1B"

    asyncio.run(scenario())


def test_app_uses_fallback_without_ghostty(cfg, fake, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])
    monkeypatch.setattr(theme_module, "ghostty_config_paths", lambda: [tmp_path / "nope"])

    async def scenario():
        app = JiraDash(cfg={**cfg, "theme": "ghostty", "theme_fallback": "nord"}, jira=fake)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.2)
            assert app.theme == "nord"

    asyncio.run(scenario())


def test_app_accepts_builtin_theme_name(cfg, fake, monkeypatch):
    monkeypatch.setattr(app_module, "prs_for_issue", lambda key: [])

    async def scenario():
        app = JiraDash(cfg={**cfg, "theme": "gruvbox"}, jira=fake)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.2)
            assert app.theme == "gruvbox"

    asyncio.run(scenario())
