"""Small in-process limiter for costly AI endpoints; deploy Redis-backed limits for multi-replica API."""
import time
from collections import defaultdict, deque
from threading import Lock


class RateLimitExceeded(RuntimeError):
    def __init__(self, retry_after: int):
        self.retry_after = max(1, retry_after)
        super().__init__("AI conversion rate limit exceeded")


class SlidingWindowRateLimiter:
    def __init__(self):
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, limit: int, window_seconds: int = 60) -> None:
        if limit <= 0:
            return
        now = time.monotonic()
        with self._lock:
            requests = self._requests[key]
            while requests and requests[0] <= now - window_seconds:
                requests.popleft()
            if len(requests) >= limit:
                raise RateLimitExceeded(int(window_seconds - (now - requests[0])) + 1)
            requests.append(now)

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()


ai_conversion_limiter = SlidingWindowRateLimiter()
