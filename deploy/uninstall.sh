#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Entfernt den JTL-Wawi MCP-Server wieder vom System.
#
#   sudo ./deploy/uninstall.sh            # Dienst + Programm entfernen, Konfiguration behalten
#   sudo ./deploy/uninstall.sh --purge    # zusaetzlich Konfiguration und Benutzer entfernen
# ---------------------------------------------------------------------------
set -euo pipefail

APP_DIR="/opt/jtl-mcp-server"
ENV_DIR="/etc/jtl-mcp-server"
SERVICE_USER="jtl-mcp"
SERVICE_GROUP="jtl-mcp"
PURGE=0

log()  { printf '\033[1;34m[uninstall]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[uninstall]\033[0m %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --purge)   PURGE=1; shift ;;
        --app-dir) APP_DIR="$2"; shift 2 ;;
        --env-dir) ENV_DIR="$2"; shift 2 ;;
        --user)    SERVICE_USER="$2"; shift 2 ;;
        -h|--help) sed -n '2,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)         die "Unbekannte Option: $1" ;;
    esac
done

[[ "${EUID}" -eq 0 ]] || die "Dieses Skript muss als root laufen (sudo)."

if systemctl list-unit-files 2>/dev/null | grep -q '^jtl-mcp-server.service'; then
    log "Stoppe und deaktiviere Dienst."
    systemctl disable --now jtl-mcp-server.service || true
fi

if [[ -f /etc/systemd/system/jtl-mcp-server.service ]]; then
    log "Entferne systemd-Unit."
    rm -f /etc/systemd/system/jtl-mcp-server.service
    systemctl daemon-reload
    systemctl reset-failed jtl-mcp-server.service 2>/dev/null || true
fi

if [[ -d "${APP_DIR}" ]]; then
    log "Entferne ${APP_DIR}."
    rm -rf "${APP_DIR}"
fi

if [[ "${PURGE}" -eq 1 ]]; then
    if [[ -d "${ENV_DIR}" ]]; then
        log "Entferne Konfiguration ${ENV_DIR}."
        rm -rf "${ENV_DIR}"
    fi
    if id -u "${SERVICE_USER}" >/dev/null 2>&1; then
        log "Entferne System-Benutzer ${SERVICE_USER}."
        userdel "${SERVICE_USER}" || true
        groupdel "${SERVICE_GROUP}" 2>/dev/null || true
    fi
    log "Aufraeumen abgeschlossen (--purge)."
else
    log "Aufraeumen abgeschlossen. Konfiguration in ${ENV_DIR} bleibt erhalten."
    log "Mit --purge werden Konfiguration und System-Benutzer ebenfalls entfernt."
fi
