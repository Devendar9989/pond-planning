#!/bin/bash
# ==============================================================================
# PondPlan AI — Master Background Deployment Across All Allowed Ports
# Port Mapping:
# Internal Port 6000 -> Public URL: http://10.1.75.51:6241/
# Internal Port 5000 -> Public URL: http://10.1.75.51:5241/
# Internal Port 3000 -> Public URL: http://10.1.75.51:3241/
# Internal Port 4000 -> Public URL: http://10.1.75.51:4241/
# ==============================================================================

set -e
TARGET_DIR="/home/student/pond_panning"

echo "🛑 [1/4] Terminating all old group-chat, supervisor, and load balancer processes..."
killall -9 group-chat 2>/dev/null || true
killall -9 lb 2>/dev/null || true
pkill -9 -f "supervisor" 2>/dev/null || true
pkill -9 -f "group-chat" 2>/dev/null || true
pkill -9 -f "run_lb" 2>/dev/null || true
pkill -9 -f "start_lb" 2>/dev/null || true
pkill -9 -f "deploy_lb" 2>/dev/null || true
pkill -9 -f "native_submitter" 2>/dev/null || true
pkill -9 -f "uvicorn" 2>/dev/null || true

# Free all allowed ports (2000, 3000, 4000, 5000, 6000, 7000)
for p in 3000 4000 5000 6000 7000; do
    fuser -k -9 ${p}/tcp 2>/dev/null || true
done
sleep 1

echo "📂 [2/4] Navigating to ${TARGET_DIR}..."
cd "${TARGET_DIR}"

echo "🐍 [3/4] Ensuring Python virtual environment is configured..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
./venv/bin/pip install --upgrade pip >/dev/null 2>&1 || true
./venv/bin/pip install -r requirements.txt >/dev/null 2>&1 || true

echo "🚀 [4/4] Launching PondPlan AI services across internal ports (6000, 5000, 3000)..."

# Launch on Port 6000 (Exposed at http://10.1.75.51:6241/)
nohup ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 6000 --workers 1 > server_6000.log 2>&1 &

# Launch on Port 5000 (Exposed at http://10.1.75.51:5241/)
nohup ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 5000 --workers 1 > server_5000.log 2>&1 &

# Launch on Port 3000 (Exposed at http://10.1.75.51:3241/)
nohup ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 3000 --workers 1 > server_3000.log 2>&1 &

sleep 2

echo ""
echo "================================================================================"
echo "🎉 PondPlan AI is now running in the background across all mapped public ports!"
echo ""
echo "🌐 PRIMARY FRONT-END URL:     http://10.1.75.51:6241/  (Internal Port: 6000)"
echo "🌐 ALTERNATIVE FRONT-END URL: http://10.1.75.51:5241/  (Internal Port: 5000)"
echo "🌐 ALTERNATIVE FRONT-END URL: http://10.1.75.51:3241/  (Internal Port: 3000)"
echo ""
echo "📚 Swagger API Docs:          http://10.1.75.51:6241/docs"
echo "================================================================================"
echo ""
echo "Testing local health checks:"
curl -s http://127.0.0.1:6000/health && echo " (Port 6000 OK)"
curl -s http://127.0.0.1:5000/health && echo " (Port 5000 OK)"
curl -s http://127.0.0.1:3000/health && echo " (Port 3000 OK)"
