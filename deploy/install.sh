#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Installiert den JTL-Wawi MCP-Server als systemd-Dienst (Proxmox LXC).
#
# Aufruf (als root):
#   sudo ./deploy/install.sh
#
# Optionen:
#   --source-dir DIR   Quellverzeichnis (Standard: Projektverzeichnis)
#   --app-dir DIR      Installationsverzeichnis (Standard: /opt/jtl-mcp-server)
#   --env-dir DIR      Verzeichnis fuer die Konfiguration (Standard: /etc/jtl-mcp-server)
#   --user NAME        System-Benutzer (Standard: jtl-mcp)
#   --no-start         Dienst nicht starten
#   --skip-service     systemd-Dienst nicht installieren
#   -h, --help         Hilfe anzeigen
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="${SCRIPT_DIR}/.."
APP_DIR="/opt/jtl-mcp-server"
ENV_DIR="/etc/jtl-mcp-server"
SERVICE_USER="jtl-mcp"
SERVICE_GROUP="jtl-mcp"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MIN_PYTHON="3.11"
INSTALL_SERVICE=1
START_SERVICE=1
ENV_FILE=""

log()  { printf '\033[1;34m[install]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[install]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[install]\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
    sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --source-dir)   SOURCE_DIR="$2"; shift 2 ;;
        --app-dir)      APP_DIR="$2"; shift 2 ;;
        --env-dir)      ENV_DIR="$2"; shift 2 ;;
        --user)         SERVICE_USER="$2"; shift 2 ;;
        --no-start)     START_SERVICE=0; shift ;;
        --skip-service) INSTALL_SERVICE=0; shift ;;
        -h|--help)      usage ;;
        *)              die "Unbekannte Option: $1 (siehe --help)" ;;
    esac
done

ENV_FILE="${ENV_DIR}/.env"

# --- Voraussetzungen -------------------------------------------------------
[[ "${EUID}" -eq 0 ]] || die "Dieses Skript muss als root laufen (sudo)."
command -v "${PYTHON_BIN}" >/dev/null 2>&1 || die "Python wurde nicht gefunden: ${PYTHON_BIN}"

python_ok="$( "${PYTHON_BIN}" -c "import sys; print(1 if sys.version_info >= tuple(int(p) for p in '${MIN_PYTHON}'.split('.')) else 0)" )"
[[ "${python_ok}" == "1" ]] || die "Python >= ${MIN_PYTHON} wird benoetigt (gefunden: $("${PYTHON_BIN}" --version))."
command -v systemctl >/dev/null 2>&1 || die "systemctl wurde nicht gefunden - ist dies ein systemd-System?"

SOURCE_DIR="$(cd "${SOURCE_DIR}" && pwd)"
[[ -f "${SOURCE_DIR}/pyproject.toml" ]] || die "In ${SOURCE_DIR} liegt keine pyproject.toml."

log "Quellverzeichnis : ${SOURCE_DIR}"
log "Installationsdir : ${APP_DIR}"
log "Konfiguration    : ${ENV_FILE}"

# --- System-Benutzer -------------------------------------------------------
if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
    log "Lege System-Benutzer '${SERVICE_USER}' an."
    groupadd --system "${SERVICE_GROUP}"
    useradd --system --gid "${SERVICE_GROUP}" --home-dir "${APP_DIR}" \
            --shell /usr/sbin/nologin --no-create-home "${SERVICE_USER}"
else
    log "System-Benutzer '${SERVICE_USER}' existiert bereits."
fi

# --- Dateien kopieren -------------------------------------------------------
log "Kopiere Programm nach ${APP_DIR}."
install -d -m 0755 -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" "${APP_DIR}"
if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
        --exclude '.venv' --exclude '.git' --exclude '__pycache__' \
        --exclude '*.pyc' --exclude '.pytest_cache' --exclude '.ruff_cache' \
        --exclude '.env' \
        "${SOURCE_DIR}/" "${APP_DIR}/"
else
    rm -rf "${APP_DIR}.new"
    mkdir -p "${APP_DIR}.new"
    (cd "${SOURCE_DIR}" && tar --exclude='.venv' --exclude='.git' --exclude='__pycache__' \
        --exclude='*.pyc' --exclude='.pytest_cache' --exclude='.ruff_cache' --exclude='.env' -cf - .) \
        | (cd "${APP_DIR}.new" && tar -xf -)
    rm -rf "${APP_DIR}"
    mv "${APP_DIR}.new" "${APP_DIR}"
fi
chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${APP_DIR}"

# --- Virtuelle Umgebung -----------------------------------------------------
log "Erzeuge Python-venv und installiere Paket."
"${PYTHON_BIN}" -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null
"${APP_DIR}/.venv/bin/python" -m pip install "${APP_DIR}"
chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${APP_DIR}"

# --- Konfiguration ----------------------------------------------------------
install -d -m 0750 -o root -g "${SERVICE_GROUP}" "${ENV_DIR}"
if [[ ! -f "${ENV_FILE}" ]]; then
    log "Erzeuge ${ENV_FILE} aus .env.example - bitte anschliessend eintragen."
    install -m 0640 -o root -g "${SERVICE_GROUP}" "${APP_DIR}/.env.example" "${ENV_FILE}"
    cat <<EOF

  ==> Nächster Schritt: Zugangsdaten in ${ENV_FILE} eintragen
      JTL_API_KEY           (Admin -> Benutzer/Rechte -> Key erzeugen)
      MCP_SERVER_AUTH_TOKEN (z. B. openssl rand -hex 32)
      JTL_BASE_URL          (Basis-URL des JTL-Wawi-API-Servers)

EOF
else
    log "Konfiguration ${ENV_FILE} existiert bereits - unverändert."
fi

# --- systemd-Dienst ---------------------------------------------------------
if [[ "${INSTALL_SERVICE}" -eq 1 ]]; then
    UNIT_SRC="${SCRIPT_DIR}/jtl-mcp-server.service"
    UNIT_DST="/etc/systemd/system/jtl-mcp-server.service"
    [[ -f "${UNIT_SRC}" ]] || die "systemd-Unit ${UNIT_SRC} nicht gefunden."

    log "Installiere systemd-Unit."
    sed -e "s|__SERVICE_USER__|${SERVICE_USER}|g" \
        -e "s|__SERVICE_GROUP__|${SERVICE_GROUP}|g" \
        -e "s|__APP_DIR__|${APP_DIR}|g" \
        -e "s|__ENV_FILE__|${ENV_FILE}|g" \
        "${UNIT_SRC}" > "${UNIT_DST}"
    chmod 0644 "${UNIT_DST}"
    systemctl daemon-reload
    systemctl enable jtl-mcp-server.service >/dev/null
    log "Dienst jtl-mcp-server aktiviert."

    if [[ "${START_SERVICE}" -eq 1 ]]; then
        log "Starte Dienst."
        systemctl restart jtl-mcp-server.service
        sleep 2
        systemctl --no-pager --lines=10 status jtl-mcp-server.service || true
    fi
fi

cat <<EOF

  ==> Installation abgeschlossen.

  Konfiguration : ${ENV_FILE}
  Dienst        : systemctl status jtl-mcp-server
  Logs          : journalctl -u jtl-mcp-server -f
  MCP-Endpunkt  : http://<host>:8080/mcp

EOF
