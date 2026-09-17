# Changelog

## 0.1.1 (2026-09-17)

- New `{review_requested}` placeholder; the default config separates Mine (`{mine_authored}`) from a To review tab
- Keybindings can run in a new terminal window with `new_terminal: true`; the terminal app is detected or set with `terminal` / `terminal_command`
- A slow preview fetch no longer overwrites the card you moved to
- The PR list survives the preview cache refetch
- Literal braces in keybinding commands show an error instead of crashing; double them as `{{ }}`
- `r` also drops other tabs' cached results so they reload when revisited
- Issue search follows `nextPageToken` and stops on an empty page
- Arrow and page keys mark Activity cards read like `j`/`k`
- Unknown config keys are warned about and ignored instead of refusing to start; invalid YAML and bad shapes still fail with a clear message
- 401/403 responses include a hint about login, token, and the scoped-token gateway URL
- `@name.` at the end of a sentence no longer captures the dot
- Background tab errors show as a toast instead of overwriting the status bar
- Switching tabs hides the filter box

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
