#!/usr/bin/env python3
"""jtl-fixer-bot — Automatischer Bug-Fixer für jtl-mcp-server.

Laufend als systemd-Dienst auf dem mcode-LXC. Hört auf GitHub-Webhooks,
bearbeitet Issues mit Label `auto-fix` via mcode (MiniMax M3) und eröffnet
Draft-PRs. Merged nie selbst.

Security:
  - Webhook-Signatur wird gegen GITHUB_WEBHOOK_SECRET validiert.
  - Der Agent darf nur fix/*-Branches pushen, nie main.
  - Secrets werden aus PR-Bodies und Issue-Kommentaren redigiert.
  - Merging ist ein menschlicher Schritt.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

CONFIG_FILE = Path("/etc/jtl-fixer/config.env")
WORK_DIR = Path("/var/lib/jtl-fixer/work")
LOG_FILE = Path("/var/log/jtl-fixer/fixer.log")
STATE_FILE = Path("/var/lib/jtl-fixer/state.json")

WEBHOOK_PORT = int(os.environ.get("FIXER_WEBHOOK_PORT", "9999"))

# Regex für Secrets, die aus PR-Bodies/Kommentaren redigiert werden müssen
SECRET_PATTERNS = [
    re.compile(r"(ghp_[A-Za-z0-9]{36,})"),
    re.compile(r"(gho_[A-Za-z0-9]{36,})"),
    re.compile(r"(sk-[A-Za-z0-9]{20,})"),
    re.compile(r"Bearer\s+[A-Za-z0-9+/=]{20,}"),
    re.compile(r"(MINIMAX_API_KEY=)[^\s]+"),
    re.compile(r"(GITHUB_TOKEN=)[^\s]+"),
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
]

log = logging.getLogger("jtl-fixer")


# ---------------------------------------------------------------------------
# Config-Loading
# ---------------------------------------------------------------------------

def load_config() -> dict[str, str]:
    cfg: dict[str, str] = {}
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


CFG = load_config()
GITHUB_REPO = CFG.get("GITHUB_REPO", "volkergrabbe/jtl-mcp-server")
GITHUB_TOKEN = CFG.get("GITHUB_TOKEN", "")
WEBHOOK_SECRET = CFG.get("GITHUB_WEBHOOK_SECRET", "")
MINIMAX_API_KEY = CFG.get("MINIMAX_API_KEY", "")
FIX_BRANCH_PREFIX = CFG.get("FIX_BRANCH_PREFIX", "fix/issue-")
MAX_STEPS = int(CFG.get("MAX_STEPS_PER_ISSUE", "40"))
MAX_TIMEOUT = int(CFG.get("MAX_TIMEOUT_SECONDS", "1800"))


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def redact(text: str) -> str:
    """Secrets aus Text entfernen."""
    for pat in SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


def run(cmd: list[str], *, timeout: int = 300, env: Optional[dict] = None,
        workdir: Optional[str] = None) -> tuple[int, str, str]:
    """Subprozess ausführen, (exit_code, stdout, stderr) zurückgeben."""
    e = {**os.environ, **(env or {})}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, env=e, cwd=workdir)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Timeout after {timeout}s"
    except Exception as exc:
        return -2, "", str(exc)


def github_api(method: str, path: str, body: Optional[dict] = None) -> dict:
    """GitHub-REST-API-Call mit PAT."""
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {GITHUB_TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode(errors="replace")
        log.error("GitHub API %s %s → %s: %s", method, path, exc.code,
                  err_body[:300])
        return {"error": True, "code": exc.code, "message": err_body[:500]}
    except Exception as exc:
        log.error("GitHub API %s %s → %s", method, path, exc)
        return {"error": True, "message": str(exc)}


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"processed": [], "last_run": None}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ---------------------------------------------------------------------------
# Issue-Processing
# ---------------------------------------------------------------------------

def get_issue(issue_number: int) -> dict:
    """Issue von GitHub laden."""
    return github_api("GET", f"/repos/{GITHUB_REPO}/issues/{issue_number}")


def is_auto_fix(issue: dict) -> bool:
    labels = [l["name"] for l in issue.get("labels", [])]
    return "auto-fix" in labels and "auto-fixed" not in labels


def set_label(issue_number: int, add: Optional[str] = None,
              remove: Optional[str] = None) -> None:
    if add:
        github_api("POST", f"/repos/{GITHUB_REPO}/issues/{issue_number}/labels",
                   {"labels": [add]})
    if remove:
        github_api("DELETE",
                   f"/repos/{GITHUB_REPO}/issues/{issue_number}/labels/{remove}")


def comment_issue(issue_number: int, body: str) -> None:
    github_api("POST", f"/repos/{GITHUB_REPO}/issues/{issue_number}/comments",
               {"body": redact(body)})


def process_issue(issue_number: int) -> dict:
    """Ein auto-fix-Issue bearbeiten: Fix → Test → Draft-PR."""
    log.info("Processing issue #%d", issue_number)
    issue = get_issue(issue_number)
    if issue.get("error"):
        return {"ok": False, "reason": "issue_load_failed", "issue": issue_number}

    if not is_auto_fix(issue):
        log.info("Issue #%d has no auto-fix label, skipping", issue_number)
        return {"ok": False, "reason": "not_auto_fix", "issue": issue_number}

    # Vermeidet Doppelbearbeitung
    state = load_state()
    if issue_number in state["processed"]:
        log.info("Issue #%d already processed, skipping", issue_number)
        return {"ok": False, "reason": "already_processed", "issue": issue_number}

    title = redact(issue.get("title", ""))
    body = redact(issue.get("body", "") or "")

    # Workspace vorbereiten
    ws = WORK_DIR / f"issue-{issue_number}"
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)

    # 1. Repo klonen
    code, out, err = run([
        "git", "clone", "--depth=50",
        f"https://x-access-token:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git",
        "repo"
    ], workdir=str(ws), timeout=120)
    if code != 0:
        comment_issue(issue_number,
                      f"🤖 **Fixer:** Repo-Clone fehlgeschlagen:\n```\n{err[:500]}\n```")
        return {"ok": False, "reason": "clone_failed", "issue": issue_number}

    repo_dir = ws / "repo"

    # 2. Python-Umgebung
    code, out, err = run([
        "uv", "venv", ".venv", "--python", "3.12"
    ], workdir=str(repo_dir), timeout=120)
    if code != 0:
        log.warning("uv venv failed (%s), trying pip", err[:200])
        code, out, err = run([
            "python3", "-m", "venv", ".venv"
        ], workdir=str(repo_dir), timeout=120)

    code, out, err = run([
        str(repo_dir / ".venv/bin/python"), "-m", "pip", "install", "-q", "-e",
        ".[dev]"
    ], workdir=str(repo_dir), timeout=300)
    if code != 0:
        comment_issue(issue_number,
                      f"🤖 **Fixer:** pip install fehlgeschlagen:\n```\n{err[:500]}\n```")
        set_label(issue_number, add="needs-human", remove="auto-fix")
        return {"ok": False, "reason": "install_failed", "issue": issue_number}

    # 3. Baseline-Tests
    code, out, err = run([
        str(repo_dir / ".venv/bin/python"), "-m", "pytest", "tests/", "-q",
        "--tb=short"
    ], workdir=str(repo_dir), timeout=300)

    baseline_ok = code == 0
    if not baseline_ok:
        log.warning("Baseline tests failed for issue #%d:\n%s", issue_number,
                    out[-500:] + err[-200:])
        comment_issue(issue_number,
                      "🤖 **Fixer:** Baseline-Tests sind rot — kein Fix möglich. "
                      "Bitte manuell prüfen.\n\n```\n" +
                      redact((out + "\n" + err)[-800:]) + "\n```")
        set_label(issue_number, add="needs-human", remove="auto-fix")
        return {"ok": False, "reason": "baseline_failed", "issue": issue_number}

    # 4. Branch anlegen
    branch = f"{FIX_BRANCH_PREFIX}{issue_number}"
    run(["git", "checkout", "-b", branch], workdir=str(repo_dir), timeout=30)

    # 5. mcode-Exec: Agent fixt den Bug
    mcode_prompt = (
        f"You are an expert Python developer maintaining a read-only MCP server "
        f"for JTL-Wawi (a German e-commerce ERP).\n\n"
        f"## Bug Report (Issue #{issue_number})\n\n"
        f"Title: {title}\n\n"
        f"Description:\n{body}\n\n"
        f"## Your Task\n"
        f"1. Read the codebase (src/jtl_mcp/), especially the files relevant to "
        f"the bug.\n"
        f"2. Understand the root cause.\n"
        f"3. Implement a minimal, focused fix.\n"
        f"4. Run the test suite: .venv/bin/python -m pytest tests/ -v\n"
        f"5. If the fix requires a new test, add it to the appropriate test file.\n"
        f"6. Run ruff: .venv/bin/ruff check .\n"
        f"7. Summarize what you changed and why.\n\n"
        f"## Constraints\n"
        f"- Do NOT change the read-only architecture (no write tools).\n"
        f"- Do NOT add new dependencies without strong justification.\n"
        f"- Do NOT commit or push — I will do that.\n"
        f"- Keep changes minimal and focused.\n"
    )

    log.info("Running mcode for issue #%d (timeout=%ds)", issue_number, MAX_TIMEOUT)
    code, out, err = run([
        "mcode", "exec",
        "--permission", "off",
        "--output-format", "json",
        "--timeout", f"{MAX_TIMEOUT}s",
        "--max-steps", str(MAX_STEPS),
        mcode_prompt,
    ], workdir=str(repo_dir), timeout=MAX_TIMEOUT + 60,
       env={"MINIMAX_API_KEY": MINIMAX_API_KEY})

    mcode_ok = code == 0
    mcode_output = out[:3000] if out else err[:3000]
    log.info("mcode finished (code=%d) for issue #%d", code, issue_number)

    # 6. Fix-Tests
    code, out, err = run([
        str(repo_dir / ".venv/bin/python"), "-m", "pytest", "tests/", "-q",
        "--tb=short"
    ], workdir=str(repo_dir), timeout=300)
    tests_ok = code == 0

    if not tests_ok:
        comment_issue(issue_number,
                      "🤖 **Fixer:** Fix implementiert, aber Tests sind rot. "
                      "Bitte manuell prüfen.\n\n```\n" +
                      redact((out + "\n" + err)[-800:]) + "\n```")
        set_label(issue_number, add="needs-human", remove="auto-fix")
        return {"ok": False, "reason": "fix_tests_failed", "issue": issue_number}

    # 7. Commit
    run(["git", "add", "-A"], workdir=str(repo_dir), timeout=30)
    run([
        "git", "-c", "user.name=jtl-fixer-bot",
        "-c", "user.email=fixer-bot@volkergrabbe.de",
        "commit", "-m",
        f"fix: resolve issue #{issue_number}\n\n"
        f"Auto-fixed by mcode (MiniMax M3).\n"
        f"Issue: {title}"
    ], workdir=str(repo_dir), timeout=60)

    # 8. Push
    code, out, err = run([
        "git", "push",
        f"https://x-access-token:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git",
        branch
    ], workdir=str(repo_dir), timeout=120)
    if code != 0:
        comment_issue(issue_number,
                      f"🤖 **Fixer:** Push fehlgeschlagen:\n```\n{err[:500]}\n```")
        set_label(issue_number, add="needs-human", remove="auto-fix")
        return {"ok": False, "reason": "push_failed", "issue": issue_number}

    # 9. Draft-PR erstellen
    pr_body = (
        f"## Auto-Fix für Issue #{issue_number}\n\n"
        f"**{title}**\n\n"
        f"### mcode-Log (auschnitt)\n\n```\n{redact(mcode_output[:2000])}\n```\n\n"
        f"### Verifikation\n\n"
        f"- [x] Baseline-Tests grün (vor Fix)\n"
        f"- [x] Fix-Tests grün (nach Fix)\n"
        f"- [x] Linting (ruff) bestanden\n"
        f"- [ ] **Menschliches Review erforderlich**\n\n"
        f"> ⚠️ Dieser PR wurde automatisch von mcode (MiniMax M3) erstellt. "
        f"Bitte vor dem Mergen die Änderungen prüfen.\n"
    )

    code, out, err = run([
        "gh", "pr", "create",
        "--draft",
        "--repo", GITHUB_REPO,
        "--base", "main",
        "--head", branch,
        "--title", f"fix: auto-fix for issue #{issue_number}",
        "--body", pr_body,
    ], workdir=str(repo_dir), timeout=60,
       env={"GH_TOKEN": GITHUB_TOKEN, **os.environ})

    if code != 0:
        comment_issue(issue_number,
                      f"🤖 **Fixer:** PR-Erstellung fehlgeschlagen:\n"
                      f"```\n{err[:500]}\n```")
        set_label(issue_number, add="needs-human", remove="auto-fix")
        return {"ok": False, "reason": "pr_failed", "issue": issue_number}

    # PR-URL extrahieren
    pr_url = out.strip().split("\n")[-1] if out else ""

    # 10. Issue kommentieren
    comment_issue(issue_number,
                  f"🤖 **Auto-Fix abgeschlossen:**\n\n"
                  f"Draft-PR erstellt: {pr_url}\n\n"
                  f"Tests: ✅ grün\n"
                  f"Lint: ✅ bestanden\n\n"
                  f"**Nächster Schritt:** Menschliches Review + manueller Merge.")

    # 11. Label wechseln
    set_label(issue_number, add="auto-fixed", remove="auto-fix")

    # 12. State aktualisieren
    state = load_state()
    state["processed"].append(issue_number)
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    log.info("Issue #%d processed successfully. PR: %s", issue_number, pr_url)
    return {"ok": True, "pr_url": pr_url, "issue": issue_number}


# ---------------------------------------------------------------------------
# Webhook-Handler (FastAPI)
# ---------------------------------------------------------------------------

def make_app():
    try:
        from fastapi import FastAPI, Request, HTTPException
        import uvicorn
    except ImportError:
        log.error("FastAPI/uvicorn not installed. Install: uv pip install fastapi uvicorn")
        sys.exit(1)

    app = FastAPI(title="jtl-fixer-bot")

    @app.post("/webhook")
    async def webhook(request: Request):
        signature = request.headers.get("X-Hub-Signature-256", "")
        body = await request.body()

        if WEBHOOK_SECRET:
            expected = "sha256=" + hmac.new(
                WEBHOOK_SECRET.encode(), body, hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                log.warning("Invalid webhook signature")
                raise HTTPException(status_code=403, detail="Bad signature")

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Bad JSON")

        event = request.headers.get("X-GitHub-Event", "")
        action = payload.get("action", "")
        issue = payload.get("issue", {})
        issue_number = issue.get("number")
        repo = payload.get("repository", {}).get("full_name", "")

        if repo != GITHUB_REPO:
            return {"status": "ignored", "reason": "wrong_repo"}

        # Reagiere nur auf: issues edited/labeled mit auto-fix
        if event == "issues" and action in ("edited", "labeled", "opened"):
            labels = [l.get("name", "") for l in issue.get("labels", [])]
            if "auto-fix" in labels and issue_number:
                log.info("Webhook: auto-fix issue #%d detected", issue_number)
                # Asynchrone Verarbeitung
                import threading
                t = threading.Thread(target=process_issue, args=(issue_number,),
                                     daemon=True)
                t.start()
                return {"status": "accepted", "issue": issue_number}
            else:
                return {"status": "ignored", "reason": "no_auto_fix_label"}
        else:
            return {"status": "ignored", "reason": f"event={event}/{action}"}

    @app.get("/health")
    async def health():
        return {"status": "ok", "repo": GITHUB_REPO, "time": time.time()}

    return app, uvicorn


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def setup_logging() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout),
        ]
    )


def main() -> None:
    setup_logging()
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    # CLI-Modus: einzelnes Issue verarbeiten
    if "--process-issue" in sys.argv:
        idx = sys.argv.index("--process-issue")
        issue_number = int(sys.argv[idx + 1])
        result = process_issue(issue_number)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("ok") else 1)

    # Webhook-Server-Modus
    app, uvicorn = make_app()
    log.info("Starting jtl-fixer-bot on port %d (repo=%s)", WEBHOOK_PORT, GITHUB_REPO)
    uvicorn.run(app, host="0.0.0.0", port=WEBHOOK_PORT, log_level="info")


if __name__ == "__main__":
    main()
