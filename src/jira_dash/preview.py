from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Preview:
    data: dict
    comments: list[dict]
    prs: list[dict] | None = None
    fetched_at: float = field(default_factory=time.monotonic)

    @property
    def updated_at(self) -> str:
        return (self.data.get("fields") or {}).get("updated") or ""


class PreviewCache:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl = ttl_seconds
        self._entries: dict[str, Preview] = {}
        self._pending_prs: dict[str, list[dict]] = {}

    def __contains__(self, key: str) -> bool:
        return key in self._entries

    def get(self, key: str) -> Preview | None:
        return self._entries.get(key)

    def fresh(self, key: str) -> Preview | None:
        p = self._entries.get(key)
        if p and time.monotonic() - p.fetched_at < self.ttl:
            return p
        return None

    def put(self, key: str, data: dict, comments: list[dict]) -> Preview:
        old = self._entries.get(key)
        prs = self._pending_prs.pop(key, None)
        if prs is None and old is not None:
            prs = old.prs
        p = Preview(data, comments, prs)
        self._entries[key] = p
        return p

    def set_prs(self, key: str, prs: list[dict]) -> Preview | None:
        p = self._entries.get(key)
        if p:
            p.prs = prs
        else:
            self._pending_prs[key] = prs
        return p

    def pop(self, key: str) -> None:
        self._entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()
        self._pending_prs.clear()

    def evict_stale(self, updates: dict[str, str]) -> set[str]:
        evicted = set()
        for key, updated_at in updates.items():
            p = self._entries.get(key)
            if p and updated_at and p.updated_at != updated_at:
                self._entries.pop(key)
                evicted.add(key)
        return evicted
