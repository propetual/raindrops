"""Background daemon implementation for raindrops ambient audio service."""

import os
import sys
import time
import json
import socket
import select
import signal
import logging
import threading
from datetime import datetime
from typing import Optional

from .config import (
    load_config, save_config, SOCKET_FILE, PID_FILE, LOG_FILE, MPV_SOCKET
)
from .scheduler import AudioScheduler
from .player import MpvPlayer
from .detector import MediaDetector


class RaindropsDaemon:
    def __init__(self, foreground: bool = False):
        self.foreground = foreground
        self.running = False
        self.config = load_config()

        self._setup_logging()
        self.scheduler = AudioScheduler(self.config["audio_dir"], self.config["slots"])
        self.player = MpvPlayer(
            MPV_SOCKET,
            default_volume=self.config.get("volume", 65),
            fade_duration=self.config.get("fade_duration", 2.0)
        )
        self.detector = MediaDetector(
            resume_delay=self.config.get("resume_delay", 2.0),
            ignore_players="mpv"
        )

        self.manually_paused = False
        self.auto_paused = False
        self.current_track: Optional[str] = None
        self.server_sock: Optional[socket.socket] = None
        self.lock = threading.Lock()

    def _setup_logging(self):
        log_level = logging.INFO
        handlers = [logging.FileHandler(LOG_FILE, encoding="utf-8")]
        if self.foreground:
            handlers.append(logging.StreamHandler(sys.stdout))

        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=handlers
        )

    def write_pid(self):
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))

    def remove_pid(self):
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except OSError:
                pass

    def setup_control_socket(self):
        if os.path.exists(SOCKET_FILE):
            try:
                os.remove(SOCKET_FILE)
            except OSError:
                pass

        self.server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_sock.bind(SOCKET_FILE)
        self.server_sock.listen(5)
        self.server_sock.setblocking(False)

    def cleanup(self):
        logging.info("Shutting down raindrops daemon...")
        self.running = False

        if self.player.is_running():
            try:
                self.player.fade_to(0, duration=0.6, blocking=True)
            except Exception:
                pass
            self.player.stop()

        if self.server_sock is not None:
            try:
                self.server_sock.close()
            except Exception:
                pass

        if os.path.exists(SOCKET_FILE):
            try:
                os.remove(SOCKET_FILE)
            except OSError:
                pass

        self.remove_pid()
        logging.info("Shutdown complete.")

    def handle_signal(self, signum, frame):
        logging.info(f"Received signal {signum}, initiating graceful exit.")
        self.running = False

    def play_next_track(self, fade_in: bool = True):
        with self.lock:
            track = self.scheduler.pick_next_track()
            if not track:
                logging.warning(f"No audio tracks found in {self.scheduler.audio_dir}")
                return

            slot = self.scheduler.get_current_slot()
            logging.info(f"Transitioning to new track [{slot}]: {os.path.basename(track)}")
            if self.player.is_running() and self.current_track:
                self.player.fade_to(0, duration=0.8, blocking=True)

            self.current_track = track
            self.player.play_file(track, fade_in=fade_in)

            if self.manually_paused or self.auto_paused:
                self.player.pause()

    def get_status_dict(self) -> dict:
        with self.lock:
            pos = self.player.get_property("time-pos")
            duration = self.player.get_property("duration")
            slot = self.scheduler.get_current_slot()
            summary = self.scheduler.get_catalog_summary()

            state = "playing"
            if self.manually_paused:
                state = "paused (user)"
            elif self.auto_paused:
                state = "paused (external media playing)"

            return {
                "running": True,
                "pid": os.getpid(),
                "state": state,
                "slot": slot,
                "track": os.path.basename(self.current_track) if self.current_track else None,
                "track_path": self.current_track,
                "position": round(pos, 1) if pos is not None else 0,
                "duration": round(duration, 1) if duration is not None else 0,
                "volume": self.player.target_volume,
                "auto_paused": self.auto_paused,
                "manually_paused": self.manually_paused,
                "catalog": summary
            }

    def process_client_command(self, client_sock: socket.socket):
        try:
            client_sock.settimeout(1.5)
            data = client_sock.recv(4096).decode("utf-8")
            if not data:
                return

            cmd_obj = json.loads(data)
            action = cmd_obj.get("action", "")
            response = {"status": "ok"}

            if action == "status":
                response = self.get_status_dict()

            elif action == "toggle":
                with self.lock:
                    if self.manually_paused:
                        self.manually_paused = False
                        if not self.auto_paused:
                            self.player.resume()
                            self.player.fade_to(self.player.target_volume, duration=1.0, start_vol=0, blocking=False)
                        response["message"] = "Resumed"
                    else:
                        self.manually_paused = True
                        self.player.fade_to(0, duration=0.8, blocking=True)
                        self.player.pause()
                        response["message"] = "Paused"
                    response["paused"] = self.manually_paused

            elif action == "next":
                self.play_next_track(fade_in=True)
                response["message"] = f"Playing {os.path.basename(self.current_track or '')}"

            elif action == "volume":
                new_vol = cmd_obj.get("value")
                if new_vol is not None:
                    with self.lock:
                        new_vol = max(0, min(100, int(new_vol)))
                        self.player.set_target_volume(new_vol)
                        self.config["volume"] = new_vol
                        save_config(self.config)
                        response["volume"] = new_vol
                else:
                    response["volume"] = self.player.target_volume

            elif action == "stop":
                response["message"] = "Stopping daemon"
                client_sock.sendall((json.dumps(response) + "\n").encode("utf-8"))
                self.running = False
                return

            else:
                response = {"status": "error", "message": f"Unknown command: {action}"}

            client_sock.sendall((json.dumps(response) + "\n").encode("utf-8"))
        except Exception as e:
            logging.error(f"Error handling client command: {e}")
        finally:
            try:
                client_sock.close()
            except Exception:
                pass

    def run(self):
        """Main daemon loop."""
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)

        self.write_pid()
        self.setup_control_socket()
        self.running = True

        logging.info("Raindrops daemon starting up...")
        self.player.start_process()
        self.play_next_track(fade_in=True)

        poll_interval = self.config.get("poll_interval", 1.0)

        while self.running:
            try:
                # 1. Check for incoming CLI control connections
                readable, _, _ = select.select([self.server_sock], [], [], 0.3)
                if readable:
                    client, _ = self.server_sock.accept()
                    self.process_client_command(client)

                if not self.running:
                    break

                # 2. Check external media conflicts (auto-ducking)
                if self.config.get("auto_pause", True):
                    media_active = self.detector.should_pause()

                    if media_active and not self.auto_paused:
                        logging.info("External media detected. Auto-pausing rain...")
                        self.auto_paused = True
                        if not self.manually_paused:
                            self.player.fade_to(0, duration=1.0, blocking=True)
                            self.player.pause()

                    elif not media_active and self.auto_paused:
                        logging.info("External media stopped. Resuming rain...")
                        self.auto_paused = False
                        if not self.manually_paused:
                            self.player.resume()
                            self.player.fade_to(self.player.target_volume, duration=1.5, start_vol=0, blocking=False)

                # 3. Check if track finished (mpv idle or eof)
                if not self.manually_paused and not self.auto_paused:
                    if self.player.is_idle():
                        logging.info("Current track reached end. Picking next track...")
                        self.play_next_track(fade_in=True)

            except Exception as e:
                logging.error(f"Error in daemon loop: {e}", exc_info=True)
                time.sleep(poll_interval)

        self.cleanup()
