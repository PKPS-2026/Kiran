#!/bin/bash
set -e

# ── Virtual display (Chrome needs a screen) ──────────────────────────
Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &
sleep 2

# ── VNC server on port 5900 (localhost) ──────────────────────────────
x11vnc -display :99 -nopw -listen 0.0.0.0 -rfbport 5900 \
        -forever -shared -bg -quiet
sleep 1

# ── noVNC websocket proxy → port 6080 ────────────────────────────────
websockify --web /usr/share/novnc/ 6080 localhost:5900 &

export DISPLAY=:99

echo ""
echo "=================================================="
echo "  KCC Loan Automation — Docker"
echo "  Dashboard  →  http://localhost:5000"
echo "  Browser    →  http://localhost:6080/vnc.html"
echo "=================================================="
echo ""

# ── Start Flask dashboard (V4) ────────────────────────────────────────
cd /app/src/v4
exec python -u dashboard_v4.py
