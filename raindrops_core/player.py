"""Headless MPV player controller with IPC socket communication and smooth volume fading."""

import os
import json
import time
import socket
import threading
import subprocess
from typing import Any, Optional


class MpvPlayer:
    def __init__(self, socket_path: str, default_volume: int = 65, fade_duration: float = 2.0):
        self.socket_path = socket_path
        self.default_volume = default_volume
        self.target_volume = default_volume
        self.current_volume = default_volume
        self.fade_duration = fade_duration
        self.process: Optional[subprocess.Popen] = None
        self.current_file: Optional[str] = None
        self._sock: Optional[socket.socket] = None
        self._sock_lock = threading.Lock()
        self._fade_thread: Optional[threading.Thread] = None
        self._fade_cancel_event = threading.Event()

    def start_process(self):
        """Start mpv in background headless mode with IPC socket."""
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except OSError:
                pass

        cmd = [
            "mpv",
            "--no-video",
            "--idle",
            "--really-quiet",
            f"--input-ipc-server={self.socket_path}",
            f"--volume={self.target_volume}"
        ]

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        # Wait for socket to become available
        for _ in range(30):
            if os.path.exists(self.socket_path):
                break
            time.sleep(0.1)

    def _get_socket(self) -> socket.socket:
        """Get or reconnect IPC socket."""
        if self._sock is not None:
            return self._sock

        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(self.socket_path)
        self._sock = s
        return self._sock

    def _close_socket(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def send_command(self, cmd: list) -> dict:
        """Send an IPC command to mpv and return the parsed JSON response."""
        with self._sock_lock:
            for attempt in range(2):
                try:
                    s = self._get_socket()
                    msg = json.dumps({"command": cmd}) + "\n"
                    s.sendall(msg.encode("utf-8"))

                    # Read response until newline
                    buf = ""
                    while "\n" not in buf:
                        chunk = s.recv(4096).decode("utf-8")
                        if not chunk:
                            raise ConnectionResetError("Empty socket response")
                        buf += chunk

                    first_line = buf.splitlines()[0]
                    return json.loads(first_line)
                except Exception:
                    self._close_socket()
                    if attempt == 0 and self.is_running():
                        time.sleep(0.15)
                        continue
                    return {"error": "socket_error"}
            return {"error": "socket_error"}

    def is_running(self) -> bool:
        """Check if mpv process is alive."""
        if self.process is None:
            return False
        return self.process.poll() is None

    def ensure_running(self):
        """Ensure mpv process and socket are active."""
        if not self.is_running():
            self._close_socket()
            self.start_process()

    def get_property(self, name: str) -> Any:
        res = self.send_command(["get_property", name])
        if res.get("error") == "success":
            return res.get("data")
        return None

    def set_property(self, name: str, val: Any) -> bool:
        res = self.send_command(["set_property", name, val])
        if name == "volume" and res.get("error") == "success":
            try:
                self.current_volume = int(val)
            except (ValueError, TypeError):
                pass
        return res.get("error") == "success"

    def is_idle(self) -> bool:
        idle = self.get_property("idle-active")
        return bool(idle)

    def is_paused(self) -> bool:
        paused = self.get_property("pause")
        return bool(paused)

    def pause(self):
        self.set_property("pause", True)

    def resume(self):
        self.set_property("pause", False)

    def set_target_volume(self, volume: int):
        self.target_volume = max(0, min(100, volume))
        self.set_property("volume", self.target_volume)

    def _fade_worker(self, start_v: int, end_v: int, duration: float, cancel_event: threading.Event):
        """Worker thread for non-blocking smooth volume interpolation."""
        if start_v == end_v or duration <= 0:
            self.set_property("volume", end_v)
            return

        steps = max(5, int(duration * 20))
        sleep_interval = duration / steps
        delta = (end_v - start_v) / steps

        for i in range(1, steps + 1):
            if cancel_event.is_set():
                break
            vol = int(round(start_v + delta * i))
            vol = max(0, min(100, vol))
            self.set_property("volume", vol)
            time.sleep(sleep_interval)

        if not cancel_event.is_set():
            self.set_property("volume", end_v)

    def fade_to(self, end_vol: int, duration: Optional[float] = None, start_vol: Optional[int] = None, blocking: bool = False):
        """Fade volume smoothly to end_vol."""
        if duration is None:
            duration = self.fade_duration

        # Cancel any previous running fade
        self._fade_cancel_event.set()
        if self._fade_thread and self._fade_thread.is_alive():
            self._fade_thread.join(timeout=0.2)

        self._fade_cancel_event = threading.Event()

        if start_vol is None:
            mpv_vol = self.get_property("volume")
            start_vol = int(mpv_vol) if mpv_vol is not None else self.current_volume

        start_v = max(0, min(100, int(start_vol)))
        end_v = max(0, min(100, int(end_vol)))

        if blocking or duration <= 0:
            self._fade_worker(start_v, end_v, duration, self._fade_cancel_event)
        else:
            self._fade_thread = threading.Thread(
                target=self._fade_worker,
                args=(start_v, end_v, duration, self._fade_cancel_event),
                daemon=True
            )
            self._fade_thread.start()

    def play_file(self, file_path: str, fade_in: bool = True):
        """Load and start playing an audio file with optional fade-in."""
        self.ensure_running()
        if fade_in:
            self.set_property("volume", 0)

        # 'replace' replaces playlist and immediately starts playback
        self.send_command(["loadfile", file_path, "replace"])
        self.resume()
        self.current_file = file_path

        if fade_in:
            self.fade_to(self.target_volume, duration=self.fade_duration, start_vol=0, blocking=False)
        else:
            self.set_property("volume", self.target_volume)

    def stop(self):
        """Cleanly terminate mpv process and remove socket."""
        self._fade_cancel_event.set()
        try:
            self.send_command(["quit"])
        except Exception:
            pass
        self._close_socket()

        if self.process is not None:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None

        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except OSError:
                pass
