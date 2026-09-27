#!/bin/bash
# ==============================================================================
# PondPlan AI — Endless Watchdog Supervisor
# Keeps Pond Planning running on Port 3241 and restarts automatically if killed
# ==============================================================================

PORT=3241
TARGET_DIR="/home/student/pond_panning"

cd "${TARGET_DIR}"

echo "Starting Pond Planning watchdog loop on port ${PORT}..."

while true; do
    echo "[$(date)] Starting PondPlan AI uvicorn instance..."
    ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 >> server_3241.log 2>&1 || true
    echo "[$(date)] PondPlan AI exited. Restarting in 2 seconds..."
    sleep 2
done
