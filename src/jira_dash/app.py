from __future__ import annotations

import os
import re
import shlex
import subprocess
import threading
import webbrowser
from dataclasses import dataclass

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Input, OptionList, Static, Tab, Tabs, TextArea
from textual.widgets.option_list import Option

from . import clipboard, gh
from .adf import adf_to_text, mention_tokens
from .config import DEFAULT_COLUMNS, Section, load_config, sections_from
from .gh import GhError, gh_dash_config_for, my_pr_keys, prs_for_issue
from .jira import BUILTIN_FIELDS, Issue, Jira, render_value
from .preview import PreviewCache
from .state import SeenStore


@dataclass
class Column:
    field: str
    title: str
    width: int | None = None

    @property
    def builtin(self) -> bool:
        return self.field.lower() in BUILTIN_FIELDS


def parse_columns(spec: list | None) -> list[Column]:
    cols: list[Column] = []
    for item in spec or DEFAULT_COLUMNS:
        if isinstance(item, str):
            cols.append(Column(item, item.title() if item.lower() in BUILTIN_FIELDS else item))
        else:
            fld = str(item.get("field", ""))
            cols.append(Column(fld, str(item.get("title") or fld), item.get("width")))
    if not cols or cols[0].field.lower() != "key":
        cols.insert(0, Column("key", "Key"))
    return cols


def split_order_by(jql: str) -> tuple[str, str]:
    m = re.search(r"\s+ORDER\s+BY\s+", jql, flags=re.IGNORECASE)
    if not m:
        return jql.strip(), ""
    return jql[: m.start()].strip(), jql[m.end() :].strip()


def human_size(size: int) -> str:
    return f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"


