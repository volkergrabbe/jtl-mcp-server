# Automatischer Bug-Fixer — mcode-LXC

Dokumentation und Setup-Script für den autonomen Bug-Fixer.
Ein dedizierter **Proxmox-LXC** läuft den **MiniMax-Code-Agenten (mcode)**
und bearbeitet GitHub-Issues mit dem Label `auto-fix` automatisch:
Reproduzieren → Fixen → Testen → Draft-PR erstellen.

> **Sicherheit:** Der Agent merged **nie** selbst. Merging ist ein menschlicher
> Schritt. Der Agent bekommt einen **read/write-fähigen, aber merge-blockierten**
> GitHub-Token (Scope: `repo` auf den einen Repo, **ohne** `workflow`, ohne
> Push auf `main`).

---

## 1. Architektur

```text
GitHub Issue (Label: auto-fix)
      │  Webhook (issues: edited/labeled)
      ▼
┌──────────────────────────────────────────────────────────────┐
│  mcode-LXC  (Proxmox, unprivileged, 1 CPU / 2 GB / 10 GB)     │
│                                                              │
│  fixer-bot.py  (Python, systemd-Unit)                        │
│    ├─ Webhook-Listener (FastAPI, Port 9999)                  │
│    ├─ Hält eine "Bearbeitet"-Liste (SQLite / JSON)           │
│    └─ Bei neuem auto-fix-Issue:                              │
│         1. git clone (Fork-Basis: main)                      │
│         2. venv + pip install -e ".[dev]"                    │
│         3. pytest tests/ -q          →  Baseline (grün?)     │
│         4. mcode exec "Fix issue #N: <body>"  →  Agent fixt  │
│         5. pytest tests/ -q          →  Fix-Verifikation     │
│         6. git commit + push  →  Branch fix/issue-N          │
│         7. gh pr create --draft  →  Draft-PR                │
│         8. Issue kommentieren (PR-Link + Log)                │
│         9. Issue-Label → auto-fixed (kein auto-fix)          │
│                                                              │
│  mcode (MiniMax M3, Thinking) — API-Key via ENV              │
│  git + gh CLI — GitHub-PAT (Repo-only, kein merge auf main)  │
└──────────────────────────────────────────────────────────────┘
      │  gh pr create --draft
      ▼
GitHub Draft-PR  →  Volker reviewed  →  manueller Merge
```

### Warum ein eigener LXC (nicht auf dem Haupt-Server)?

1. **Isolation:** mcode + MiniMax-Keys + GitHub-PAT isoliert vom produktiven
   jtl-mcp-server und vom LLM-Stack.
2. **Kost:** 1 CPU / 2 GB / 10 GB reichen — mcode ist ein CLI-Agent, kein
   LLM-Server. Die teuerste Ressource (MiniMax-Inferenz) läuft in der Cloud.
3. **Reproduzierbarkeit:** Der Agent braucht Python 3.12, Node.js 22 (Prism),
   git, gh. Ein sauberes LXC mit Debian-12-Template ist das deterministischste
   Ziel.
4. **Kein VRAM-Druck:** Kein lokales LLM — MiniMax-M3 läuft remote.

---

## 2. LXC-Vorgaben

| Parameter | Wert |
|-----------|------|
| Template | `local:vztmpl/debian-12-standard_12-*.tar.zst` |
| Container-ID | frei (z.B. 910) |
| Host | PVE3 |
| CPU | 1 (host-Mode) |
| RAM | 2048 MB |
| Disk | 10 GB (local-lvm) |
| Unprivileged | ja |
| Rootfs | read-only = nein |
| IP | statisch aus dem UniFi-Netz (z.B. 192.168.178.x/24) |
| Features | nesting=1 (nicht nötig, aber harmlos), kvm=0 |

---

## 3. Setup-Script

Das Skript `deploy/setup_mcode_lxc.sh` läuft **im LXC** und richtet alles ein.
Es ist idempotent (mehrfache Ausführung sicher).

Voraussetzung: LXC ist frisch aus dem Template gestartet, du bist als `root`
im Container (oder `sudo bash setup_mcode_lxc.sh`).

```bash
# Im LXC:
bash setup_mcode_lxc.sh
```

