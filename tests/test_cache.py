from app.runtime.cache import ToolResultCache
from app.tools.base import ToolResult


def test_cache_hit_and_miss_stats() -> None:
    cache = ToolResultCache()
    result = ToolResult(ok=True, data={"count": 1})
    assert cache.get("list_classrooms", {}) is None
    cache.put("list_classrooms", {}, result)
    assert cache.get("list_classrooms", {}) is result
    assert cache.stats == {"hits": 1, "misses": 1, "size": 1}


def test_cache_key_is_order_independent() -> None:
    assert ToolResultCache.key("t", {"a": 1, "b": 2}) == ToolResultCache.key(
        "t", {"b": 2, "a": 1}
    )
