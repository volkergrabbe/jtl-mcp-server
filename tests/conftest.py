"""Gemeinsame Test-Fixtures."""

from __future__ import annotations

import pytest
import respx

from jtl_mcp import server as server_module
from jtl_mcp.config import Settings

API_BASE_URL = "http://wawi.test:5883/api/eazybusiness/v1"


@pytest.fixture
def settings() -> Settings:
    """Testkonfiguration ohne echte Zugangsdaten."""

    return Settings(
        jtl_base_url="http://wawi.test:5883",
        jtl_api_path="/api/eazybusiness/v1",
        jtl_api_key="12345678-ABCD-1234-1234-123456ABCDEF",
        mcp_server_auth_token="test-mcp-token",
        jtl_max_retries=2,
        jtl_backoff_seconds=0.0,
        jtl_page_size=50,
        jtl_max_page_size=200,
    )


@pytest.fixture(autouse=True)
def _use_test_settings(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> Settings:
    """Verhindert, dass Tests echte Umgebungsvariablen verwenden."""

    monkeypatch.setattr(server_module, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def api():
    """respx-Router, der alle Requests an die JTL-Wawi-API abfängt."""

    with respx.mock(base_url=API_BASE_URL, assert_all_called=False) as router:
        yield router
