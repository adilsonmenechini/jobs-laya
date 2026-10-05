"""Shared retry utility — exponential backoff + jitter."""

import httpx
import pytest

from app.sources.retry import retry_on_transient


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failures(monkeypatch):
    calls: list = []
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    async def operation() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ConnectError("blip")
        return "ok"

    monkeypatch.setattr("app.sources.retry.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("app.sources.retry.random.uniform", lambda low, high: 0.0)

    result = await retry_on_transient(operation, max_retries=2, backoff_seconds=5.0)

    assert result == "ok"
    assert len(calls) == 3
    assert slept == [5.0, 10.0]


@pytest.mark.asyncio
async def test_retry_raises_after_exhausting_attempts(monkeypatch):
    calls: list = []
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    async def operation() -> str:
        calls.append(1)
        raise httpx.ConnectError("down")

    monkeypatch.setattr("app.sources.retry.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("app.sources.retry.random.uniform", lambda low, high: 0.0)

    with pytest.raises(httpx.ConnectError):
        await retry_on_transient(operation, max_retries=2, backoff_seconds=5.0)

    assert len(calls) == 3
    assert slept == [5.0, 10.0]


@pytest.mark.asyncio
async def test_retry_does_not_catch_non_transient_errors(monkeypatch):
    calls: list = []

    async def operation() -> str:
        calls.append(1)
        raise ValueError("permanent")

    with pytest.raises(ValueError):
        await retry_on_transient(operation, max_retries=3, backoff_seconds=1.0)

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_retry_includes_jitter(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    async def operation() -> str:
        raise httpx.ConnectError("blip")

    monkeypatch.setattr("app.sources.retry.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("app.sources.retry.random.uniform", lambda low, high: high)

    with pytest.raises(httpx.ConnectError):
        await retry_on_transient(operation, max_retries=1, backoff_seconds=5.0)

    assert slept == [10.0]  # 5·2⁰ + jitter(5)


@pytest.mark.asyncio
async def test_retry_zero_retries_is_single_shot(monkeypatch):
    calls: list = []

    async def operation() -> str:
        calls.append(1)
        raise httpx.ConnectError("down")

    with pytest.raises(httpx.ConnectError):
        await retry_on_transient(operation, max_retries=0, backoff_seconds=1.0)

    assert len(calls) == 1
