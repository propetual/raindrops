"""Time-based scheduling and audio file indexing for raindrops."""

import os
import random
from datetime import datetime
from typing import Dict, List, Optional

AUDIO_EXTENSIONS = {".wav", ".ogg", ".mp3", ".flac", ".m4a", ".aac", ".opus"}


class AudioScheduler:
    def __init__(self, audio_dir: str, slots_config: dict):
        self.audio_dir = os.path.expanduser(audio_dir)
        self.slots_config = slots_config
        self.recent_history: List[str] = []
        self.history_limit = 3

    def rescan(self) -> Dict[str, List[str]]:
        """Scan audio directory and group valid audio files by subfolder name."""
        catalog: Dict[str, List[str]] = {}
        if not os.path.isdir(self.audio_dir):
            return catalog

        for entry in os.scandir(self.audio_dir):
            if entry.is_dir():
                sub_files = []
                for root, _, files in os.walk(entry.path):
                    for f in files:
                        ext = os.path.splitext(f)[1].lower()
                        if ext in AUDIO_EXTENSIONS:
                            sub_files.append(os.path.join(root, f))
                if sub_files:
                    catalog[entry.name.lower()] = sorted(sub_files)

        # Also check root directory for any loose audio files
        root_files = []
        for entry in os.scandir(self.audio_dir):
            if entry.is_file():
                ext = os.path.splitext(entry.name)[1].lower()
                if ext in AUDIO_EXTENSIONS:
                    root_files.append(entry.path)
        if root_files:
            catalog["_root"] = sorted(root_files)

        return catalog

    def get_current_slot(self, now: Optional[datetime] = None) -> str:
        """Determine slot name based on current hour."""
        if now is None:
            now = datetime.now()
        hour = now.hour

        # Check configured slots
        for slot_name, hours in self.slots_config.items():
            start = hours.get("start", 0)
            end = hours.get("end", 24)
            if start < end:
                if start <= hour < end:
                    return slot_name
            else:
                # Wraps around midnight (e.g. 18 to 6)
                if hour >= start or hour < end:
                    return slot_name

        # Fallback based on standard 3-period day
        if 6 <= hour < 12:
            return "morning"
        elif 12 <= hour < 18:
            return "afternoon"
        return "night"

    def pick_next_track(self, slot_override: Optional[str] = None) -> Optional[str]:
        """Pick a random track suited for the current time slot."""
        catalog = self.rescan()
        if not catalog:
            return None

        slot = (slot_override or self.get_current_slot()).lower()
        candidates: List[str] = []

        # Exact match or substring match (e.g. '1_morning' matching 'morning')
        for folder_name, files in catalog.items():
            if folder_name == slot or slot in folder_name:
                candidates.extend(files)

        # Fallback to any folder if no candidates found
        if not candidates:
            for folder_name, files in catalog.items():
                candidates.extend(files)

        if not candidates:
            return None

        # Filter out recently played tracks if possible
        pool = [c for c in candidates if c not in self.recent_history]
        if not pool:
            pool = candidates

        chosen = random.choice(pool)
        self.recent_history.append(chosen)
        if len(self.recent_history) > self.history_limit:
            self.recent_history.pop(0)

        return chosen

    def get_catalog_summary(self) -> dict:
        """Return catalog stats and folder track counts."""
        catalog = self.rescan()
        summary = {
            "current_slot": self.get_current_slot(),
            "audio_dir": self.audio_dir,
            "folders": {folder: len(files) for folder, files in catalog.items()},
            "total_tracks": sum(len(files) for files in catalog.values())
        }
        return summary
