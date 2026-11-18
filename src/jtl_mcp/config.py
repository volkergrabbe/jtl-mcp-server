"""Konfiguration des MCP-Servers (Pydantic Settings).

Alle Werte werden über Umgebungsvariablen bzw. eine `.env`-Datei gesetzt.
Secrets (`JTL_API_KEY`, `MCP_SERVER_AUTH_TOKEN`) werden als `SecretStr`
gehalten, damit sie weder in Logausgaben noch in repr()-Aufrufen auftauchen.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _split_csv(value: Any) -> Any:
    """Erlaubt Komma-Listen in Umgebungsvariablen (z. B. ``MCP_ALLOWED_HOSTS=a,b``)."""

    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return value


class Settings(BaseSettings):
    """Laufzeit-Konfiguration.

    Umgebungsvariablen sind groß- und kleinschreibungunabhängig, z. B.
    ``JTL_BASE_URL``, ``MCP_SERVER_AUTH_TOKEN``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- JTL-Wawi API ---------------------------------------------------
    jtl_base_url: str = "http://localhost:5883"
    """Basis-URL des JTL-Wawi-API-Servers, z. B. ``http://wawi-intern:5883``."""

    jtl_api_path: str = "/api/eazybusiness/v1"
    """Pfad-Präfix der REST-API.

    ``/api/eazybusiness/v1`` für die JTL-Wawi API (ab JTL-Wawi 1.9/2.0),
    ``/rest/eazybusiness/v1`` für den in Wawi integrierten REST-Server.
    """

    jtl_api_key: SecretStr
    """API-Key aus JTL-Wawi (Admin -> Benutzer/Rechte -> Key erzeugen)."""

    jtl_api_key_b64: bool = False
    """``true``, falls ``JTL_API_KEY`` bereits base64-kodiert vorliegt.

    Die Wawi erwartet ein base64-kodiertes Bearer-Token. Ist der Key ein
    reiner GUID-String (Standard), kodiert der Server ihn automatisch.
    """

    jtl_app_id: str | None = None
    """Optionale App-Id der registrierten App (nur Dokumentation/Logging)."""

    jtl_app_version: str = "1.0.0"
    """Version der registrierten App."""

    jtl_timeout: float = Field(default=20.0, gt=0, le=300)
    """Gesamtes Request-Timeout in Sekunden."""

    jtl_connect_timeout: float = Field(default=10.0, gt=0, le=300)
    """Connect-Timeout in Sekunden."""

    jtl_max_retries: int = Field(default=3, ge=0, le=10)
    """Anzahl Wiederholungen bei Timeouts und 429/5xx-Antworten."""

    jtl_backoff_seconds: float = Field(default=0.5, ge=0, le=30)
    """Basis-Wartezeit für exponentielles Backoff."""

    jtl_verify_tls: bool = True
    """TLS-Zertifikate prüfen (in Produktion aktiv lassen)."""

    jtl_page_size: int = Field(default=50, ge=1, le=500)
    """Standard-Seitengröße bei Listenabfragen."""

    jtl_max_page_size: int = Field(default=200, ge=1, le=1000)
    """Obergrenze der Seitengröße (Schutz gegen zu große Antworten)."""

    # --- MCP-Server -----------------------------------------------------
    mcp_server_auth_token: SecretStr
    """Statisches Bearer-Token, das der MCP-Server von LiteLLM erwartet."""

    mcp_host: str = "0.0.0.0"
    """Bind-Adresse des HTTP-Servers."""

    mcp_port: int = Field(default=8080, ge=1, le=65535)
    """Port des HTTP-Servers (MCP-Endpunkt: ``http://<host>:<port>/mcp``)."""

    mcp_path: str = "/mcp"
    """Pfad des Streamable-HTTP-Endpunkts."""

    mcp_allowed_hosts: Annotated[list[str], NoDecode] = Field(default_factory=list)
    """Erlaubte Host-Header (Host-Origin-Protection)."""

    mcp_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    """Erlaubte Origin-Header (Host-Origin-Protection)."""

    mcp_stateless_http: bool = False
    """Stateless-Modus des Streamable-HTTP-Transports."""

    mcp_log_level: str = "INFO"
    """Log-Level des Servers."""

    # --- Validatoren ----------------------------------------------------
    @field_validator("jtl_base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("JTL_BASE_URL muss mit 'http://' oder 'https://' beginnen.")
        return value

    @field_validator("jtl_api_path")
    @classmethod
    def _validate_api_path(cls, value: str) -> str:
        value = value.strip().strip("/")
        return f"/{value}" if value else ""

    @field_validator("mcp_path")
    @classmethod
    def _validate_mcp_path(cls, value: str) -> str:
        value = value.strip().strip("/")
        return f"/{value}" if value else "/mcp"

    @field_validator("mcp_allowed_hosts", "mcp_allowed_origins", mode="before")
    @classmethod
    def _parse_list(cls, value: Any) -> Any:
        return _split_csv(value)

    # --- Abgeleitete Werte ----------------------------------------------
    @property
    def api_base_url(self) -> str:
        """Vollständige Basis-URL der JTL-REST-API ohne abschließenden Slash."""

        return f"{self.jtl_base_url}{self.jtl_api_path}"

    @property
    def jtl_bearer_token(self) -> str:
        """Bearer-Token für die JTL-Wawi-API (base64-kodiert, sofern nötig)."""

        raw = self.jtl_api_key.get_secret_value()
        if self.jtl_api_key_b64:
            return raw
        return base64.b64encode(raw.encode("utf-8")).decode("ascii")

    @property
    def mcp_auth_token(self) -> str:
        """Erwartetes Bearer-Token für eingehende MCP-Requests."""

        return self.mcp_server_auth_token.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Gecachte Settings-Instanz (wird beim ersten Zugriff aus der Umgebung geladen)."""

    return Settings()  # type: ignore[call-arg]
