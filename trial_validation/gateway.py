"""
Submission gateway: safely send cleared records to an outside system
(for example the sponsor's safety database or EDC system).

Outside systems fail in 3 common ways:
  1. Random short errors      (HTTP 503 "try again")
  2. Too many requests         (HTTP 429 "slow down")
  3. Full outage for a while   (system is down)

A NAIVE client sends each record once, as fast as it can. Any error = lost submission.

The GATEWAY adds 4 protections:
  - Rate limiter (token bucket): max N calls per second per site, so we don't get 429s
  - Retry with exponential backoff + jitter: on a short error, wait 0.5s, 1s, 2s, 4s... then retry
  - Circuit breaker: after 5 errors in a row, STOP calling for 30s (the system is probably down),
                     then try one call. If it works, continue.
  - Dead-letter queue: records that still fail are kept and retried later, never lost

We use a SIMULATED clock, so a 30-second wait takes 0 real seconds and the test is fast.
"""
import random


class Clock:
    def __init__(self):
        self.t = 0.0

    def sleep(self, s):
        self.t += s


class FlakyAPI:
    """A fake outside system that fails in realistic ways."""

    def __init__(self, clock, seed=1, error_rate=0.08, max_per_sec=20, outage=(40.0, 70.0)):
        self.clock, self.rng = clock, random.Random(seed)
        self.error_rate, self.max_per_sec, self.outage = error_rate, max_per_sec, outage
        self.window_start, self.window_count = 0.0, 0
        self.calls = 0
        self.received = set()

    def submit(self, record_id):
        self.calls += 1
        self.clock.sleep(0.01)                          # each call takes 10 ms
        t = self.clock.t
        if int(t) != int(self.window_start):            # new 1-second window
            self.window_start, self.window_count = t, 0
        self.window_count += 1
        if self.outage[0] <= t < self.outage[1]:
            return 503                                  # system down
        if self.window_count > self.max_per_sec:
            return 429                                  # too many requests
        if self.rng.random() < self.error_rate:
            return 503                                  # random short error
        self.received.add(record_id)
        return 200


def naive_submit(api, record_ids, rate=15, retries=0):
    """Send at a steady pace (same as the gateway, to be fair).
    retries=0 -> send once.  retries=3 -> retry right away, no waiting."""
    failed = []
    for r in record_ids:
        for _ in range(retries + 1):
            api.clock.sleep(1 / rate)
            if api.submit(r) == 200:
                break
        else:
            failed.append(r)
    return {"failed": failed, "calls": api.calls, "seconds": api.clock.t}


class TokenBucket:
    """Allows `rate` calls per second. Each call takes a token; tokens refill over time."""

    def __init__(self, clock, rate):
        self.clock, self.rate, self.tokens, self.last = clock, rate, rate, 0.0

    def wait(self):
        now = self.clock.t
        self.tokens = min(self.rate, self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens < 1:
            self.clock.sleep((1 - self.tokens) / self.rate)   # wait for the next token
            self.tokens = 1
            self.last = self.clock.t
        self.tokens -= 1


class CircuitBreaker:
    """CLOSED = normal. OPEN = stop calling. HALF_OPEN = try one call to test."""

    def __init__(self, clock, fail_limit=5, cooldown=30.0):
        self.clock, self.fail_limit, self.cooldown = clock, fail_limit, cooldown
        self.state, self.fails, self.opened_at = "CLOSED", 0, None
        self.times_opened = 0

    def allow(self):
        if self.state == "OPEN" and self.clock.t - self.opened_at >= self.cooldown:
            self.state = "HALF_OPEN"
        return self.state != "OPEN"

    def success(self):
        self.state, self.fails = "CLOSED", 0

    def failure(self):
        self.fails += 1
        if self.state == "HALF_OPEN" or self.fails >= self.fail_limit:
            if self.state != "OPEN":
                self.times_opened += 1
            self.state, self.opened_at = "OPEN", self.clock.t


class Gateway:
    def __init__(self, api, rate=15, max_retries=5, base_delay=0.5, seed=2):
        self.api, self.clock = api, api.clock
        self.bucket = TokenBucket(self.clock, rate)
        self.breaker = CircuitBreaker(self.clock)
        self.max_retries, self.base_delay = max_retries, base_delay
        self.rng = random.Random(seed)
        self.dead_letter = []
        self.events = []        # for the audit log: (record_id, attempt, status, action)

    def send(self, record_id):
        for attempt in range(1, self.max_retries + 1):
            while not self.breaker.allow():               # circuit open: wait, don't hammer
                self.clock.sleep(1.0)
            self.bucket.wait()
            status = self.api.submit(record_id)
            if status == 200:
                self.breaker.success()
                self.events.append((record_id, attempt, status, "SENT"))
                return True
            self.breaker.failure()
            delay = self.base_delay * 2 ** (attempt - 1) * self.rng.uniform(0.5, 1.5)  # backoff + jitter
            self.events.append((record_id, attempt, status, f"RETRY in {delay:.2f}s"))
            self.clock.sleep(delay)
        self.dead_letter.append(record_id)
        self.events.append((record_id, self.max_retries, status, "DEAD_LETTER"))
        return False

    def run(self, record_ids):
        for r in record_ids:
            self.send(r)
        first_pass_failed = list(self.dead_letter)
        # Retry the dead-letter queue once at the end (the outage is usually over by then)
        retry, self.dead_letter = self.dead_letter, []
        for r in retry:
            self.send(r)
        return {"failed": self.dead_letter, "failed_first_pass": first_pass_failed,
                "calls": self.api.calls, "seconds": self.clock.t,
                "breaker_opened": self.breaker.times_opened}
