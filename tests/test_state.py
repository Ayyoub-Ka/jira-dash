from datetime import date

from jira_dash.preview import PreviewCache
from jira_dash.state import SeenStore


def test_seen_store_marks_and_prunes_by_age(tmp_path):
    store = SeenStore(tmp_path / "seen.json")
    assert store.is_unread("A-1", "2026-09-15T10:00:00.000+0000")
    assert store.mark("A-1", "2026-09-15T10:00:00.000+0000")
    assert not store.mark("A-1", "2026-09-15T10:00:00.000+0000")
    assert not store.is_unread("A-1", "2026-09-15T10:00:00.000+0000")
    store.mark("OLD-1", "2026-09-10T00:00:00.000+0000")
    store.prune_older_than(3, today=date(2026, 9, 16))
    reloaded = SeenStore(tmp_path / "seen.json")
    assert "OLD-1" not in reloaded.seen
    assert "A-1" in reloaded.seen


def test_preview_cache_pending_prs_and_stale_eviction():
    cache = PreviewCache(ttl_seconds=60)
    assert cache.set_prs("A-1", [{"number": 1}]) is None
    p = cache.put("A-1", {"fields": {"updated": "t1"}}, [])
    assert p.prs == [{"number": 1}]
    assert cache.fresh("A-1") is p
    assert cache.evict_stale({"A-1": "t1"}) == set()
    assert cache.evict_stale({"A-1": "t2"}) == {"A-1"}
    assert "A-1" not in cache


def test_preview_cache_keeps_prs_across_refetch():
    cache = PreviewCache(ttl_seconds=60)
    cache.put("A-1", {"fields": {"updated": "t1"}}, [])
    cache.set_prs("A-1", [{"number": 7}])
    again = cache.put("A-1", {"fields": {"updated": "t2"}}, [])
    assert again.prs == [{"number": 7}]
