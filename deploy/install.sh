#!/bin/bash
# BrewSignal Installation Script
# Installs BrewSignal as a systemd service on Raspberry Pi

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

INSTALL_DIR="/opt/brewsignal"
SERVICE_FILE="/etc/systemd/system/brewsignal.service"
REPO_URL="https://github.com/machug/brewsignal.git"
VENV_DIR="$INSTALL_DIR/.venv"
FRONTEND_DIR="$INSTALL_DIR/frontend"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  BrewSignal Installation Script${NC}"
echo -e "${GREEN}========================================${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root (sudo ./install.sh)${NC}"
    exit 1
fi

# Check for Raspberry Pi
if ! grep -q "Raspberry Pi\|BCM" /proc/cpuinfo 2>/dev/null; then
    echo -e "${YELLOW}Warning: This doesn't appear to be a Raspberry Pi${NC}"
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo -e "\n${GREEN}[1/8] Installing system dependencies...${NC}"
apt-get update
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    nodejs \
    npm \
    bluetooth \
    bluez \
    libbluetooth-dev \
    libcap2-bin \
    git

# Ensure Bluetooth is enabled
echo -e "\n${GREEN}[2/8] Configuring Bluetooth...${NC}"
systemctl enable bluetooth
systemctl start bluetooth

# Stop existing service if running
if systemctl is-active --quiet brewsignal; then
    echo -e "\n${YELLOW}Stopping existing BrewSignal service...${NC}"
    systemctl stop brewsignal
fi

# Create install directory
echo -e "\n${GREEN}[3/8] Setting up installation directory...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/data"

# Copy files (assuming script is run from project root or deploy dir)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -d "$PROJECT_DIR/backend" ]; then
    echo "Installing from local project..."
    cp -r "$PROJECT_DIR/backend" "$INSTALL_DIR/"
    cp -r "$PROJECT_DIR/frontend" "$INSTALL_DIR/" 2>/dev/null || true
    cp "$PROJECT_DIR/pyproject.toml" "$INSTALL_DIR/" 2>/dev/null || true
else
    echo "Cloning from repository..."
    if [ -d "$INSTALL_DIR/.git" ]; then
        cd "$INSTALL_DIR"
        git pull
    else
        rm -rf "$INSTALL_DIR"
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
fi

# Set up Python virtual environment
echo -e "\n${GREEN}[4/8] Setting up Python environment...${NC}"
cd "$INSTALL_DIR"

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

# Install dependencies
if [ -f "pyproject.toml" ]; then
    pip install --upgrade pip
    pip install uv
    uv pip install -e .
else
    pip install --upgrade pip
    pip install \
        fastapi \
        uvicorn[standard] \
        sqlalchemy[asyncio] \
        aiosqlite \
        httpx
fi

deactivate

# Build frontend assets
echo -e "\n${GREEN}[5/8] Building frontend assets...${NC}"
if [ -d "$FRONTEND_DIR" ]; then
    if ! command -v npm >/dev/null 2>&1; then
        echo -e "${YELLOW}npm is not installed; skipping frontend build. Make sure backend/static has prebuilt assets.${NC}"
    else
        cd "$FRONTEND_DIR"
        rm -rf node_modules
        npm ci
        npm run build
        cd "$INSTALL_DIR"
    fi
else
    echo "Frontend source not found; assuming prebuilt assets exist in backend/static."
fi

# Set capabilities for BLE scanning
echo -e "\n${GREEN}[6/8] Setting Bluetooth capabilities...${NC}"
setcap 'cap_net_raw,cap_net_admin+eip' "$VENV_DIR/bin/python3" || true

# Set ownership
echo -e "\n${GREEN}[7/8] Setting permissions...${NC}"
chown -R pi:pi "$INSTALL_DIR"
chmod 755 "$INSTALL_DIR"
chmod 700 "$INSTALL_DIR/data"

# Install systemd service
echo -e "\n${GREEN}[8/8] Installing systemd service...${NC}"
cp "$SCRIPT_DIR/brewsignal.service" "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable brewsignal
systemctl start brewsignal

# Verify service started
sleep 3
if systemctl is-active --quiet brewsignal; then
    echo -e "\n${GREEN}========================================${NC}"
    echo -e "${GREEN}  Installation Complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "BrewSignal is now running at: ${GREEN}http://$(hostname -I | awk '{print $1}')${NC}"
    echo ""
    echo "Useful commands:"
    echo "  - View logs:    journalctl -u brewsignal -f"
    echo "  - Restart:      sudo systemctl restart brewsignal"
    echo "  - Stop:         sudo systemctl stop brewsignal"
    echo "  - Status:       sudo systemctl status brewsignal"
else
    echo -e "\n${RED}Service failed to start. Check logs:${NC}"
    echo "  journalctl -u brewsignal -n 50"
    exit 1
fi
