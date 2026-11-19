#!/usr/bin/env bash
# =============================================================================
# setup_mcode_lxc.sh — Einmal-Setup des mcode-Bug-Fixer-LXC
# Läuft IM LXC (root oder sudo). Idempotent.
#
# Vorher:
#   1. LXC aus Debian-12-Template anlegen (siehe deploy/AUTO_FIX.md)
#   2. Diesem Skript die 3 Secrets über ENV oder /etc/jtl-fixer/config.env
#      übergeben (werden nachher angelegt):
#        GITHUB_TOKEN, GITHUB_WEBHOOK_SECRET, MINIMAX_API_KEY
# =============================================================================
set -euo pipefail

echo "==> [1/6] Systempakete"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
    ca-certificates curl git build-essential \
    python3 python3-venv python3-pip \
    openssh-client

echo "==> [2/6] Python 3.12 + uv"
# Debian 12 liefert Python 3.11. Wir brauchen 3.12 für mcode-Kompatibilität.
# uv bringt seine eigene Python-Version mit — das ist der sauberste Weg.
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.12 || true
uv --version

echo "==> [3/6] Node.js 22 (Prism-Mock)"
NODE_VER=v22.14.0
if ! command -v node >/dev/null 2>&1 || ! node -v | grep -q "v22"; then
  mkdir -p /opt/node && cd /opt/node
  curl -fsSL "https://nodejs.org/dist/${NODE_VER}/node-${NODE_VER}-linux-x64.tar.xz" \
    | tar -xJ --strip-components=1
  ln -sf /opt/node/bin/node /usr/local/bin/node
  ln -sf /opt/node/bin/npm /usr/local/bin/npm
fi
node -v

echo "==> [4/6] mcode (MiniMax Code Agent)"
npm install -g @minimax-ai/code@latest \
  --registry=https://registry.npmjs.org/ \
  --include=optional \
  --allow-scripts=@minimax-ai/code,better-sqlite3
mcode --version

echo "==> [5/6] gh CLI"
if ! command -v gh >/dev/null 2>&1; then
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    -o /usr/share/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list
  apt-get update -y
  apt-get install -y gh
fi
gh --version

echo "==> [6/6] jtl-fixer-Dienste + Verzeichnisse"
mkdir -p /opt/jtl-fixer /etc/jtl-fixer /var/log/jtl-fixer

# Benutzer anlegen (unprivilegiert)
if ! id jtlfixer >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin jtlfixer
fi

# config.env anlegen (wenn noch nicht vorhanden) — Platzhalter
if [ ! -f /etc/jtl-fixer/config.env ]; then
  cat > /etc/jtl-fixer/config.env <<'EOF'
# GitHub
GITHUB_REPO="volkergrabbe/jtl-mcp-server"
GITHUB_TOKEN="PASTE_...HERE"
GITHUB_WEBHOOK_SECRET="PASTE_...HERE"

# MiniMax
MINIMAX_API_KEY="PASTE_...HERE"

# Verhalten
FIX_BRANCH_PREFIX="fix/issue-"
MAX_STEPS_PER_ISSUE="40"
MAX_TIMEOUT_SECONDS="1800"
EOF
  chown jtlfixer:jtlfixer /etc/jtl-fixer/config.env
  chmod 600 /etc/jtl-fixer/config.env
  echo "   ANMELDEN: /etc/jtl-fixer/config.env mit echten Secrets befüllen!"
fi

# fixer-bot.py und systemd-Unit ausliefern
cp /opt/jtl-fixer-src/fixer-bot.py /opt/jtl-fixer/fixer-bot.py 2>/dev/null || true
cp /opt/jtl-fixer-src/jtl-fixer.service /etc/systemd/system/jtl-fixer.service 2>/dev/null || true

systemctl daemon-reload
systemctl enable jtl-fixer 2>/dev/null || true

echo ""
echo "============================================================"
echo " Setup abgeschlossen."
echo ""
echo " Nächste Schritte:"
echo "   1. cp fixer-bot.py jtl-fixer.service /opt/jtl-fixer-src/"
echo "      (oder direkt hier ablegen — das Skript erwartet sie dort)"
echo "   2. /etc/jtl-fixer/config.env mit echten Secrets befüllen"
echo "   3. mcode provider set-minimax-key --api-key-env MINIMAX_API_KEY"
echo "      (einmalig, als jtlfixer-User)"
echo "   4. systemctl start jtl-fixer"
echo "   5. journalctl -u jtl-fixer -f"
echo "============================================================"
