"""langsmith's tracing stays off under Compose's settings (CF-113 item 48)."""

from collections.abc import Iterator

import pytest
from langsmith import utils as langsmith_utils


def _clear_lookups() -> None:
    clear = getattr(langsmith_utils.get_env_var, "cache_clear", None)
    assert callable(clear), "langsmith's get_env_var cache has changed"
    clear()


@pytest.fixture
def fresh_lookups() -> Iterator[None]:
    _clear_lookups()
    yield
    _clear_lookups()


def test_langsmith_tracing_stays_off(
    fresh_lookups: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert langsmith_utils.tracing_is_enabled() is False
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    _clear_lookups()
    assert langsmith_utils.tracing_is_enabled() is False
