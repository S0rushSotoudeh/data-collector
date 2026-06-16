from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_ch_client() -> Generator[MagicMock, None, None]:
    with patch("src.db.clickhouse.clickhouse_connect.get_client") as m:
        instance = MagicMock()
        instance.command.return_value = None
        m.return_value = instance
        yield instance


@pytest.fixture
def mock_async_client() -> Generator[AsyncMock, None, None]:
    import src.db.clickhouse
    src.db.clickhouse._async_client = None
    with patch("src.db.clickhouse.clickhouse_connect.get_async_client") as m:
        instance = AsyncMock()
        instance.query = AsyncMock()
        instance.query.return_value.result_rows = []
        m.return_value = instance
        yield instance
    src.db.clickhouse._async_client = None


@pytest.fixture
def reset_client_cache() -> Generator[None, None, None]:
    import src.db.clickhouse
    src.db.clickhouse._client = None
    src.db.clickhouse._async_client = None
    yield
    src.db.clickhouse._client = None
    src.db.clickhouse._async_client = None