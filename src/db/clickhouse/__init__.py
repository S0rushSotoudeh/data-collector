import time

import clickhouse_connect
from clickhouse_connect.driver import Client
from clickhouse_connect.driver.asyncclient import AsyncClient

from src.config import env, env_float, env_int

_client: Client | None = None
_async_client: AsyncClient | None = None
def get_client() -> Client:
    global _client
    if _client is not None:
        try:
            _client.command("SELECT 1")
            return _client
        except Exception:
            _client = None

    retries = env_int("CLICKHOUSE_CONNECT_RETRIES")
    retry_delay = env_float("CLICKHOUSE_RETRY_DELAY")
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            _client = clickhouse_connect.get_client(
                host=env("CLICKHOUSE_HOST"),
                port=env_int("CLICKHOUSE_PORT"),
                username=env("CLICKHOUSE_USER"),
                password=env("CLICKHOUSE_PASSWORD"),
                connect_timeout=env_int("CLICKHOUSE_CONNECT_TIMEOUT"),
            )
            _client.command("SELECT 1")
            return _client
        except Exception as e:
            last_exc = e
            if attempt < retries - 1:
                time.sleep(retry_delay * (attempt + 1))

    raise ConnectionError(
        f"Cannot connect to ClickHouse after {retries} attempts"
    ) from last_exc


async def get_async_client() -> AsyncClient:
    global _async_client
    if _async_client is not None:
        try:
            await _async_client.query("SELECT 1")
            return _async_client
        except Exception:
            _async_client = None

    retries = env_int("CLICKHOUSE_CONNECT_RETRIES")
    retry_delay = env_float("CLICKHOUSE_RETRY_DELAY")
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            _async_client = await clickhouse_connect.get_async_client(
                host=env("CLICKHOUSE_HOST"),
                port=env_int("CLICKHOUSE_PORT"),
                username=env("CLICKHOUSE_USER"),
                password=env("CLICKHOUSE_PASSWORD"),
                connect_timeout=env_int("CLICKHOUSE_CONNECT_TIMEOUT"),
            )
            await _async_client.query("SELECT 1")
            return _async_client
        except Exception as e:
            last_exc = e
            if attempt < retries - 1:
                await _async_sleep(retry_delay * (attempt + 1))

    raise ConnectionError(
        f"Cannot connect to ClickHouse after {retries} attempts"
    ) from last_exc


async def _async_sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)


def _ensure_client(client: Client | None) -> Client:
    return client if client is not None else get_client()


def price_to_storage(price: float | int) -> int:
    return int(price)


def price_from_storage(price: int) -> float:
    return float(price)
