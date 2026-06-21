#!/bin/bash
set -e

# ── Virtual display ────────────────────────────────────────────────────────
Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &
sleep 2

# ── VNC server ────────────────────────────────────────────────────────────
x11vnc -display :99 -nopw -listen 0.0.0.0 -rfbport 5900 \
        -forever -shared -bg -quiet
sleep 1

# ── noVNC websocket proxy ─────────────────────────────────────────────────
websockify --web /usr/share/novnc/ 6080 localhost:5900 &

export DISPLAY=:99

echo ""
echo "=================================================="
echo "  IS Claim Automation — Docker"
echo "  Dashboard  →  http://localhost:5000"
echo "  Browser    →  http://localhost:6080/vnc.html"
echo "=================================================="
echo ""

cd /app/src/v1
exec python -u dashboard_is_claim.py
