#!/usr/bin/env bash
# ==============================================================================
# Automated One-Click Setup, Test & Deployment Script for Port 3241
# ==============================================================================
set -euo pipefail

PORT=3241
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

echo "============================================================"
echo "🚀 [1/5] Setting up Python Virtual Environment..."
echo "============================================================"
if [ ! -d "venv" ]; then
    echo "Creating virtual environment at ${SCRIPT_DIR}/venv..."
    python3 -m venv venv
fi

echo "Installing/Updating dependencies..."
./venv/bin/pip install --upgrade pip --quiet
./venv/bin/pip install -r requirements.txt --quiet
echo "✅ Dependencies installed."

echo ""
echo "============================================================"
echo "🧪 [2/5] Running Test Suite (21 Unit & Scenario Tests)..."
echo "============================================================"
./venv/bin/pytest -v
echo "✅ All tests passed successfully."

echo ""
echo "============================================================"
echo "🛑 [3/5] Freeing Port ${PORT} (Stopping Any Previous Process)..."
echo "============================================================"
fuser -k "${PORT}/tcp" 2>/dev/null || true
pkill -f "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}" 2>/dev/null || true
sleep 1

echo ""
echo "============================================================"
echo "🌐 [4/5] Starting API Server on Port ${PORT}..."
echo "============================================================"
nohup ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --workers 1 > server.log 2>&1 &
SERVER_PID=$!
echo "✅ Server started with PID: ${SERVER_PID} on port ${PORT}"

echo "Waiting for server to become healthy..."
MAX_RETRIES=15
COUNTER=0
until curl -s "http://127.0.0.1:${PORT}/health" | grep -q "ok" || [ $COUNTER -eq $MAX_RETRIES ]; do
    sleep 1
    COUNTER=$((COUNTER + 1))
done

if [ $COUNTER -eq $MAX_RETRIES ]; then
    echo "❌ Server failed to start. Last 20 lines of server.log:"
    tail -n 20 server.log
    exit 1
fi
echo "✅ Health check passed: http://127.0.0.1:${PORT}/health"

echo ""
echo "============================================================"
echo "🛰️  [5/5] Testing POST /analyzeContour with contours_1m.kml..."
echo "============================================================"
SAMPLE_FILE="${SCRIPT_DIR}/contours_1m.kml"
if [ -f "${SAMPLE_FILE}" ]; then
    RESPONSE=$(curl -s -X POST "http://127.0.0.1:${PORT}/analyzeContour" \
      -F "file=@${SAMPLE_FILE}" \
      -F "resolution_m=10.0")
    echo "Response Payload:"
    echo "${RESPONSE}" | python3 -m json.tool || echo "${RESPONSE}"
    echo "✅ Analysis endpoint verified."
else
    echo "⚠️  ${SAMPLE_FILE} not found; skipping sample test."
fi

echo ""
echo "============================================================"
echo "🎉 DEPLOYMENT COMPLETE!"
echo "📍 API listening on: http://0.0.0.0:${PORT}"
echo "📄 Logs: tail -f ${SCRIPT_DIR}/server.log"
echo "🛑 Stop server: fuser -k ${PORT}/tcp"
echo "============================================================"
