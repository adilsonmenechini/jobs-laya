"""Shared retry utility for HTTP sources — exponential backoff + jitter."""

import asyncio
import random

import httpx


async def retry_on_transient(
    operation,
    max_retries: int,
    backoff_seconds: float,
):
    """Retry an async operation on transient HTTP errors.

    Retries on `httpx.HTTPError` (connect, timeout, 5xx) with exponential
    backoff + jitter. Non-transient errors (ValueError, etc.) propagate
    immediately. After exhausting retries, the last `httpx.HTTPError`
    propagates.
    """
    attempts = 1 + max(0, max_retries)
    backoff = max(0.0, backoff_seconds)
    for attempt in range(attempts):
        try:
            return await operation()
        except httpx.HTTPError:
            if attempt >= attempts - 1:
                raise
            await asyncio.sleep(backoff * (2**attempt) + random.uniform(0.0, backoff))
