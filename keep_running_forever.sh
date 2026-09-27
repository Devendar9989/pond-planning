#!/bin/bash
# ==============================================================================
# PondPlan AI — Auto-Restarting Watchdog Loop for Uninterrupted Availability
# Monitors internal ports 6000 (public 6241), 5000 (public 5241), and 3000 (public 3241)
# ==============================================================================

TARGET_DIR="/home/student/pond_panning"
cd "${TARGET_DIR}"

echo "[$(date)] Starting PondPlan AI Multi-Port Watchdog Daemon..."

while true; do
    # Check Port 6000 (Public: 6241)
    if ! curl -s http://127.0.0.1:6000/health | grep -q "ok"; then
        echo "[$(date)] Port 6000 down. Restarting..."
        fuser -k -9 6000/tcp 2>/dev/null || true
        nohup ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 6000 --workers 1 > server_6000.log 2>&1 &
    fi

    # Check Port 5000 (Public: 5241)
    if ! curl -s http://127.0.0.1:5000/health | grep -q "ok"; then
        echo "[$(date)] Port 5000 down. Restarting..."
        fuser -k -9 5000/tcp 2>/dev/null || true
        nohup ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 5000 --workers 1 > server_5000.log 2>&1 &
    fi

    # Check Port 3000 (Public: 3241)
    if ! curl -s http://127.0.0.1:3000/health | grep -q "ok"; then
        echo "[$(date)] Port 3000 down. Restarting..."
        fuser -k -9 3000/tcp 2>/dev/null || true
        nohup ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 3000 --workers 1 > server_3000.log 2>&1 &
    fi

    sleep 5
done
