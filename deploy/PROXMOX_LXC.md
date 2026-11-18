# Betrieb im Proxmox-LXC

Kurzanleitung fuer den Betrieb des JTL-Wawi MCP-Servers in einem
Proxmox-VE-Container (LXC, unprivileged).

## 1. Container anlegen

Im Web-UI oder auf der Proxmox-CLI:

```bash
# Template herunterladen (Debian 12/13 oder Ubuntu 24.04)
pveam update
pveam download ubuntu jammy

# CT 110 auf dem Node "pve01" anlegen
pct create 110 local:vztmpl/ubuntu-24.04-standard-24.04-2.10 \
    --hostname jtl-mcp \
    --cores 2 \
    --memory 2048 \
    --swap 512 \
    --rootfs local-lvm:8 \
    --net0 name=eth0,bridge=vmbr0,ip=10.10.10.20/24,gw=10.10.10.1 \
    --unprivileged 1 \
    --features nesting=1 \
    --onboot 1
```

Empfehlungen:

| Ressource | Wert | Begruendung |
|---|---|---|
| CPU | 2 vCPU | httpx-Async-Client, Last ist I/O-gebunden |
| RAM | 2 GB | Python + FastMCP reichen mit ~150 MB |
| Platte | 8 GB | Python-Umgebung und Logs |
| `features=nesting=1` | optional | nur noetig, falls Docker im CT eingesetzt wird |

Der Container braucht **keine** oeffentliche IP. Der Zugriff erfolgt
ausschliesslich intern (LiteLLM-Host bzw. Admin-Client).

## 2. Netzwerk und Firewall

Firewall-Regel im Container (nur interner Zugriff):

```bash
pct set 110 --firewall 1
pct exec 110 -- bash -c 'apt-get update && apt-get install -y ufw'
pct exec 110 -- bash -c 'ufw default deny incoming && ufw allow from 10.10.10.0/24 to any port 8080 proto tcp && ufw enable'
```

Zusaetzlich in der Proxmox-Firewall (Host) eine Regel nur fuer das
LiteLLM-Segment:

```
IN ACCEPT -p tcp -s 10.10.10.30/32 --dport 8080 -m state --state NEW
```

## 3. JTL-Wawi-API erreichbar

Der MCP-Server spricht die **JTL-Wawi API** (`JTL.Wawi.Rest.exe`) an, die auf
dem Windows-Host mit der Wawi-Datenbank laeuft (Standardport 5883):

1. In JTL-Wawi: `Admin -> Benutzer / Rechte -> Benutzer` -> Benutzer waehlen ->
   `Key erzeugen` -> API-Key kopieren (GUID).
2. In JTL-Wawi: `Admin -> Globale Einstellungen -> Server Einstellungen` bzw. im
   JTL-Administrator eine API-Instanz anlegen und starten.
3. Firewall auf dem Windows-Host: Port 5883 nur vom LXC freigeben.

Verbindungstest aus dem Container:

```bash
curl -sS -u ":" -H "Authorization: bearer $(printf '%s' '<API-KEY>' | base64)" \
    http://10.10.20.10:5883/api/eazybusiness/v1/feature | head -c 300
```

## 4. Installation

Auf dem Container:

```bash
# Pakete
apt-get update && apt-get install -y python3 python3-venv python3-pip curl rsync

# Projekt kopieren (z. B. via git clone oder scp)
cd /root
git clone <repository> jtl-mcp-server
cd jtl-mcp-server

# Installieren (legt Benutzer, venv, systemd-Unit und Dienst an)
sudo ./deploy/install.sh
```

Anschliessend `/etc/jtl-mcp-server/.env` bearbeiten:

```bash
nano /etc/jtl-mcp-server/.env
```

```ini
JTL_BASE_URL=http://10.10.20.10:5883
JTL_API_PATH=/api/eazybusiness/v1
JTL_API_KEY=<GUID aus JTL-Wawi>
MCP_SERVER_AUTH_TOKEN=<openssl rand -hex 32>
```

Danach:

```bash
systemctl restart jtl-mcp-server
MCP_SERVER_AUTH_TOKEN=<token> ./deploy/healthcheck.sh http://127.0.0.1:8080/mcp
```

## 5. Betrieb

```bash
systemctl status jtl-mcp-server          # Status
journalctl -u jtl-mcp-server -f          # Live-Logs
systemctl restart jtl-mcp-server         # Neustart
```

Der MCP-Endpunkt laeuft auf `http://<container-ip>:8080/mcp` (Streamable HTTP).

## 6. Absicherung

* MCP-Port nur im internen Netz freigeben (siehe Firewall oben).
* `MCP_SERVER_AUTH_TOKEN` ist ein statisches Token: regelmaessig rotieren und
  in LiteLLM (`auth_value`) nachziehen.
* Der Dienst laeuft als eigener System-Benutzer `jtl-mcp` mit
  systemd-Hardening (`ProtectSystem=strict`, `NoNewPrivileges`, leere
  Capability-Liste).
* TLS: Der MCP-Port laeuft unverschluesselt im internen Netz. Terminal-VPN
  (Tailscale/WireGuard) oder einen TLS-Reverse-Proxy (nginx/Caddy) davor
  setzen, wenn das Netz nicht als vertrauenswuerdig gilt.
* JTL-Wawi-seitig nur Leserechte des API-Benutzers vergeben und den
  API-Key regelmaessig erneuern.

## 7. Update

```bash
cd /root/jtl-mcp-server && git pull
sudo ./deploy/install.sh --no-start
sudo systemctl restart jtl-mcp-server
```

Die Konfiguration in `/etc/jtl-mcp-server/.env` bleibt dabei erhalten.
