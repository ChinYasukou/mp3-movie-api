"""Verify the published cache contract and its diagnostics."""

import logging

from src.cache import MovieCache


def test_cache_keys_expiration_and_logs(caplog):
    cache = MovieCache()
    with caplog.at_level(logging.DEBUG, logger="src.cache"):
        assert cache.get(100) is None
        response = {"data": [], "total_rows": 0}
        cache.set(100, response)
        assert cache.get(100) == response
        assert cache.get(1) is None
        assert cache.make_key(100) == "movies:limit:100"
        assert 89 <= cache.client.ttl(cache.make_key(100)) <= 90
        cache.invalidate()
        assert cache.get(100) is None

    messages = [record.getMessage() for record in caplog.records]
    assert "Cache MISS: movies:limit:100" in messages
    assert "Cache HIT: movies:limit:100" in messages
    assert "Invalidated movie cache" in messages
