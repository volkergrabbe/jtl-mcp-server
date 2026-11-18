"""JTL-Wawi Read-Only MCP Server.

Stellt JTL-Wawi-Daten (Aufträge, Kunden, Artikel, Lagerbestände, Versandstatus)
über das Model Context Protocol bereit. Der Server ist strikt lesend: es werden
ausschließlich HTTP-GET-Requests gegen die JTL-Wawi-REST-API ausgeführt.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
