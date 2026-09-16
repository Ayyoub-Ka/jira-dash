# jira-dash

A [gh-dash](https://github.com/dlvhdr/gh-dash) style terminal dashboard for Jira Cloud.

Tabs are JQL queries. Move through cards with vim keys, read the full description and
comments on the right, comment, move, assign, open attachments, and jump to the card's
pull requests in gh-dash. Built with [Textual](https://textual.textualize.io).

```
┌ Mine ─ Sprint ─ Review ─ Done ────────────────────────────────────────────────────┐
│ Key       Type   Priority  Status         Assignee  Summary        │ PROJ-123    │
│ PROJ-123  Bug    High      In Progress    Ann       Login fails    │ Login fails │
│ PROJ-118  Story  Medium    Code Review    Bob       Add export     │             │
│ PROJ-101  Task   Low       QA             -         Bump deps      │ Type Bug    │
│                                                                    │ Status ...  │
│                                                                    │ Pull reqs   │
│                                                                    │  open #42   │
│                                                                    │ Description │
└────────────────────────────────────────────────────────────────────┴─────────────┘
 q Quit  r Refresh  enter List/Read  c Comment  m Move  a Assign  o Browser  g gh-dash
```

## Install

```bash
uv tool install git+https://github.com/Ayyoub-Ka/jira-dash
# or
pipx install git+https://github.com/Ayyoub-Ka/jira-dash
```

Upgrade later with `uv tool upgrade jira-dash` or `pipx upgrade jira-dash`. Pin a release with
`git+https://github.com/Ayyoub-Ka/jira-dash@v0.1.0`.

Requires Python 3.11+. The GitHub features need the [`gh`](https://cli.github.com) CLI logged in;
`g` also needs [gh-dash](https://github.com/dlvhdr/gh-dash). Both are optional.

## Connect to Jira

jira-dash reads the connection from the first place that has it:

1. Environment: `JIRA_SERVER`, `JIRA_LOGIN`, `JIRA_API_TOKEN`
2. The `jira:` block in `~/.config/jira-dash/config.yml`
3. [jira-cli](https://github.com/ankitpokhrel/jira-cli)'s `~/.config/.jira/.config.yml`, if you already use it

So with jira-cli set up, `jira-dash` works with no configuration. Without it:

```yaml
jira:
  server: https://your-site.atlassian.net
  login: you@example.com
  project: PROJ
  board_id: 1                       # scrum board, used for {sprint}
  token_command: security find-generic-password -a "$USER" -s jira-api-token -w
```

`token_command` runs a shell command and uses its output as the token, so the token stays in a
password manager or keychain. `JIRA_API_TOKEN` in the environment takes precedence when set.

Create a token at https://id.atlassian.com/manage-profile/security/api-tokens. Use the classic
"Create API token" button. Tokens created "with scopes" only work through Atlassian's gateway URL:
set `server` to `https://api.atlassian.com/ex/jira/<cloudId>`, where `<cloudId>` comes from
`https://your-site.atlassian.net/_edge/tenant_info`.

## Configuration

`jira-dash --config` prints the config path. The file is created with commented defaults on first run.
See [config.example.yml](config.example.yml) for a fuller example with a team sprint and a kanban board.

### Sections

Each entry under `sections` becomes a tab. `jql` is any JQL. `hide_done: false` keeps the
statuses listed in `hide_statuses` for that tab only.

```yaml
sections:
  - name: Mine
    jql: "{mine} AND statusCategory != Done ORDER BY updated DESC"
  - name: Sprint
    jql: sprint = {sprint} ORDER BY Rank
    hide_done: false
  - name: Kanban
    jql: filter = 12345 AND status in ("To Do", "In Progress") ORDER BY Rank
```

### Placeholders

| Placeholder | Expands to |
|---|---|
| `{project}` | `jira.project` from the config, or jira-cli's default project |
| `{sprint}` | id of the active sprint on `board_id` whose name contains `team`. Useful when several teams share one board and `openSprints()` mixes them. Re-resolved on `r`, so it follows sprint rollover. |
| `{mine}` | `(assignee = currentUser() OR key in (...))` where the keys come from the titles of your GitHub PRs: PRs you authored updated in the last `pr_days` days, and open PRs where your review is requested. For teams that track ownership by PR rather than Jira assignee. |
| `{mine_authored}` | same without the review requests, which are often team-wide and drag in other teams' cards. The Activity tab uses this. |

### Other keys

| Key | Default | Meaning |
|---|---|---|
| `team` | `""` | substring matched against active sprint names for `{sprint}` |
| `hide_statuses` | `[Done, Closed]` | appended to every tab as `AND status not in (...)` |
| `status_order` | `[]` | sort cards by this list, e.g. your board columns. Done cards always go last and are dimmed. |
| `pr_reviews` | `true` | enable GitHub lookups (`{mine}`, PR list in the preview) |
| `pr_days` | `30` | look-back for PRs you authored |
| `pr_refresh_every` | `5` | re-query your PR keys every N tab refreshes |
| `gh_per_minute` | `15` | hard cap on GitHub searches per minute |
| `pr_dwell_seconds` | `1.5` | rest time on a card before its PR list is fetched |
| `refresh_seconds` | `180` | auto-refresh the current tab, keeping the cursor. `0` disables |
| `cache_seconds` | `120` | how long card previews are cached |
| `page_size` | `50` | max cards per tab |
| `import_favourite_filters` | `false` | add every starred Jira filter as a tab |

### Activity tab

The last tab, on by default, lists cards you are involved in (assignee, reporter, watcher, or PRs you
authored) that changed in the last `activity_days` days. Cards updated since you last opened them are
marked with a dot and counted in the tab title; moving onto one or opening it marks it read. The
tab refreshes on the timer even while you work elsewhere, so the count stays current. The read state lives in
`~/.local/state/jira-dash/seen.json`. Set `activity_tab: false` to remove the tab, or `activity_jql`
to change the query. Jira Cloud has no public API for its bell notifications, so this is built
from JQL instead.

### Columns

Pick the columns globally or per tab. Built-ins: `key` `type` `priority` `status` `assignee` `reporter`
`summary` `updated` `created` `labels` `project`. Anything else is a custom field, looked up by its
display name (or given as `customfield_NNNNN`). The object form sets a title and width.

```yaml
columns: [key, type, priority, status, assignee, summary, updated]
sections:
  - name: Support
    jql: project = SUP AND statusCategory != Done ORDER BY Rank
    columns:
      - key
      - status
      - {field: "Environment", title: Env, width: 14}
      - summary
```

`key` is always first. The `/` filter also matches custom column values.

### Custom keybindings

Like gh-dash, you can bind keys to shell commands. The TUI is suspended while the command runs,
so interactive programs work. Fields are filled from the selected card and shell-quoted for you.

```yaml
keybindings:
  - key: C
    name: Claude
    command: claude "Read Jira card {key} ({url}) and propose an implementation plan"
    cwd: ~/code/my-repo
  - key: b
    name: branch
    command: git switch -c {key}
```

Fields: `{key}` `{summary}` `{status}` `{assignee}` `{type}` `{url}` `{jira_server}` `{project}`,
plus every custom column of the current tab by its lower-cased title, so a column titled
`Environment` is available as `{environment}`. Values are shell-quoted.

Add `suspend: false` to launch the command detached instead of pausing the TUI, for example to
open a console in a new terminal window:

```yaml
  - key: T
    name: console
    suspend: false
    command: open -na Ghostty --args -e zsh -ic 'ssh {environment}'
```

Avoid keys the app already uses (see below). The current tab reloads when a suspended command exits.
Literal braces in a command must be doubled: `awk '{{print $1}}'`.

GitHub's search API allows 30 calls a minute plus a stricter burst limit. jira-dash fetches a card's
PR list only after you rest on it for `pr_dwell_seconds` (1.5), caps itself at `gh_per_minute` (15)
searches, and pauses GitHub lookups for five minutes on a rate-limit response. The last known
`{mine}` keys are kept in the meantime. Jira calls: one search per visible tab refresh, two per
newly opened card, cached for `cache_seconds`.

## Keys

| Key | Action |
|---|---|
| `h` `l` `←` `→` `tab` `shift+←` `shift+→` | previous / next tab |
| `j` `k` `↑` `↓` | move in the list, or scroll the reading pane when it has focus |
| `shift+↑` `shift+↓` `PgUp` `PgDn` | page through the list or the reading pane |
| `enter` `v` | toggle focus between list and reading pane |
| `esc` | back to the list, or clear the filter |
| `/` | filter the current tab (key, summary, status, assignee, type) |
| `c` | comment (`ctrl+s` sends). `@name` or `@"Full Name"` mentions a Jira user; ambiguous names open a picker |
| `m` | move: pick a workflow transition |
| `a` `u` | assign to me / unassign |
| `o` | open the card in the browser |
| `x` | pick an attachment and open it in the browser |
| `g` | open gh-dash filtered on this card's PRs, `q` returns |
| `y` | copy the key |
| `r` | refresh everything |
| `q` | quit |

`jira-dash PROJ-123` starts with an extra first tab focused on that card.

## gh-dash integration

`g` suspends jira-dash and starts gh-dash with your own config plus two PR sections for the card
(`open`, `all`). For the other direction, add keybindings to `~/.config/gh-dash/config.yml`:

```yaml
keybindings:
  prs:
    - key: J
      name: jira-dash card
      command: >
        k=$(printf '%s\n%s\n' '{{.HeadRefName}}' "$(gh pr view {{.PrNumber}} --repo {{.RepoName}} --json title -q .title)"
        | grep -oE '\b[A-Z][A-Z0-9]+-[0-9]+\b' | head -1);
        if [ -n "$k" ]; then jira-dash "$k"; else echo "no Jira key in branch or title"; read -r _; fi
    - key: B
      name: open jira card in browser
      command: >
        k=$(printf '%s\n' '{{.HeadRefName}}' | grep -oE '\b[A-Z][A-Z0-9]+-[0-9]+\b' | head -1);
        [ -n "$k" ] && open "https://your-site.atlassian.net/browse/$k"
```

Both read the issue key from the branch name or PR title, so name branches `PROJ-123-something`
or start PR titles with the key.

## Relationship to jira-cli

jira-dash is a dashboard, not a replacement for [jira-cli](https://github.com/ankitpokhrel/jira-cli).
It reuses jira-cli's config when present and leaves creating issues, sprints, epics and
scripting to `jira`. Use both.

## Releasing

Bump `version` in `pyproject.toml`, add a section to `CHANGELOG.md`, then tag and push:

```bash
git tag -a v0.2.0 -m "v0.2.0" && git push origin v0.2.0
```

The release workflow tests, checks the tag matches the version, builds, and creates a GitHub
release with the wheel and sdist attached. The project is not published to PyPI.

## Development

```bash
git clone https://github.com/Ayyoub-Ka/jira-dash && cd jira-dash
uv sync --group dev
uv run pytest
uv run jira-dash
```

The tests drive the app headless with Textual's `Pilot` against a fake Jira, so they need no network.

## License

MIT
