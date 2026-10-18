"""External media detection using playerctl (MPRIS) for media ducking/auto-pause."""

import subprocess
import time
from typing import Optional


class MediaDetector:
    def __init__(self, resume_delay: float = 2.0, ignore_players: Optional[str] = "mpv"):
        self.resume_delay = resume_delay
        self.ignore_players = ignore_players
        self.last_media_active_time: Optional[float] = None

    def is_external_media_playing(self) -> bool:
        """Check if any external media player is currently playing."""
        cmd = ["playerctl"]
        if self.ignore_players:
            cmd.extend([f"--ignore-player={self.ignore_players}"])
        cmd.extend(["-a", "status"])

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
            if res.returncode == 0:
                statuses = [line.strip().lower() for line in res.stdout.strip().splitlines() if line.strip()]
                return any(s == "playing" for s in statuses)
            return False
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return False

    def should_pause(self) -> bool:
        """Returns True if raindrops should be paused due to media playback."""
        is_playing = self.is_external_media_playing()
        now = time.time()

        if is_playing:
            self.last_media_active_time = now
            return True

        # If media recently stopped, hold pause until resume_delay has elapsed
        if self.last_media_active_time is not None:
            if (now - self.last_media_active_time) < self.resume_delay:
                return True
            else:
                self.last_media_active_time = None

        return False
