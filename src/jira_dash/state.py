from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .config import STATE_PATH


class SeenStore:
    def __init__(self, path: Path = STATE_PATH) -> None:
        self.path = path
        try:
            self.seen: dict[str, str] = json.loads(path.read_text())
        except (OSError, ValueError):
            self.seen = {}

    def is_unread(self, key: str, updated_at: str) -> bool:
        return bool(updated_at) and self.seen.get(key) != updated_at

    def mark(self, key: str, updated_at: str) -> bool:
        if not updated_at or self.seen.get(key) == updated_at:
            return False
        self.seen[key] = updated_at
        self.save()
        return True

    def prune_older_than(self, days: int) -> None:
        cutoff = (date.today() - timedelta(days=days + 1)).isoformat()
        kept = {k: v for k, v in self.seen.items() if v[:10] >= cutoff}
        if len(kept) != len(self.seen):
            self.seen = kept
            self.save()

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.seen, indent=0, sort_keys=True))
        except OSError:
            pass
