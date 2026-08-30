#!/usr/bin/env bash
# Deployment script for 512MB RAM / 1 vCPU / 1.5GB Storage Linux Target Box
set -euo pipefail

APP_DIR="/opt/pond-api"
SERVICE_NAME="pond-api"

echo "=== [1/6] Configuring 1GB Swap File for Memory Safety ==="
if [ ! -f /swapfile ]; then
    echo "Creating 1GB swapfile..."
    sudo fallocate -l 1G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=1024
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "Swap created successfully."
else
    echo "Swapfile already exists."
fi

echo "=== [2/6] Setting Up Application Directory ==="
sudo mkdir -p "${APP_DIR}"
sudo rsync -av --exclude 'venv' --exclude '__pycache__' --exclude '.pytest_cache' --exclude '.git' ./ "${APP_DIR}/"
sudo chown -R ubuntu:ubuntu "${APP_DIR}"

echo "=== [3/6] Creating Python Virtual Environment ==="
cd "${APP_DIR}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

echo "=== [4/6] Installing Pinned Dependencies (No Cache to Save Disk) ==="
./venv/bin/pip install --upgrade pip
./venv/bin/pip install --no-cache-dir -r requirements.txt

echo "=== [5/6] Installing Systemd Service ==="
sudo cp deploy/pond-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

echo "=== [6/6] Verifying API Health ==="
sleep 3
if curl -s -f http://127.0.0.1:8000/health > /dev/null; then
    echo "✅ Pond Catchment Analysis API is up and healthy on http://127.0.0.1:8000"
else
    echo "❌ Health check failed. Inspect logs with: journalctl -u ${SERVICE_NAME} -n 50 --no-pager"
    exit 1
fi
