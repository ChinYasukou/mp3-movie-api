"""Process-local cache for movie list responses."""

import json

from fakeredis import FakeRedis


class MovieCache:
    def __init__(self):
        self._redis = FakeRedis(decode_responses=True)

    def get(self, limit):
        payload = self._redis.get(f"movies:list:{limit}")
        return json.loads(payload) if payload is not None else None

    def set(self, limit, response):
        self._redis.set(f"movies:list:{limit}", json.dumps(response), ex=60)

    def invalidate(self):
        """Discard every list variant from this dedicated cache."""
        self._redis.flushdb()
