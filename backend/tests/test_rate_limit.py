from backend.app.rate_limit import RateLimiter


def test_blocks_the_next_request_after_the_window_limit():
    now = [0.0]
    limiter = RateLimiter(clock=lambda: now[0])

    assert limiter.allow("user-a", limit=2, window_seconds=60)
    assert limiter.allow("user-a", limit=2, window_seconds=60)
    assert not limiter.allow("user-a", limit=2, window_seconds=60)

    now[0] = 61.0
    assert limiter.allow("user-a", limit=2, window_seconds=60)
