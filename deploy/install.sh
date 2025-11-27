#!/bin/bash
# Tilt UI Installation Script
# Installs Tilt UI as a systemd service on Raspberry Pi

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

INSTALL_DIR="/opt/tiltui"
SERVICE_FILE="/etc/systemd/system/tiltui.service"
REPO_URL="https://github.com/yourusername/tilt_ui.git"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Tilt UI Installation Script${NC}"
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

echo -e "\n${GREEN}[1/7] Installing system dependencies...${NC}"
apt-get update
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    bluetooth \
    bluez \
    libbluetooth-dev \
    libcap2-bin \
    git

# Ensure Bluetooth is enabled
echo -e "\n${GREEN}[2/7] Configuring Bluetooth...${NC}"
systemctl enable bluetooth
systemctl start bluetooth

# Stop existing service if running
if systemctl is-active --quiet tiltui; then
    echo -e "\n${YELLOW}Stopping existing Tilt UI service...${NC}"
    systemctl stop tiltui
fi

# Create install directory
echo -e "\n${GREEN}[3/7] Setting up installation directory...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/data"

# Copy files (assuming script is run from project root or deploy dir)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -d "$PROJECT_DIR/backend" ]; then
    echo "Installing from local project..."
    cp -r "$PROJECT_DIR/backend" "$INSTALL_DIR/"
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
echo -e "\n${GREEN}[4/7] Setting up Python environment...${NC}"
cd "$INSTALL_DIR"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate

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
        httpx \
        aioblescan
fi

deactivate

# Set capabilities for BLE scanning
echo -e "\n${GREEN}[5/7] Setting Bluetooth capabilities...${NC}"
setcap 'cap_net_raw,cap_net_admin+eip' "$INSTALL_DIR/.venv/bin/python3" || true

# Set ownership
echo -e "\n${GREEN}[6/7] Setting permissions...${NC}"
chown -R pi:pi "$INSTALL_DIR"
chmod 755 "$INSTALL_DIR"
chmod 700 "$INSTALL_DIR/data"

# Install systemd service
echo -e "\n${GREEN}[7/7] Installing systemd service...${NC}"
cp "$SCRIPT_DIR/tiltui.service" "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable tiltui
systemctl start tiltui

# Verify service started
sleep 3
if systemctl is-active --quiet tiltui; then
    echo -e "\n${GREEN}========================================${NC}"
    echo -e "${GREEN}  Installation Complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "Tilt UI is now running at: ${GREEN}http://$(hostname -I | awk '{print $1}')${NC}"
    echo ""
    echo "Useful commands:"
    echo "  - View logs:    journalctl -u tiltui -f"
    echo "  - Restart:      sudo systemctl restart tiltui"
    echo "  - Stop:         sudo systemctl stop tiltui"
    echo "  - Status:       sudo systemctl status tiltui"
else
    echo -e "\n${RED}Service failed to start. Check logs:${NC}"
    echo "  journalctl -u tiltui -n 50"
    exit 1
fi
