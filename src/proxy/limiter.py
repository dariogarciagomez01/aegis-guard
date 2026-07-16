import time
import asyncio
from collections import defaultdict

class InMemoryRateLimiter:
    def __init__(self):
        # Maps: api_key -> list of timestamps of successful requests
        self._requests = defaultdict(list)
        # Maps: api_key -> asyncio.Lock to prevent async race conditions
        self._locks = defaultdict(asyncio.Lock)

    async def is_rate_limited(self, api_key: str, max_rpm: int) -> bool:
        """
        Evaluates requests using an in-memory sliding window algorithm.
        Returns True if the user has breached their RPM limit, False otherwise.
        """
        # Acquire a thread-safe async lock specifically for this API Key
        async with self._locks[api_key]:
            current_time = time.time()
            one_minute_ago = current_time - 60

            # Step 1: Evict old timestamps outside the 60-second sliding window
            self._requests[api_key] = [
                timestamp for timestamp in self._requests[api_key] if timestamp > one_minute_ago
            ]

            # Step 2: Check if the current request volume exceeds the allowed ceiling
            if len(self._requests[api_key]) >= max_rpm:
                return True  # Throttled!

            # Step 3: Register the current request timestamp
            self._requests[api_key].append(current_time)
            return False  # Allowed
            
# Instantiate a singleton to preserve state across the application lifespan
limiter = InMemoryRateLimiter()