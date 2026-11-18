"""Asynchroner HTTP-Client für die JTL-Wawi-REST-API.

Merkmale:

* **Strikt read-only:** Der Client bietet ausschließlich GET-Operationen an.
  Ein interner Wächter blockiert jede andere HTTP-Methode.
* **Retry-Logik:** Zeitouts sowie 429/5xx-Antworten werden mit exponentiellem
  Backoff wiederholt.
* **Fehler-Mapping:** HTTP- und Netzwerkfehler werden auf eigene, klar
  benannte Ausnahmen abgebildet, damit die MCP-Tools verständliche Meldungen
  an den Client geben können.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import Settings

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


class JtlApiError(Exception):
    """Basisklasse für Fehler der JTL-Wawi-API."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class JtlAuthError(JtlApiError):
    """Zugang wurde abgelehnt (401/403) oder der API-Key ist ungültig."""


class JtlNotFoundError(JtlApiError):
    """Die angeforderte Ressource existiert nicht (404)."""


class JtlTimeoutError(JtlApiError):
    """Die API hat innerhalb des Timeouts nicht geantwortet."""


class JtlConnectionError(JtlApiError):
    """Die API ist nicht erreichbar (DNS, TCP, TLS)."""


class JtlReadOnlyViolation(RuntimeError):
    """Es wurde versucht, eine schreibende HTTP-Methode auszuführen."""


@dataclass(frozen=True, slots=True)
class Page:
    """Eine Seite einer paged API-Antwort."""

    items: list[Any] = field(default_factory=list)
    total_items: int = 0
    page_number: int = 1
    page_size: int = 0
    total_pages: int = 0


class JtlClient:
    """Async-Client für die JTL-Wawi-REST-API (nur GET)."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    # --- Kontextmanagement ------------------------------------------------
    async def __aenter__(self) -> JtlClient:
        self._ensure_client()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Schließt den zugrunde liegenden HTTP-Pool."""

        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # --- HTTP --------------------------------------------------------------
    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=f"{self._settings.api_base_url}/",
                timeout=httpx.Timeout(
                    self._settings.jtl_timeout,
                    connect=self._settings.jtl_connect_timeout,
                ),
                headers={
                    "Authorization": f"Bearer {self._settings.jtl_bearer_token}",
                    "Accept": "application/json",
                    "User-Agent": "jtl-mcp-server/0.1.0",
                },
                verify=self._settings.jtl_verify_tls,
                transport=self._transport,
                follow_redirects=False,
            )
        return self._client

    async def get_json(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """Führt einen GET-Request aus und liefert das dekodierte JSON."""

        response = await self._request("GET", path, params)
        self._raise_for_status(response)
        try:
            return response.json()
        except ValueError as exc:
            raise JtlApiError(
                "Die JTL-Wawi-API hat keine gültige JSON-Antwort geliefert.",
                status_code=response.status_code,
            ) from exc

    async def get_paged(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        page_number: int = 1,
        page_size: int | None = None,
    ) -> Page:
        """Führt einen GET-Request auf einen paged Endpunkt aus."""

        size = page_size or self._settings.jtl_page_size
        size = max(1, min(size, self._settings.jtl_max_page_size))
        query: dict[str, Any] = {
            key: value for key, value in (params or {}).items() if value is not None
        }
        query["pageNumber"] = page_number
        query["pageSize"] = size

        payload = await self.get_json(path, query)
        return self._to_page(payload, page_number=page_number, page_size=size)

    @staticmethod
    def _to_page(payload: Any, *, page_number: int, page_size: int) -> Page:
        if isinstance(payload, list):
            return Page(
                items=list(payload),
                total_items=len(payload),
                page_number=page_number,
                page_size=page_size,
                total_pages=1,
            )
        if not isinstance(payload, Mapping):
            return Page(items=[], page_number=page_number, page_size=page_size)

        raw_items = payload.get("Items")
        items = list(raw_items) if isinstance(raw_items, list) else []
        total_items = payload.get("TotalItems")
        total_pages = payload.get("TotalPages")
        return Page(
            items=items,
            total_items=int(total_items) if isinstance(total_items, int) else len(items),
            page_number=int(payload.get("PageNumber") or page_number),
            page_size=int(payload.get("PageSize") or page_size),
            total_pages=int(total_pages) if isinstance(total_pages, int) else 0,
        )

    async def _request(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        """Führt den Request mit Retry-Logik aus."""

        if method.upper() != "GET":
            raise JtlReadOnlyViolation(
                f"HTTP-Methode {method.upper()!r} ist in diesem Server nicht erlaubt "
                "(strikt read-only)."
            )
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError(f"Ungültiger API-Pfad: {path!r}")

        client = self._ensure_client()
        attempts = self._settings.jtl_max_retries + 1
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                response = await client.get(path, params=params)
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt >= attempts:
                    raise JtlTimeoutError(
                        f"Zeitüberschreitung bei der Abfrage der JTL-Wawi-API ({path})."
                    ) from exc
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= attempts:
                    raise JtlConnectionError(
                        f"Die JTL-Wawi-API ist nicht erreichbar ({path}): {exc}"
                    ) from exc
            else:
                if response.status_code in RETRYABLE_STATUS_CODES and attempt < attempts:
                    logger.warning(
                        "JTL-Wawi-API antwortete mit %s - erneuter Versuch (%s/%s).",
                        response.status_code,
                        attempt,
                        attempts - 1,
                    )
                else:
                    return response

            delay = self._settings.jtl_backoff_seconds * (2 ** (attempt - 1))
            if delay > 0:
                await asyncio.sleep(delay)

        # Nicht erreichbar, da die Schleife bei Erfolg returnt.
        raise JtlConnectionError(f"Abfrage der JTL-Wawi-API fehlgeschlagen: {last_error}")

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status = response.status_code
        if status < 400:
            return

        detail = _extract_detail(response)
        if status in (401, 403):
            raise JtlAuthError(
                "Die JTL-Wawi-API hat die Authentifizierung abgelehnt "
                "(401/403). Bitte JTL_API_KEY prüfen.",
                status_code=status,
                detail=detail,
            )
        if status == 404:
            raise JtlNotFoundError(
                "Der angeforderte Datensatz wurde in JTL-Wawi nicht gefunden (404).",
                status_code=status,
                detail=detail,
            )
        if status == 429:
            raise JtlApiError(
                "Die JTL-Wawi-API hat zu viele Anfragen erhalten (429) - "
                "bitte später erneut versuchen.",
                status_code=status,
                detail=detail,
            )
        raise JtlApiError(
            f"Die JTL-Wawi-API hat mit HTTP {status} geantwortet.",
            status_code=status,
            detail=detail,
        )


def _extract_detail(response: httpx.Response) -> str | None:
    """Liest eine kurze Fehlermeldung aus dem Response-Body."""

    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:300] or None
    if isinstance(payload, Mapping):
        for key in ("title", "detail", "message", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:300]
    return None
