#!/usr/bin/env bash
# Raindrops installer script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_TARGET="$HOME/.local/bin/raindrops"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_TARGET="$SERVICE_DIR/raindrops.service"

echo "🌧 Installing Raindrops..."

# 1. Symlink executable
mkdir -p "$HOME/.local/bin"
ln -sf "$SCRIPT_DIR/raindrops" "$BIN_TARGET"
chmod +x "$SCRIPT_DIR/raindrops"
echo "✔ Symlinked binary to $BIN_TARGET"

# 2. Install systemd user service
mkdir -p "$SERVICE_DIR"
cp "$SCRIPT_DIR/systemd/raindrops.service" "$SERVICE_TARGET"
systemctl --user daemon-reload
echo "✔ Installed systemd service to $SERVICE_TARGET"

echo ""
echo "Raindrops is ready!"
echo "Commands:"
echo "  raindrops start       # Start in background"
echo "  raindrops status      # View currently playing rain & stats"
echo "  raindrops toggle      # Pause / resume playback"
echo "  raindrops next        # Skip to next random rain track"
echo "  raindrops volume 70   # Change volume"
echo "  raindrops stop        # Stop daemon"
echo ""
echo "To automatically start Raindrops on system boot/login:"
echo "  systemctl --user enable --now raindrops"
