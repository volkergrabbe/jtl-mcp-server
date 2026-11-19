# Contributing — jtl-mcp-server

Danke für den Beitrag! Dieses Projekt ist **MIT-lizenziert** und open source.

## Bug-Reporting (wichtigster Beitrag)

Der schnellste Weg, dieses Projekt besser zu machen: **gute Bug-Reports**.

### Format

Nutzt das Bug-Report-Template (`Issues → New issue → Bug Report`).
Es enthält alle Felder, die der automatische Fixer braucht:

- **JTL-Wawi-Version** — 1.11, 2.0, 2.1?
- **jtl-mcp-server Version** — `pip show jtl-mcp-server`
- **Vollständiger Traceback** — nicht nur die letzte Zeile
- **Minimales Reproduktionsbeispiel** — welcher Tool-Aufruf?
- **Umgebung** — HTTP, stdio, Docker, LXC?

### Was der automatische Fixer damit macht

Issues mit Label `auto-fix` werden von einem **autonomen mcode-Agenten**
(MiniMax M3) auf einem dedizierten LXC-Container bearbeitet:

1. Agent klonnt den Repo
2. Reproduziert den Bug (mit respx-Mocks, keine echte JTL-Instanz nötig)
3. Implementiert den Fix
4. Läuft die komplette Test-Suite
5. Eröffnet einen **Draft-PR** mit dem Fix + Verifikations-Log
6. **Ihr** (der Maintainer) reviewed den PR und merged ihn

> **Wichtig:** Der Agent merged **nie** selbst. Merging ist immer
> ein menschlicher Schritt. Der Agent öffnet nur Draft-PRs.

### Labels

| Label | Bedeutung |
|-------|-----------|
| `bug` | Bestätigter Fehler |
| `auto-fix` | Vom mcode-Agenten bearbeitbar |
| `needs-triage` | Wartet auf menschliche Prüfung |
| `enhancement` | Feature Request |
| `help wanted` | Setup/Config-Frage |
| `wontfix` | Kann oder soll nicht gefixt werden |

## Code-Beiträge

### Setup

```bash
git clone https://github.com/volkergrabbe/jtl-mcp-server.git
cd jtl-mcp-server
uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### Tests

```bash
# Alle Tests
pytest tests/ -v

# Nur Unit-Tests (schnell)
pytest tests/test_tools.py -v

# Mit Coverage
pytest tests/ --cov=jtl_mcp --cov-report=term-missing
```

### Linting

```bash
ruff check .
ruff format .
```

### PR-Richtlinien

- Ein PR = ein Fix / eine Feature
- Alle Tests müssen grün sein
- Kein echter JTL-Wawi-Zugriff in Tests (immer respx-Mocks)
- Neue Tools: immer mit Unit-Test

## Was NICHT gehört

- API-Keys, Zugangsdaten, echte Kundendaten
- Kommerzielle Nutzung als gehosteter Service (MIT erlaubt das, aber
  der Maintainer will keine Agensi-Skills sehen — siehe README)
- Änderungen an der Read-only-Architektur (bewusst keine Write-Tools)