Das Skript installiert:
* Python 3.12 + venv + uv
* Node.js 22 (Prism-Mock)
* git + gh CLI
* mcode (`npm install -g @minimax-ai/code`)
* `fixer-bot.py` als systemd-Unit
* Konfigurationsdatei `/etc/jtl-fixer/config.env` (Secrets — nicht im Git!)

---

## 4. GitHub-Token (minimales Scope)

Erstelle einen **Personal Access Token (classic)** mit:

- Repo: **nur** `volkergrabbe/jtl-mcp-server` (fine-grained)
- Permissions:
  - `Contents: Read and write`
  - `Pull requests: Read and write`
  - `Issues: Read and write`
  - `Metadata: Read`
- **Kein** Admin, **kein** Deploy, **kein** Workflow-Write
- Der Token darf **nicht** auf `main` pushen — das erzwingt `fixer-bot.py`
  selbst (nur `fix/*`-Branches), zusätzlich: `branch protection` auf `main`
  (Require PR, no direct push).

---

## 5. GitHub-Webhook

Im Repo `volkergrabbe/jtl-mcp-server` → **Settings → Webhooks**:

* **Payload URL:** `http://<lxc-ip>:9999/webhook`
* **Content type:** `application/json`
* **Secret:** ein zufälliger String (muss in `config.env` als
  `WEBHOOK_SECRET` stehen)
* **Events:** `issues` (nur `edited` und `labeled` sind relevant; der Rest
  wird vom Bot ignoriert)

> GitHub-Webhooks kommen aus dem öffentlichen Internet. Wenn der LXC nur im
> UniFi-Netz liegt, brauchst du **einen** öffentlichen Pfad:
> 1. Cloudflare Tunnel (empfohlen — kein Port-Forwarding), oder
> 2. Reverse-Proxy auf einem public-reachbaren Host.

Der Bot validiert `X-Hub-Signature-256` gegen `WEBHOOK_SECRET` und verwirft
alles Unsignierte.

---

## 6. Betrieb

```bash
# Status
systemctl status jtl-fixer

# Logs
journalctl -u jtl-fixer -f

# Manuell ein Issue anstoßen (ohne Webhook):
sudo -u jtlfixer python3 /opt/jtl-fixer/fixer-bot.py --process-issue 42

# Konfiguration
cat /etc/jtl-fixer/config.env
```

### config.env (Beispiel)

```bash
# GitHub
GITHUB_REPO="volkergrabbe/jtl-mcp-server"
GITHUB_TOKEN="***"          # PAT aus Abschnitt 4
GITHUB_WEBHOOK_SECRET="***"  # Webhook-Secret

# MiniMax (mcode)
MINIMAX_API_KEY="***"

# Verhalten
FIX_BRANCH_PREFIX="fix/issue-"
MAX_STEPS_PER_ISSUE="40"
MAX_TIMEOUT_SECONDS="1800"
PR_BODY_TEMPLATE="/opt/jtl-fixer/pr_body.md"
```

---

## 7. Was der Agent NICHT darf

- Auf `main` pushen (Branch-Protection + Bot-Logik)
- PRs mergen (Token ohne Merge-Recht, Bot ruft `pr merge` nicht auf)
- Secrets in Commits oder PR-Bodies schreiben (Bot redagiert `Bearer`,
  API-Keys, Tokens aus dem PR-Body)
- Issues/PRs kommentieren, die nicht `auto-fix`-gelabelt sind

---

## 8. Fehlerbehandlung

| Situation | Verhalten |
|-----------|-----------|
| Baseline-Tests rot (vor dem Fix) | Bot kommentiert: "Baseline rot — kein Fix möglich" und labelt `wontfix` + `needs-human` |
| mcode-Timeout | Bot kommentiert mit Partial-Log, labelt `needs-human` |
| PR-Erstellung schlägt fehl | Retry 3×, dann `needs-human` |
| Issue hat kein `auto-fix` | Ignoriert |
| Issue bereits in der "Bearbeitet"-Liste | Ignoriert (kein Doppel-Fix) |

---

## 9. Kosten

| Position | Kosten |
|----------|--------|
| LXC (CPU/RAM/Disk) | ~0 (Bestands-Server) |
| MiniMax M3 | Token-Plan / Token-Plan (ab ~$22/Monat) |
| GitHub Actions (CI) | Free (Public Repo) |
| Cloudflare Tunnel | Free |
| **Gesamt** | **~$22/Monat** (MiniMax) |