class Picker(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(self, title: str, options: list[tuple[str, str]]) -> None:
        super().__init__()
        self.title_text = title
        self.options = options

    def compose(self) -> ComposeResult:
        with Vertical(id="picker"):
            yield Static(self.title_text, classes="modal-title")
            yield OptionList(*[Option(label, id=oid) for oid, label in self.options])

    @on(OptionList.OptionSelected)
    def _selected(self, ev: OptionList.OptionSelected) -> None:
        self.dismiss(ev.option.id)


class CommentEditor(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel"), Binding("ctrl+s", "submit", "Send")]

    def __init__(self, key: str) -> None:
        super().__init__()
        self.key = key

    def compose(self) -> ComposeResult:
        with Vertical(id="editor"):
            yield Static(f"Comment on {self.key}  (ctrl+s send, esc cancel)", classes="modal-title")
            yield TextArea(id="body")

    def action_submit(self) -> None:
        body = self.query_one("#body", TextArea).text.strip()
        self.dismiss(body or None)


class JiraDash(App):
    TITLE = "jira-dash"
    CSS = """
    Screen { layout: vertical; }
    #main { height: 1fr; }
    #list { width: 55%; border-left: solid $primary-darken-2; }
    #list:focus-within { border-left: thick $accent; }
    #preview { width: 45%; border-left: solid $primary-darken-2; padding: 0 1; }
    #preview:focus { border-left: thick $accent; }
    #status { height: 1; color: $text-muted; padding: 0 1; }
    #search { display: none; }
    #search.visible { display: block; }
    DataTable { height: 1fr; }
    .modal-title { text-style: bold; padding: 0 1; height: 1; }
    #picker { width: 60; height: auto; max-height: 80%; border: thick $primary; background: $surface; }
    #editor { width: 90%; height: 60%; border: thick $primary; background: $surface; }
    #editor TextArea { height: 1fr; }
    Picker, CommentEditor { align: center middle; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("l,right,tab,shift+right", "next_section", "Next tab", show=False),
        Binding("h,left,shift+tab,shift+left", "prev_section", "Prev tab", show=False),
        Binding("j,down", "cursor_down", show=False),
        Binding("k,up", "cursor_up", show=False),
        Binding("shift+down,pagedown", "page_down", show=False),
        Binding("shift+up,pageup", "page_up", show=False),
        Binding("enter,v", "view", "List/Read"),
        Binding("c", "comment", "Comment"),
        Binding("m", "move", "Move"),
        Binding("a", "assign_me", "Assign me"),
        Binding("u", "unassign", "Unassign"),
        Binding("o", "open", "Browser"),
        Binding("x", "attachments", "Attachments"),
        Binding("g", "gh_dash", "PRs in gh-dash"),
        Binding("y", "yank", "Copy key"),
        Binding("slash", "search", "Filter"),
        Binding("escape", "clear_search", show=False),
    ]

    def __init__(self, cfg: dict | None = None, jira: Jira | None = None, focus_issue: str | None = None) -> None:
        super().__init__()
        self.cfg = cfg if cfg is not None else load_config()
        self.jira = jira or Jira(self.cfg)
        self.sections: list[Section] = sections_from(self.cfg)
        self.seen = SeenStore()
        gh.set_budget(int(self.cfg.get("gh_per_minute", 15) or 15))
        self._pr_timer = None
        if focus_issue:
            self.sections.insert(0, Section(focus_issue, f"key = {focus_issue}", hide_done=False))
        self._tab_ids: dict[Section, str] = {}
        self._by_tab: dict[str, Section] = {}
        for sec in self.sections:
            self._register_tab(sec)
        self.issues: dict[Section, list[Issue]] = {}
        self._loading: set[Section] = set()
        self._load_seq: dict[Section, int] = {}
        self._resolve_lock = threading.Lock()
        self.sprint: tuple[int, str] | None = None
        self.pr_keys: tuple[set[str], set[str]] | None = None
        self.last_pr_keys: tuple[set[str], set[str]] | None = None
        self.attachments: dict[str, list[dict]] = {}
        self.preview_cache = PreviewCache(int(self.cfg.get("cache_seconds") or 120))
        self._preview_timer = None
        self._auto_key: str | None = None
        self._column_keys: list = []
        self._ticks = 0
        self.filter_text = ""
        self.custom_commands: list[dict] = []
        for kb in self.cfg.get("keybindings") or []:
            if not kb.get("key") or not kb.get("command"):
                continue
            self.custom_commands.append(kb)
            self.bind(
                str(kb["key"]), f"custom({len(self.custom_commands) - 1})", description=kb.get("name") or "custom"
            )

    def _register_tab(self, sec: Section) -> str:
        tab_id = f"sec{len(self._tab_ids)}"
        self._tab_ids[sec] = tab_id
        self._by_tab[tab_id] = sec
        return tab_id

    def tab_for(self, sec: Section) -> Tab:
        return self.tabs.query_one(f"#{self._tab_ids[sec]}", Tab)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Tabs(*[Tab(s.name, id=self._tab_ids[s]) for s in self.sections], id="tabs")
        with Horizontal(id="main"):
            with Vertical(id="list"):
                yield Input(placeholder="filter this section (esc to clear)", id="search")
                yield DataTable(id="table", cursor_type="row", zebra_stripes=True)
            with VerticalScroll(id="preview"):
                yield Static("Select an issue", id="detail")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.table = self.query_one(DataTable)
        self.detail = self.query_one("#detail", Static)
        self.preview = self.query_one("#preview", VerticalScroll)
        self.status_bar = self.query_one("#status", Static)
        self.search_input = self.query_one("#search", Input)
        self.tabs = self.query_one(Tabs)
        self._table_columns: list[Column] | None = None
        if self.cfg.get("import_favourite_filters"):
            self.load_favourites()
        if self.sections:
            self.load_section(self.current_section)
            for sec in self.sections:
                if sec.activity and sec is not self.current_section:
                    self.load_section(sec)
        else:
            self.set_status("no sections in config")
        every = int(self.cfg.get("refresh_seconds") or 0)
        if every > 0:
            self.set_interval(every, self.auto_refresh)

    def on_unmount(self) -> None:
        close = getattr(self.jira, "close", None)
        if close:
            close()

    def auto_refresh(self) -> None:
        if isinstance(self.screen, ModalScreen) or not self.sections:
            return
        self._ticks += 1
        if self._ticks % int(self.cfg.get("pr_refresh_every", 5) or 1) == 0:
            self.pr_keys = None
        current = self.current_section
        self.load_section(current)
        for sec in self.sections:
            if sec.activity and sec is not current:
                self.load_section(sec)

    @property
    def current_section(self) -> Section:
        sec = self._by_tab.get(self.tabs.active or "")
        return sec if sec is not None else self.sections[0]

    @property
    def current_index(self) -> int:
        return self.sections.index(self.current_section)

    def set_status(self, msg: str) -> None:
        self.status_bar.update(msg)

    def selected_key(self) -> str | None:
        if self.table.row_count == 0:
            return None
        row = self.table.get_row_at(self.table.cursor_row)
        return str(row[0].plain if isinstance(row[0], Text) else row[0]).lstrip("● ")

    @work(thread=True, exclusive=True, group="favs")
    def load_favourites(self) -> None:
        try:
            favs = self.jira.favourite_filters()
        except Exception as e:
            self.call_from_thread(self.set_status, f"favourite filters: {e}")
            return
        self.call_from_thread(self._add_sections, favs)

    def _add_sections(self, new: list[Section]) -> None:
        new = [s for s in new if not any(x.jql == s.jql for x in self.sections)]
        activity = next((s for s in self.sections if s.activity), None)
        for s in new:
            tab = Tab(s.name, id=self._register_tab(s))
            if activity is not None:
                self.sections.insert(self.sections.index(activity), s)
                self.tabs.add_tab(tab, before=self._tab_ids[activity])
            else:
                self.sections.append(s)
                self.tabs.add_tab(tab)

    def load_section(self, sec: Section) -> None:
        self._loading.add(sec)
        self._load_seq[sec] = self._load_seq.get(sec, 0) + 1
        show_status = sec is self.current_section
        self._load_section(sec, self._load_seq[sec], self.columns_for(sec), show_status)

    @work(thread=True, group="search")
    def _load_section(self, sec: Section, seq: int, cols: list[Column], show_status: bool) -> None:
        if show_status:
            self.call_from_thread(self.set_status, f"loading {sec.name}…")
        try:
            jql = self.build_jql(sec)
            extra = {}
            builtin: list[str] = []
            for col in cols:
                if col.builtin:
                    fid = BUILTIN_FIELDS.get(col.field.lower())
                    if fid:
                        builtin.append(fid)
                    continue
                fid = self.jira.field_id(col.field)
                if fid:
                    extra[col.field] = fid
                else:
                    self.call_from_thread(self.notify, f"unknown field '{col.field}'", severity="warning")
            issues = self.jira.search(jql, int(self.cfg.get("page_size") or 50), extra, builtin)
            order = [x.lower() for x in self.cfg.get("status_order") or []]
            if order:
                rank = {name: i for i, name in enumerate(order)}
                issues.sort(key=lambda i: (i.done, rank.get(i.status.lower(), len(order))))
        except Exception as e:
            self._loading.discard(sec)
            self.call_from_thread(self.set_status, f"error: {e}")
            return
        self.call_from_thread(self._store_result, sec, seq, issues)

    def _store_result(self, sec: Section, seq: int, issues: list[Issue]) -> None:
        if seq != self._load_seq.get(sec):
            return
        self.issues[sec] = issues
        self._loading.discard(sec)
        self._loaded(sec)

    def build_jql(self, sec: Section) -> str:
        jql = sec.jql
        if "{project}" in jql:
            jql = jql.replace("{project}", self.jira.project or "")
        if "{sprint}" in jql:
            with self._resolve_lock:
                if not self.sprint:
                    self.sprint = self.jira.active_sprint(str(self.cfg.get("team") or ""))
                    self.call_from_thread(setattr, self, "sub_title", self.sprint[1])
            jql = jql.replace("{sprint}", str(self.sprint[0]))
        if "{mine}" in jql or "{mine_authored}" in jql:
            with self._resolve_lock:
                if self.pr_keys is None and self.cfg.get("pr_reviews"):
                    try:
                        self.pr_keys = my_pr_keys(int(self.cfg.get("pr_days") or 30))
                        self.last_pr_keys = self.pr_keys
                    except GhError as e:
                        self.pr_keys = self.last_pr_keys
                        self.call_from_thread(self.notify, str(e), severity="warning", timeout=6)
            authored, reviews = self.pr_keys or (set(), set())

            def clause(keys: set[str]) -> str:
                base = "assignee = currentUser()"
                return f"({base} OR key in ({', '.join(sorted(keys))}))" if keys else f"({base})"

            jql = jql.replace("{mine}", clause(authored | reviews)).replace("{mine_authored}", clause(authored))
        hidden = self.cfg.get("hide_statuses") or []
        if hidden and sec.hide_done:
            where, order = split_order_by(jql)
            quoted = ", ".join(f'"{h}"' for h in hidden)
            jql = f"({where}) AND status not in ({quoted})" + (f" ORDER BY {order}" if order else "")
        return jql

    def _loaded(self, sec: Section) -> None:
        issues = self.issues.get(sec, [])
        self.preview_cache.evict_stale({i.key: i.updated_at for i in issues})
        if sec.activity:
            self._update_unread_badge(sec)
            self.seen.prune_older_than(int(self.cfg.get("activity_days") or 3))
        if sec is self.current_section:
            self.render_table()

    def _update_unread_badge(self, sec: Section) -> None:
        unread = sum(1 for i in self.issues.get(sec, []) if self.seen.is_unread(i.key, i.updated_at))
        self.tab_for(sec).label = f"{sec.name} ({unread})" if unread else sec.name

    def columns_for(self, sec: Section) -> list[Column]:
        return parse_columns(sec.columns or self.cfg.get("columns"))

    def is_unread(self, i: Issue) -> bool:
        return self.current_section.activity and self.seen.is_unread(i.key, i.updated_at)

    def cell(self, col: Column, i: Issue) -> Text:
        dim = "dim" if i.done else ""
        f = col.field.lower()
        if f == "key":
            if self.is_unread(i):
                return Text("● ", style="bold yellow").append(i.key, style="bold cyan")
            return Text(i.key, style="dim cyan" if i.done else "bold cyan")
        if f == "type":
            return Text(i.issuetype, style=dim)
        if f == "priority":
            return Text(i.priority, style=dim or self._priority_style(i.priority))
        if f == "status":
            return Text(i.status, style="dim green" if i.done else self._status_style(i.status))
        if f == "assignee":
            return Text(i.assignee.split(" ")[0], style=dim)
        if f == "summary":
            return Text(i.summary, style="bold" if self.is_unread(i) else dim)
        if f == "updated":
            return Text(i.updated, style=dim)
        if f == "project":
            return Text(i.key.split("-")[0], style=dim)
        raw = i.raw.get("fields", {}) if f in BUILTIN_FIELDS else None
        if raw is not None:
            return Text(render_value(raw.get(BUILTIN_FIELDS[f])), style=dim)
        return Text(i.extra.get(col.field, ""), style=dim)

    def render_table(self) -> None:
        table = self.table
        previous = self.selected_key()
        cols = self.columns_for(self.current_section)
        if cols != self._table_columns:
            table.clear(columns=True)
            self._column_keys = [table.add_column(c.title, width=c.width) for c in cols]
            self._table_columns = cols
        else:
            table.clear()
        issues = self.issues.get(self.current_section, [])
        ft = self.filter_text.lower()
        shown = 0
        keep_row = 0
        for i in issues:
            hay = f"{i.key} {i.summary} {i.status} {i.assignee} {i.issuetype} {' '.join(i.extra.values())}".lower()
            if ft and ft not in hay:
                continue
            table.add_row(*(self.cell(c, i) for c in cols), key=i.key)
            if i.key == previous:
                keep_row = shown
            shown += 1
        self.set_status(f"{self.current_section.name}: {shown}/{len(issues)}   {self.current_section.jql}")
        if shown:
            table.move_cursor(row=keep_row)
            self._auto_key = self.selected_key()
            if self._auto_key != previous or previous not in self.preview_cache:
                self.select_card(self._auto_key)
        else:
            self.detail.update("No issues")

    @staticmethod
    def _priority_style(priority: str) -> str:
        p = priority.lower()
        if p in ("highest", "critical", "blocker"):
            return "bold red"
        if p == "high":
            return "red"
        if p in ("low", "lowest"):
            return "dim"
        return ""

    @staticmethod
    def _status_style(status: str) -> str:
        s = status.lower()
        if "done" in s or "closed" in s or "released" in s:
            return "green"
        if "review" in s or "qa" in s or "test" in s:
            return "yellow"
        if "progress" in s or "dev" in s:
            return "blue"
        return ""

    @on(Tabs.TabActivated)
    def _tab_changed(self) -> None:
        if not self.is_mounted or not hasattr(self, "table"):
            return
        self.filter_text = ""
        self.search_input.value = ""
        sec = self.current_section
        if sec in self.issues:
            self.render_table()
        elif sec not in self._loading:
            self.load_section(sec)

    @on(DataTable.RowSelected)
    def _row_selected(self) -> None:
        self.action_view()

    @on(DataTable.RowHighlighted)
    def _row_highlighted(self, ev: DataTable.RowHighlighted) -> None:
        if ev.row_key is None or not ev.row_key.value:
            return
        self.select_card(str(ev.row_key.value))

    def select_card(self, key: str) -> None:
        if self._preview_timer:
            self._preview_timer.stop()
        if self._pr_timer:
            self._pr_timer.stop()
        mark = key != self._auto_key
        cols = self.columns_for(self.current_section)
        if key in self.preview_cache:
            self.show_preview(key, mark, cols)
        else:
            self._preview_timer = self.set_timer(0.25, lambda: self.show_preview(key, mark, cols))
        cached = self.preview_cache.get(key)
        if self.cfg.get("pr_reviews") and (cached is None or cached.prs is None):
            dwell = float(self.cfg.get("pr_dwell_seconds", 1.5) or 0)
            self._pr_timer = self.set_timer(dwell, lambda: self.fetch_prs(key))

    def fetch_prs(self, key: str) -> None:
        if self.selected_key() == key:
            self._fetch_prs(key)

    @work(thread=True, exclusive=True, group="prs")
    def _fetch_prs(self, key: str) -> None:
        try:
            prs = prs_for_issue(key)
        except GhError as e:
            self.call_from_thread(self.set_status, str(e))
            return
        self.call_from_thread(self._prs_loaded, key, prs)

    def _prs_loaded(self, key: str, prs: list[dict]) -> None:
        cached = self.preview_cache.set_prs(key, prs)
        if cached and self.selected_key() == key:
            self.detail.update(
                self.render_issue(key, cached.data, cached.comments, prs, self.columns_for(self.current_section))
            )

    @work(thread=True, exclusive=True, group="preview")
    def show_preview(self, key: str | None, mark: bool = True, cols: list[Column] | None = None) -> None:
        if not key:
            return
        cached = self.preview_cache.fresh(key)
        if cached is None:
            try:
                data = self.jira.issue(key)
                comments = self.jira.comments(key)
            except Exception as e:
                self.call_from_thread(self.detail.update, f"error: {e}")
                return
            cached = self.preview_cache.put(key, data, comments)
        self.call_from_thread(
            self.detail.update, self.render_issue(key, cached.data, cached.comments, cached.prs, cols or [])
        )
        if mark:
            self.call_from_thread(self.mark_seen, key, cached.updated_at)

    def mark_seen(self, key: str, updated_at: str) -> None:
        if not self.seen.mark(key, updated_at):
            return
        for sec in self.sections:
            if not sec.activity:
                continue
            for i in self.issues.get(sec, []):
                if i.key == key:
                    i.updated_at = updated_at
                    if sec is self.current_section:
                        self._refresh_row(i)
            self._update_unread_badge(sec)

    def _refresh_row(self, issue: Issue) -> None:
        cols = self._table_columns or []
        for col, ckey in zip(cols, self._column_keys, strict=False):
            if col.field.lower() in ("key", "summary"):
                try:
                    self.table.update_cell(issue.key, ckey, self.cell(col, issue))
                except Exception:
                    return

    def render_issue(
        self, key: str, data: dict, comments: list[dict], prs: list[dict] | None, cols: list[Column]
    ) -> Text:
        f = data["fields"]
        t = Text()
        t.append(f"{key}  ", style="bold cyan").append(f.get("summary", ""), style="bold").append("\n\n")

        def kv(label: str, value: str) -> None:
            t.append(f"{label} ", style="dim").append(f"{value}   ")

        kv("Type", (f.get("issuetype") or {}).get("name", ""))
        kv("Status", (f.get("status") or {}).get("name", ""))
        kv("Priority", (f.get("priority") or {}).get("name", ""))
        t.append("\n")
        kv("Assignee", (f.get("assignee") or {}).get("displayName", "Unassigned"))
        kv("Reporter", (f.get("reporter") or {}).get("displayName", ""))
        t.append("\n")
        kv("Created", (f.get("created") or "")[:10])
        kv("Updated", (f.get("updated") or "")[:10])
        t.append("\n")
        parent = f.get("parent")
        if parent:
            kv("Parent", f"{parent.get('key')} {parent.get('fields', {}).get('summary', '')}")
            t.append("\n")
        labels = f.get("labels") or []
        if labels:
            kv("Labels", ", ".join(labels))
            t.append("\n")
        shown_custom = False
        for col in cols:
            if col.builtin:
                continue
            fid = self.jira.field_id(col.field)
            value = render_value(f.get(fid)) if fid else ""
            if value:
                kv(col.title, value)
                shown_custom = True
        if shown_custom:
            t.append("\n")
        atts = f.get("attachment") or []
        self.attachments[key] = atts
        if atts:
            t.append("\nAttachments (x to open)\n", style="bold")
            for a in atts:
                who = (a.get("author") or {}).get("displayName", "")
                t.append(f"  {a.get('filename')}", style="cyan")
                t.append(f"  {human_size(a.get('size', 0))}  {who}\n", style="dim")
        if prs:
            t.append("\nPull requests (g for gh-dash)\n", style="bold")
            for pr in prs:
                state = "draft" if pr.get("isDraft") else pr.get("state", "").lower()
                style = {"open": "green", "merged": "magenta", "closed": "red", "draft": "dim"}.get(state, "")
                repo = (pr.get("repository") or {}).get("name", "")
                t.append(f"  {state:<6}", style=style).append(f" {repo}#{pr['number']} ", style="dim")
                t.append(pr["title"] + "\n")
        t.append("\nDescription\n\n", style="bold")
        t.append((adf_to_text(f.get("description")).strip() or "none") + "\n\n")
        if comments:
            t.append("Comments\n\n", style="bold")
            for c in comments:
                who = (c.get("author") or {}).get("displayName", "?")
                when = (c.get("created") or "")[:16].replace("T", " ")
                t.append(who, style="yellow").append(f"  {when}\n", style="dim")
                t.append(adf_to_text(c.get("body")).strip() + "\n\n")
        return t

    def action_refresh(self) -> None:
        self.sprint = None
        self.pr_keys = None
        self.preview_cache.clear()
        if self.sections:
            self.load_section(self.current_section)

    def action_next_section(self) -> None:
        self.tabs.action_next_tab()

    def action_prev_section(self) -> None:
        self.tabs.action_previous_tab()

    def _reading(self) -> bool:
        return self.focused is self.preview

    def action_cursor_down(self) -> None:
        if self._reading():
            self.preview.scroll_down(animate=False)
        else:
            self._auto_key = None
            self.table.action_cursor_down()

    def action_cursor_up(self) -> None:
        if self._reading():
            self.preview.scroll_up(animate=False)
        else:
            self._auto_key = None
            self.table.action_cursor_up()

    def action_page_down(self) -> None:
        if self._reading():
            self.preview.scroll_page_down(animate=False)
        else:
            self._auto_key = None
            self.table.action_page_down()

    def action_page_up(self) -> None:
        if self._reading():
            self.preview.scroll_page_up(animate=False)
        else:
            self._auto_key = None
            self.table.action_page_up()

    def action_view(self) -> None:
        if self._reading():
            self.table.focus()
            return
        key = self.selected_key()
        if key:
            self._auto_key = None
            cached = self.preview_cache.get(key)
            if cached:
                self.mark_seen(key, cached.updated_at)
            else:
                self.show_preview(key, True, self.columns_for(self.current_section))
        self.preview.scroll_home(animate=False)
        self.preview.focus()

    def action_open(self) -> None:
        key = self.selected_key()
        if key:
            webbrowser.open(self.jira.browse_url(key))

    def action_attachments(self) -> None:
        key = self.selected_key()
        atts = self.attachments.get(key or "", [])
        if not key or not atts:
            self.set_status("no attachments")
            return

        def done(url: str | None) -> None:
            if url:
                webbrowser.open(url)

        self.push_screen(Picker(f"Attachments on {key}", [(a["content"], a["filename"]) for a in atts]), done)

    def action_gh_dash(self) -> None:
        key = self.selected_key()
        if not key:
            return
        cfg = None
        try:
            cfg = gh_dash_config_for(key)
            with self.suspend():
                subprocess.run(["gh", "dash", "--config", cfg], check=False)
        except FileNotFoundError:
            self.notify("gh is not installed", severity="error")
            return
        except Exception as e:
            self.notify(f"gh-dash: {e}", severity="error")
            return
        finally:
            if cfg:
                try:
                    os.unlink(cfg)
                except OSError:
                    pass
        self.preview_cache.pop(key)
        self.screen.refresh(repaint=True, layout=True)
        self.table.focus()
        self.select_card(key)

    def command_context(self, key: str) -> dict[str, str]:
        issue = next((i for i in self.issues.get(self.current_section, []) if i.key == key), None)
        ctx = {
            "key": key,
            "summary": issue.summary if issue else "",
            "status": issue.status if issue else "",
            "assignee": issue.assignee if issue else "",
            "type": issue.issuetype if issue else "",
            "url": self.jira.browse_url(key),
            "jira_server": self.jira.server,
            "project": key.split("-")[0],
        }
        for col in self.columns_for(self.current_section):
            if not col.builtin:
                slug = re.sub(r"[^a-z0-9]+", "_", col.title.lower()).strip("_")
                ctx.setdefault(slug, issue.extra.get(col.field, "") if issue else "")
        return ctx

    def action_custom(self, index: int) -> None:
        key = self.selected_key()
        if not key or index >= len(self.custom_commands):
            return
        kb = self.custom_commands[index]
        ctx = {k: shlex.quote(v) for k, v in self.command_context(key).items()}
        try:
            command = kb["command"].format(**ctx)
        except KeyError as e:
            self.notify(f"keybinding {kb['key']}: unknown field {e}", severity="error")
            return
        cwd = os.path.expanduser(kb["cwd"]) if kb.get("cwd") else None
        if kb.get("suspend", True) is False:
            subprocess.Popen(
                command,
                shell=True,
                cwd=cwd,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.set_status(f"started: {kb.get('name') or command[:40]}")
            return
        with self.suspend():
            subprocess.run(command, shell=True, cwd=cwd, check=False)
        self.preview_cache.pop(key)
        self.screen.refresh(repaint=True, layout=True)
        self.table.focus()
        self.load_section(self.current_section)

    def action_yank(self) -> None:
        key = self.selected_key()
        if key:
            self.set_status(f"copied {key}" if clipboard.copy(key) else "no clipboard tool found")

    def action_search(self) -> None:
        self.search_input.add_class("visible")
        self.search_input.focus()

    def action_clear_search(self) -> None:
        if self._reading():
            self.table.focus()
            return
        self.search_input.value = ""
        self.search_input.remove_class("visible")
        self.filter_text = ""
        self.render_table()
        self.table.focus()

    @on(Input.Changed, "#search")
    def _search_changed(self, ev: Input.Changed) -> None:
        self.filter_text = ev.value
        self.render_table()

    @on(Input.Submitted, "#search")
    def _search_done(self) -> None:
        self.table.focus()

    def action_comment(self) -> None:
        key = self.selected_key()
        if not key:
            return

        def done(body: str | None) -> None:
            if body:
                self.resolve_mentions(key, body)

        self.push_screen(CommentEditor(key), done)

    @work(thread=True)
    def resolve_mentions(self, key: str, body: str) -> None:
        resolved: dict[str, tuple[str, str]] = {}
        ambiguous: list[tuple[str, list[tuple[str, str]]]] = []
        for name in mention_tokens(body):
            try:
                users = self.jira.search_users(name)
            except Exception as e:
                self.call_from_thread(self.notify, f"user search failed: {e}", severity="warning")
                users = []
            exact = [u for u in users if u[1].lower() == name.lower()]
            prefix = [u for u in users if any(w.startswith(name.lower()) for w in u[1].lower().split())]
            if len(exact) == 1 or len(prefix) == 1:
                resolved[name] = (exact or prefix)[0]
            elif users:
                ambiguous.append((name, users))
            else:
                self.call_from_thread(self.notify, f"no Jira user matches @{name}, left as text", severity="warning")
        self.call_from_thread(self._pick_mentions, key, body, resolved, ambiguous)

    def _pick_mentions(self, key, body, resolved, ambiguous) -> None:
        if not ambiguous:
            self.post_comment(key, body, resolved)
            return
        name, users = ambiguous[0]

        def done(account_id: str | None) -> None:
            if account_id:
                resolved[name] = next(u for u in users if u[0] == account_id)
            self._pick_mentions(key, body, resolved, ambiguous[1:])

        self.push_screen(Picker(f"Who is @{name}?", [(u[0], u[1]) for u in users]), done)

    @work(thread=True)
    def post_comment(self, key: str, body: str, mentions: dict[str, tuple[str, str]] | None = None) -> None:
        try:
            self.jira.add_comment(key, body, mentions)
            self.preview_cache.pop(key)
            self.call_from_thread(self.set_status, f"commented on {key}")
            self.call_from_thread(self.select_card, key)
        except Exception as e:
            self.call_from_thread(self.set_status, f"comment failed: {e}")

    def action_move(self) -> None:
        key = self.selected_key()
        if key:
            self.fetch_transitions(key)

    @work(thread=True)
    def fetch_transitions(self, key: str) -> None:
        try:
            trs = self.jira.transitions(key)
        except Exception as e:
            self.call_from_thread(self.set_status, f"transitions: {e}")
            return
        opts = [(t["id"], f"{t['name']}  →  {(t.get('to') or {}).get('name', '')}") for t in trs]

        def open_picker() -> None:
            def done(tid: str | None) -> None:
                if tid:
                    self.do_transition(key, tid)

            self.push_screen(Picker(f"Move {key}", opts), done)

        self.call_from_thread(open_picker)

    @work(thread=True)
    def do_transition(self, key: str, tid: str) -> None:
        try:
            self.jira.transition(key, tid)
            self.preview_cache.pop(key)
            self.call_from_thread(self.set_status, f"moved {key}")
            self.call_from_thread(lambda: self.load_section(self.current_section))
        except Exception as e:
            self.call_from_thread(self.set_status, f"move failed: {e}")

    def action_assign_me(self) -> None:
        key = self.selected_key()
        if key:
            self.do_assign(key, True)

    def action_unassign(self) -> None:
        key = self.selected_key()
        if key:
            self.do_assign(key, False)

    @work(thread=True)
    def do_assign(self, key: str, me: bool) -> None:
        try:
            self.jira.assign(key, self.jira.myself() if me else None)
            self.preview_cache.pop(key)
            self.call_from_thread(self.set_status, f"{'assigned' if me else 'unassigned'} {key}")
            self.call_from_thread(lambda: self.load_section(self.current_section))
        except Exception as e:
            self.call_from_thread(self.set_status, f"assign failed: {e}")
