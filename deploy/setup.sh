#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Framer QA — Oracle Cloud Ubuntu 22.04 ARM setup script
# Run once as the ubuntu user after first SSH into the server:
#   bash setup.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

REPO="https://github.com/farismuhtadi/framer-qa.git"
APP_DIR="/home/ubuntu/framer-qa"
SERVICE_NAME="framer-qa"
PORT=8080

echo "════════════════════════════════════════"
echo "  Framer QA — Server Setup"
echo "════════════════════════════════════════"

# ── 1. System packages ────────────────────────────────────────────────────────
echo ""
echo "→ Updating system packages..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq

echo "→ Installing Python 3, pip, git, and build tools..."
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv python3-dev \
    git curl wget unzip \
    build-essential libssl-dev libffi-dev \
    # Playwright system dependencies
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2

# ── 2. Clone repo ─────────────────────────────────────────────────────────────
echo ""
echo "→ Cloning repository..."
if [ -d "$APP_DIR" ]; then
    echo "  Directory exists — pulling latest instead"
    cd "$APP_DIR" && git pull origin main
else
    git clone "$REPO" "$APP_DIR"
    cd "$APP_DIR"
fi

# ── 3. Python virtualenv + dependencies ───────────────────────────────────────
echo ""
echo "→ Creating Python virtual environment..."
python3 -m venv "$APP_DIR/venv"
source "$APP_DIR/venv/bin/activate"

echo "→ Installing Python dependencies..."
pip install --upgrade pip --quiet
pip install -r "$APP_DIR/requirements.txt" --quiet

# ── 4. Playwright browser ─────────────────────────────────────────────────────
echo ""
echo "→ Installing Playwright Chromium (this may take a minute)..."
playwright install chromium
playwright install-deps chromium

# ── 5. Persistent reports directory ───────────────────────────────────────────
echo ""
echo "→ Creating persistent reports directory..."
mkdir -p "$APP_DIR/reports"

# ── 6. Systemd service ────────────────────────────────────────────────────────
echo ""
echo "→ Installing systemd service..."
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<EOF
[Unit]
Description=Framer QA Agent
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=${APP_DIR}
Environment="PORT=${PORT}"
Environment="PYTHONUNBUFFERED=1"
ExecStart=${APP_DIR}/venv/bin/gunicorn \\
    --workers 2 \\
    --bind 0.0.0.0:${PORT} \\
    --timeout 600 \\
    --keep-alive 5 \\
    --log-level info \\
    "app:app"
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"

# ── 7. Firewall ───────────────────────────────────────────────────────────────
echo ""
echo "→ Opening port ${PORT} in the OS firewall..."
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport "$PORT" -j ACCEPT
# Make the rule persist across reboots
sudo apt-get install -y -qq iptables-persistent
sudo netfilter-persistent save

# ── 8. Done ───────────────────────────────────────────────────────────────────
echo ""
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || echo "<your-server-ip>")
echo "════════════════════════════════════════"
echo "  ✅ Setup complete!"
echo ""
echo "  App running at: http://${SERVER_IP}:${PORT}"
echo ""
echo "  Useful commands:"
echo "    sudo systemctl status ${SERVICE_NAME}   # check app status"
echo "    sudo journalctl -u ${SERVICE_NAME} -f   # live logs"
echo "    sudo systemctl restart ${SERVICE_NAME}  # restart app"
echo "════════════════════════════════════════"
