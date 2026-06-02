#!/bin/bash
set -e

# Start Visual Desktop if enabled
if [ "$VISUAL_DESKTOP" = "1" ]; then
    echo "Starting Visual Desktop Streaming..."
    
    # Clean up old locks
    rm -f /tmp/.X99-lock
    
    # 1. Start X virtual framebuffer
    Xvfb :99 -screen 0 1280x800x24 -ac &
    XVFB_PID=$!
    
    # Wait for Xvfb to be ready
    sleep 2
    
    # 2. Start a lightweight window manager (fluxbox)
    DISPLAY=:99 fluxbox &
    
    # 3. Start x11vnc server (listening on 5900)
    x11vnc -display :99 -forever -shared -nopw -quiet -listen localhost -xkb &
    
    # 4. Start websockify (WebSocket to TCP proxy for noVNC, listening on 6080)
    websockify --web /usr/share/novnc 6080 localhost:5900 &
    
    echo "Visual Desktop available at ws://localhost:6080"
fi

# Execute the main command (e.g., python run.py)
exec "$@"
