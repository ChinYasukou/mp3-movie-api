"""Process-local cache for movie list responses."""

import json
import logging

import fakeredis


logger = logging.getLogger(__name__)


class MovieCache:
    def __init__(self):
        self.client = fakeredis.FakeRedis(decode_responses=True)

    def make_key(self, limit):
        return f"movies:limit:{limit}"

    def get(self, limit):
        """Return the cached response dictionary, or None."""
        key = self.make_key(limit)
        payload = self.client.get(key)
        if payload is None:
            logger.debug("Cache MISS: %s", key)
            return None
        logger.debug("Cache HIT: %s", key)
        return json.loads(payload)

    def set(self, limit, response):
        """Cache the complete movie response for 90 seconds."""
        self.client.set(self.make_key(limit), json.dumps(response), ex=90)

    def invalidate(self):
        """Discard every list variant from this dedicated cache."""
        self.client.flushdb()
        logger.debug("Invalidated movie cache")
