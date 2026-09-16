# Changelog

## 0.1.0 (2026-09-16)

First release.

- JQL tabs with `{sprint}`, `{mine}`, `{mine_authored}` and `{project}` placeholders
- Reading pane with description, comments, attachments and pull requests; `@mentions` in comments
- Comment, transition, assign and unassign from the list
- Per-tab columns including custom fields by display name
- Activity tab with unread tracking, on by default
- gh-dash hand-off (`g`) and custom keybindings that run shell commands with card fields
- GitHub search throttling: dwell-based PR fetch, per-minute budget, rate-limit back-off
- Connection from env vars, the config file, or an existing jira-cli setup; `token_command` for keychains
