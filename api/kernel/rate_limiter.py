import os
import redis
from typing import Optional


class KernelRateLimiter:
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "")
        self.max_hits = int(os.getenv("KERNEL_RATE_LIMIT_MAX", "30"))
        self.window = int(os.getenv("KERNEL_RATE_LIMIT_WINDOW", "60"))
        self._client: Optional[redis.Redis] = None

    def _get_client(self) -> Optional[redis.Redis]:
        if self._client is not None:
            return self._client
        if not self.redis_url:
            return None
        self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    def check(self, client_id: str):
        """
        Returns:
            None if allowed
            dict with { "error": "RATE_LIMITED", "retry_after": int }
            dict with { "error": "FAILURE" } on backend failure
        """
        try:
            r = self._get_client()
            if r is None:
                return {"error": "FAILURE"}

            key = f"kernel_rl:cid:{client_id}"

            count = r.incr(key)
            if count == 1:
                r.expire(key, self.window)

            if count > self.max_hits:
                ttl = r.ttl(key)
                return {"error": "RATE_LIMITED", "retry_after": ttl}

            return None

        except Exception:
            return {"error": "FAILURE"}
