"""Configuration management for raindrops daemon."""

import os
import json
from pathlib import Path

CONFIG_DIR = os.path.expanduser("~/.config/raindrops")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
SOCKET_FILE = os.path.join(CONFIG_DIR, "daemon.sock")
PID_FILE = os.path.join(CONFIG_DIR, "raindrops.pid")
LOG_FILE = os.path.join(CONFIG_DIR, "raindrops.log")
MPV_SOCKET = "/tmp/raindrops_mpv.sock"

DEFAULT_AUDIO_DIR = os.path.expanduser("~/Downloads/raindrops")

DEFAULT_CONFIG = {
    "audio_dir": DEFAULT_AUDIO_DIR,
    "volume": 65,
    "fade_duration": 2.0,
    "poll_interval": 1.0,
    "auto_pause": True,
    "resume_delay": 2.0,
    "slots": {
        "morning": {"start": 6, "end": 12},
        "afternoon": {"start": 12, "end": 18},
        "night": {"start": 18, "end": 6}
    }
}


def ensure_config_dir():
    """Ensure ~/.config/raindrops exists."""
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load_config() -> dict:
    """Load configuration from disk, creating default if missing."""
    ensure_config_dir()
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # Ensure all default keys exist
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
    except Exception:
        return DEFAULT_CONFIG.copy()


def save_config(cfg: dict):
    """Save configuration dictionary to disk."""
    ensure_config_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)
