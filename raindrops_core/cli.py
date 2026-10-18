"""CLI interface and control client for raindrops."""

import os
import sys
import time
import json
import socket
import argparse
import subprocess
from datetime import datetime
from typing import Optional

from .config import PID_FILE, SOCKET_FILE, LOG_FILE, CONFIG_FILE, load_config
from .daemon import RaindropsDaemon


def send_daemon_request(action: str, **kwargs) -> Optional[dict]:
    """Connect to running daemon control socket and send request."""
    if not os.path.exists(SOCKET_FILE):
        return None

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(SOCKET_FILE)

        payload = {"action": action, **kwargs}
        s.sendall((json.dumps(payload) + "\n").encode("utf-8"))

        data = s.recv(8192).decode("utf-8")
        s.close()
        if data:
            return json.loads(data.splitlines()[0])
        return None
    except Exception:
        return None


def is_daemon_running() -> bool:
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            # Check if PID exists
            os.kill(pid, 0)
            return True
        except (OSError, ValueError):
            return False
    return False


def get_daemon_pid() -> Optional[int]:
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None
    return None


def cmd_start(args):
    if is_daemon_running():
        print(f"\033[33m● Raindrops daemon is already running (PID: {get_daemon_pid()})\033[0m")
        return

    # If foreground requested
    if getattr(args, "foreground", False):
        print("\033[36m🌧  Starting Raindrops daemon in foreground...\033[0m")
        daemon = RaindropsDaemon(foreground=True)
        daemon.run()
        return

    # Start detached in background
    script_path = os.path.abspath(sys.argv[0])
    print("\033[36m🌧  Starting Raindrops background daemon...\033[0m")

    # Run `raindrops run` in background
    proc = subprocess.Popen(
        [sys.executable, script_path, "run"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True
    )

    # Wait up to 3 seconds for daemon to initialize socket
    for _ in range(30):
        if is_daemon_running() and os.path.exists(SOCKET_FILE):
            print(f"\033[32m✔ Raindrops daemon started successfully (PID: {get_daemon_pid()})\033[0m")
            cmd_status(args)
            return
        time.sleep(0.1)

    print("\033[33mDaemon launched. Check 'raindrops status' or logs at ~/.config/raindrops/raindrops.log\033[0m")


def cmd_stop(args):
    if not is_daemon_running():
        print("\033[33m● Raindrops daemon is not running.\033[0m")
        return

    print("Stopping Raindrops daemon...")
    res = send_daemon_request("stop")
    if res and res.get("status") == "ok":
        time.sleep(0.5)

    # If process still alive, send SIGTERM
    pid = get_daemon_pid()
    if pid and is_daemon_running():
        try:
            os.kill(pid, 15)  # SIGTERM
            time.sleep(0.5)
        except OSError:
            pass

    if not is_daemon_running():
        print("\033[32m✔ Raindrops daemon stopped.\033[0m")
    else:
        print("\033[31mFailed to stop daemon cleanly. Check PID.\033[0m")


def cmd_restart(args):
    cmd_stop(args)
    time.sleep(1)
    cmd_start(args)


def cmd_toggle(args):
    if not is_daemon_running():
        print("\033[31mRaindrops daemon is not running. Start with 'raindrops start'.\033[0m")
        return

    res = send_daemon_request("toggle")
    if res:
        msg = res.get("message", "Toggled")
        state_icon = "⏸" if res.get("paused") else "▶"
        print(f"\033[36m{state_icon} {msg}\033[0m")
    else:
        print("\033[31mFailed to communicate with daemon socket.\033[0m")


def cmd_next(args):
    if not is_daemon_running():
        print("\033[31mRaindrops daemon is not running. Start with 'raindrops start'.\033[0m")
        return

    res = send_daemon_request("next")
    if res:
        print(f"\033[36m⏭  {res.get('message', 'Switched track')}\033[0m")
    else:
        print("\033[31mFailed to communicate with daemon socket.\033[0m")


def cmd_volume(args):
    if not is_daemon_running():
        print("\033[31mRaindrops daemon is not running. Start with 'raindrops start'.\033[0m")
        return

    if args.level is not None:
        res = send_daemon_request("volume", value=args.level)
        if res:
            print(f"\033[32m✔ Volume set to {res.get('volume')}%\033[0m")
    else:
        res = send_daemon_request("volume")
        if res:
            print(f"Volume: {res.get('volume')}%")


def format_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def cmd_status(args):
    if not is_daemon_running():
        print("\033[33m● Raindrops daemon: Inactive (Stopped)\033[0m")
        print("  Start with: \033[36mraindrops start\033[0m")
        return

    data = send_daemon_request("status")
    if not data:
        print(f"\033[33m● Raindrops daemon: Running (PID: {get_daemon_pid()}) but socket is unresponsive.\033[0m")
        return

    pid = data.get("pid")
    state = data.get("state", "unknown")
    slot = data.get("slot", "").capitalize()
    track = data.get("track", "None")
    pos = data.get("position", 0)
    dur = data.get("duration", 0)
    vol = data.get("volume", 0)

    # State badge
    if "playing" in state:
        state_badge = f"\033[32m▶ {state.upper()}\033[0m"
    else:
        state_badge = f"\033[33m⏸ {state.upper()}\033[0m"

    # Progress bar
    bar_width = 24
    if dur > 0:
        filled = int((pos / dur) * bar_width)
        bar = "━" * filled + "╸" + "─" * max(0, bar_width - filled - 1)
        time_str = f"{format_time(pos)} / {format_time(dur)}"
    else:
        bar = "─" * bar_width
        time_str = "--:-- / --:--"

    current_hour_str = datetime.now().strftime("%H:%M")

    print("\n\033[1;36m🌧  Raindrops Ambient Audio Daemon\033[0m")
    print("──────────────────────────────────────────")
    print(f" Status:       {state_badge} (PID: {pid})")
    print(f" Time of Day:  \033[1m{slot}\033[0m (Current Clock: {current_hour_str})")
    print(f" Track:        \033[34m{track}\033[0m")
    print(f" Progress:     [{bar}] {time_str}")
    print(f" Volume:       {vol}%")
    print("──────────────────────────────────────────")

    catalog = data.get("catalog", {})
    folders = catalog.get("folders", {})
    if folders:
        folder_list = ", ".join([f"{f}: {cnt}" for f, cnt in folders.items()])
        print(f" Audio tracks: {folder_list} (Total: {catalog.get('total_tracks', 0)})")
    print()


def main():
    parser = argparse.ArgumentParser(
        prog="raindrops",
        description="Raindrops - Dynamic time-of-day ambient rain sound daemon"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # start
    p_start = subparsers.add_parser("start", help="Start raindrops background daemon")
    p_start.add_argument("-f", "--foreground", action="store_true", help="Run in foreground")

    # run (internal / service)
    subparsers.add_parser("run", help=argparse.SUPPRESS)

    # stop
    subparsers.add_parser("stop", help="Stop raindrops daemon")

    # restart
    subparsers.add_parser("restart", help="Restart raindrops daemon")

    # toggle
    subparsers.add_parser("toggle", help="Pause / resume audio playback")

    # next
    subparsers.add_parser("next", help="Skip to next random track for current time slot")

    # status
    subparsers.add_parser("status", help="Show daemon status, current track, and volume")

    # volume
    p_vol = subparsers.add_parser("volume", help="Get or set playback volume (0-100)")
    p_vol.add_argument("level", type=int, nargs="?", default=None, help="Volume level (0-100)")

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(args)
    elif args.command == "run":
        daemon = RaindropsDaemon(foreground=True)
        daemon.run()
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "restart":
        cmd_restart(args)
    elif args.command == "toggle":
        cmd_toggle(args)
    elif args.command == "next":
        cmd_next(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "volume":
        cmd_volume(args)
    else:
        # Default to status if running, or help
        if is_daemon_running():
            cmd_status(args)
        else:
            parser.print_help()


if __name__ == "__main__":
    main()
