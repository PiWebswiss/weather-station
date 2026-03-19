#!/bin/bash
# ============================================================
# Weather Station Pi — UFW Firewall Setup
# ============================================================
# Allows:
#   - SSH (port 22)           — remote admin
#   - HTTP (port 80)          — local network access only
#   - HTTPS (port 443)        — Cloudflare tunnel & direct HTTPS
#   - Outbound (all)          — needed for weather API calls
# Blocks everything else inbound.
# ============================================================

set -e

echo "=== InkyPi Firewall Setup ==="
echo ""

# Check root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Please run as root (sudo ./setup_firewall.sh)"
    exit 1
fi

# Install ufw if not present
if ! command -v ufw &>/dev/null; then
    echo "[1/6] Installing ufw..."
    apt-get update -qq && apt-get install -y ufw
else
    echo "[1/6] ufw already installed."
fi

# Reset to defaults (keeps rules clean)
echo "[2/6] Resetting ufw rules to defaults..."
ufw --force reset

# Default policies
echo "[3/6] Setting default policies (deny in, allow out)..."
ufw default deny incoming
ufw default allow outgoing

# Allow SSH — critical: do this BEFORE enabling ufw
echo "[4/6] Allowing SSH (port 22)..."
ufw allow 22/tcp comment 'SSH remote admin'

# Allow HTTP — for local network access when no HTTPS tunnel is running
echo "      Allowing HTTP (port 80) — local access..."
ufw allow 80/tcp comment 'HTTP local network'

# Allow HTTPS — for Cloudflare tunnel and direct HTTPS connections
echo "      Allowing HTTPS (port 443)..."
ufw allow 443/tcp comment 'HTTPS / Cloudflare tunnel'

# Enable ufw
echo "[5/6] Enabling firewall..."
ufw --force enable

# Show status
echo ""
echo "[6/6] Firewall status:"
ufw status verbose

echo ""
echo "=== Done ==="
echo ""
echo "Active rules summary:"
echo "  SSH  (22/tcp)  : OPEN — remote administration"
echo "  HTTP (80/tcp)  : OPEN — local network (no HTTPS tunnel)"
echo "  HTTPS(443/tcp) : OPEN — Cloudflare tunnel / direct HTTPS"
echo "  All other inbound traffic : BLOCKED"
echo ""
echo "RECOMMENDATION: Once your Cloudflare tunnel is running,"
echo "you can block port 80 to force HTTPS-only:"
echo "  sudo ufw delete allow 80/tcp"
echo "  sudo ufw allow from 127.0.0.1 to any port 80"
echo "(This keeps HTTP for localhost only, blocking external HTTP access.)"
echo ""
echo "See DEVLOG.md for Cloudflare tunnel setup instructions."
