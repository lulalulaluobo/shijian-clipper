from collections import deque
from time import monotonic


class RateLimiter:
    def __init__(self, clock=monotonic, max_buckets: int = 4096) -> None:
        self.clock = clock
        self.max_buckets = max_buckets
        self.buckets: dict[str, deque[float]] = {}

    def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        now = self.clock()
        bucket = self.buckets.get(key)
        if bucket is None:
            if len(self.buckets) >= self.max_buckets:
                self.buckets.pop(next(iter(self.buckets)))
            bucket = deque()
            self.buckets[key] = bucket
        while bucket and bucket[0] <= now - window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True
