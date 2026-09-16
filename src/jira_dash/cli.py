from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import CONFIG_PATH, ConfigError
from .gh import ISSUE_KEY_RE


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="jira-dash", description="gh-dash style terminal dashboard for Jira")
    parser.add_argument("issue", nargs="?", help="open with a tab focused on this issue key, e.g. PROJ-123")
    parser.add_argument("--config", action="store_true", help="print the config file path and exit")
    parser.add_argument("--version", action="version", version=f"jira-dash {__version__}")
    args = parser.parse_args(argv)

    if args.config:
        print(CONFIG_PATH)
        return

    focus = None
    if args.issue:
        focus = args.issue.upper()
        if not ISSUE_KEY_RE.fullmatch(focus):
            parser.error(f"'{args.issue}' does not look like an issue key")

    from .app import JiraDash
    from .jira import JiraConfigError

    try:
        app = JiraDash(focus_issue=focus)
    except (JiraConfigError, ConfigError) as e:
        sys.exit(f"jira-dash: {e}\nconfig: {CONFIG_PATH}")
    app.run()


if __name__ == "__main__":
    main()
