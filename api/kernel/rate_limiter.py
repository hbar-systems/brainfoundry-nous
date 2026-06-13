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


class PublicRateLimiter:
    """Per-IP + brain-wide-daily rate limiter for the public chat surface.

    Two stacked checks, both Redis-backed and fail-closed:

    1. **Per-IP / per-window** — PUBLIC_RATE_LIMIT_MAX (default 10) over
       PUBLIC_RATE_LIMIT_WINDOW (default 60s). Catches a single abuser.

    2. **Brain-wide daily cap** — PUBLIC_CHAT_DAILY_MAX (default 0 = unlimited).
       Counts all /v1/public/chat calls regardless of IP, resets at UTC
       midnight. Catches distributed-IP attacks that bypass per-IP rate-limit
       (botnets, IP rotation). Returns 503 with retry-after = seconds-to-UTC-
       midnight when exceeded. Default 0 preserves existing behavior; org
       brains opt in by setting PUBLIC_CHAT_DAILY_MAX in their .env.
    """

    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "")
        self.max_hits = int(os.getenv("PUBLIC_RATE_LIMIT_MAX", "10"))
        self.window = int(os.getenv("PUBLIC_RATE_LIMIT_WINDOW", "60"))
        self.daily_max = int(os.getenv("PUBLIC_CHAT_DAILY_MAX", "0"))
        self._client: Optional[redis.Redis] = None

    def _get_client(self) -> Optional[redis.Redis]:
        if self._client is not None:
            return self._client
        if not self.redis_url:
            return None
        self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    def check(self, ip: str):
        try:
            r = self._get_client()
            if r is None:
                return {"error": "FAILURE"}

            # Per-IP check
            key = f"public_rl:ip:{ip}"
            count = r.incr(key)
            if count == 1:
                r.expire(key, self.window)
            if count > self.max_hits:
                ttl = r.ttl(key)
                return {"error": "RATE_LIMITED", "retry_after": ttl}

            # Brain-wide daily check (only if enabled). Key naturally bins by
            # UTC date so rollover is automatic; TTL set to 25h so the key
            # eventually evicts even if no traffic the next day.
            if self.daily_max > 0:
                from datetime import datetime, timezone
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                daily_key = f"public_rl:daily:{today}"
                daily_count = r.incr(daily_key)
                if daily_count == 1:
                    r.expire(daily_key, 90000)  # 25h
                if daily_count > self.daily_max:
                    # Seconds until UTC midnight — gives operator-tunable
                    # client backoff hint without leaking the exact cap.
                    now = datetime.now(timezone.utc)
                    midnight = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                    retry = int((midnight - now).total_seconds())
                    return {"error": "DAILY_BUDGET_EXCEEDED", "retry_after": retry}

            return None

        except Exception:
            return {"error": "FAILURE"}


class FederationRateLimiter:
    """Per-caller rate + daily cap for the inbound /v1/federation/query surface.

    The public chat limiter keys on IP only — fine for a browser, wrong for a
    federation peer that is *identified*. A peer presents a signed ED25519
    assertion (verified against its pinned pubkey in the introduced-peers
    directory); when that verifies we key the limiter on the peer's brain_id so
    one peer's volume is bounded regardless of how many IPs it calls from.
    Anonymous public calls (no assertion) fall back to an IP key — the same
    floor the public chat surface already enforces.

    Two stacked checks, both Redis-backed and fail-closed:

    1. **Per-caller / per-window** — FEDERATION_RATE_LIMIT_MAX (default 30) over
       FEDERATION_RATE_LIMIT_WINDOW (default 60s).

    2. **Per-caller daily cap** — FEDERATION_DAILY_MAX (default 1000), resets at
       UTC midnight. Set 0 to disable. Catches a peer (or IP) that stays under
       the per-window rate but hammers all day.

    `check(key)` takes a pre-computed caller key ("peer:<brain_id>" or
    "ip:<addr>") so the endpoint owns the identify-the-caller decision.
    """

    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "")
        self.max_hits = int(os.getenv("FEDERATION_RATE_LIMIT_MAX", "30"))
        self.window = int(os.getenv("FEDERATION_RATE_LIMIT_WINDOW", "60"))
        self.daily_max = int(os.getenv("FEDERATION_DAILY_MAX", "1000"))
        self._client: Optional[redis.Redis] = None

    def _get_client(self) -> Optional[redis.Redis]:
        if self._client is not None:
            return self._client
        if not self.redis_url:
            return None
        self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    def check(self, key: str):
        """key is "peer:<brain_id>" or "ip:<addr>". Returns None if allowed, or
        a dict {error, retry_after} when a cap is exceeded / the backend fails."""
        try:
            r = self._get_client()
            if r is None:
                return {"error": "FAILURE"}

            # Per-caller window
            wkey = f"fed_rl:{key}"
            count = r.incr(wkey)
            if count == 1:
                r.expire(wkey, self.window)
            if count > self.max_hits:
                ttl = r.ttl(wkey)
                return {"error": "RATE_LIMITED", "retry_after": ttl}

            # Per-caller daily cap (binned by UTC date so rollover is automatic)
            if self.daily_max > 0:
                from datetime import datetime, timezone
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                dkey = f"fed_rl:daily:{today}:{key}"
                daily_count = r.incr(dkey)
                if daily_count == 1:
                    r.expire(dkey, 90000)  # 25h
                if daily_count > self.daily_max:
                    now = datetime.now(timezone.utc)
                    midnight = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                    retry = int((midnight - now).total_seconds())
                    return {"error": "DAILY_CAP_EXCEEDED", "retry_after": retry}

            return None

        except Exception:
            return {"error": "FAILURE"}
