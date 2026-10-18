#  Raindrops

> A lightweight, dynamic time-of-day  rain sound daemon for Linux.

Raindrops runs silently in the background, smoothly playing rain sounds that change with the time of day—gentle morning drizzles, energized afternoon showers, and soft nightly pitter-patters. It automatically ducks or pauses whenever you play music or watch videos in your browser, and seamlessly resumes when your media stops.

---

##  Features

- ** Time-of-Day Rain Progression:**
  - `Morning` (06:00 – 12:00): Gentle drizzle and moderate rain.
  - `Afternoon` (12:00 – 18:00): Energized showers and heavy rain.
  - `Night` (18:00 – 06:00): Heavy rain dying down to calm night pitter-patter.
- ** Headless Background Playback:** Powered by headless `mpv` through a Unix IPC socket. Zero terminal windows, completely unobtrusive across all virtual workspaces.
- **⏸ Smart Media Ducking (Auto-Pause):** Automatically pauses rain when browser videos, YouTube, Spotify, or VLC start playing via `playerctl` (MPRIS), and smoothly fades rain back in when media stops.
- ** Smooth Volume Fading:** Non-blocking cinematic volume fades between tracks, pauses, and resumes—no harsh audio cut-offs.
- ** Full CLI Control:** Intuitive terminal command dashboard (`raindrops status`, `toggle`, `next`, `volume`, `start`, `stop`).
- ** Systemd Service Integration:** Run automatically on boot/login via a systemd user unit.

---

##  Quick Start

### 1. Requirements
Ensure you have Python 3 and MPV installed:
```bash
# Arch Linux
sudo pacman -S mpv python playerctl
```

### 2. Audio Folder Structure
Organize your audio files into subfolders corresponding to the time slots:
```text
~/Downloads/raindrops/
├── morning/        # e.g. morning_1.ogg, morning_2.wav
├── afternoon/      # e.g. afternoon_1.mp3, afternoon_2.flac
└── night/          # e.g. night_1.mp3, night_2.m4a
```
*(Supports `.wav`, `.ogg`, `.mp3`, `.flac`, `.m4a`)*.

### 3. Install & Link
Run the installer to link `raindrops` to `~/.local/bin` and install the systemd unit:
```bash
./install.sh
```

---

##  CLI Usage

```bash
raindrops start          # Start background daemon
raindrops status         # Show status, current track, time slot & progress bar
raindrops toggle         # Pause or resume rain sounds
raindrops next           # Skip to next random track for the current time slot
raindrops volume 60      # Set volume level (0-100)
raindrops stop           # Stop background daemon
```

### Terminal Status Dashboard
Running `raindrops status` outputs a clean status card:
```text
🌧  Raindrops Ambient Audio Daemon
──────────────────────────────────────────
 Status:       ▶ PLAYING (PID: 25830)
 Time of Day:  Night (Current Clock: 21:32)
 Track:        night_2.wav
 Progress:     [━━━╸────────────────────] 01:15 / 09:41
 Volume:       50%
──────────────────────────────────────────
 Audio tracks: afternoon: 3, morning: 3, night: 2 (Total: 8)
```

---

##  Run Automatically at Login

Enable the systemd user service so Raindrops starts with your session:
```bash
systemctl --user enable --now raindrops
```

To stop or disable:
```bash
systemctl --user stop raindrops
systemctl --user disable raindrops
```

---

##  Configuration

Custom configuration is automatically stored at `~/.config/raindrops/config.json`:
```json
{
    "audio_dir": "/home/place/Downloads/raindrops",
    "volume": 65,
    "fade_duration": 2.0,
    "poll_interval": 1.0,
    "auto_pause": true,
    "resume_delay": 2.0,
    "slots": {
        "morning": {"start": 6, "end": 12},
        "afternoon": {"start": 12, "end": 18},
        "night": {"start": 18, "end": 6}
    }
}
```

---

##  Roadmap & Future Ideas

- [ ] Connect with Open-Meteo or wttr.in to blend real-time outdoor local weather into the diurnal simulation.
- [ ] ASCII weather & rain status widget for `eww` / Waybar / Polybar.
- [ ] Dynamic ambient rain video wallpapers synced with desktop wallpaper.
- [ ] AI generative rain audio soundscapes.

---

##  License

MIT
