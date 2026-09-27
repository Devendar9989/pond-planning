#!/bin/bash
# ==============================================================================
# PondPlan AI — Master Startup & Clean Deployment Script for Remote Server
# Stops old group-chat / load balancer services and starts Pond Planning on Port 3241
# ==============================================================================

set -e

echo "🛑 [1/5] Stopping all previous group chat and load balancer processes..."
pkill -f "group-chat" 2>/dev/null || true
pkill -f "run_lb" 2>/dev/null || true
pkill -f "supervisor_lb" 2>/dev/null || true
pkill -f "start_lb" 2>/dev/null || true
pkill -f "deploy_lb" 2>/dev/null || true
pkill -f "native_submitter" 2>/dev/null || true
pkill -f "uvicorn" 2>/dev/null || true
fuser -k 3241/tcp 2>/dev/null || true
fuser -k 3000/tcp 2>/dev/null || true
sleep 2

TARGET_DIR="/home/student/pond_panning"
echo "📂 [2/5] Navigating to ${TARGET_DIR}..."
cd "${TARGET_DIR}"

echo "🐍 [3/5] Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

echo "🧪 [4/5] Running automated tests (23 tests)..."
./venv/bin/pytest -v

echo "🚀 [5/5] Launching PondPlan AI server on Port 3241 & Port 3000..."
nohup ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 3241 --workers 1 > server_3241.log 2>&1 &
nohup ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 3000 --workers 1 > server_3000.log 2>&1 &

sleep 3

echo ""
echo "=================================================================="
echo "✅ PondPlan AI is now live!"
echo "🌐 Front-End URL: http://10.1.75.51:3241/"
echo "📚 Swagger API:  http://10.1.75.51:3241/docs"
echo "=================================================================="
echo ""
echo "Testing health endpoint:"
curl -s http://127.0.0.1:3241/health || echo "Starting..."
echo ""
