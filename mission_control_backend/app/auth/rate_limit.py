import time
from collections import defaultdict
from threading import Lock
from fastapi import HTTPException, Request


class InMemoryRateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def check(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            # Prune old entries
            self._attempts[key] = [t for t in self._attempts[key] if t > cutoff]

            if len(self._attempts[key]) >= self.max_attempts:
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please try again later.",
                )

            self._attempts[key].append(now)


login_limiter = InMemoryRateLimiter(max_attempts=5, window_seconds=300)
refresh_limiter = InMemoryRateLimiter(max_attempts=10, window_seconds=60)
