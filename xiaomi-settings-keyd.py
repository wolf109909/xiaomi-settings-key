#!/usr/bin/env python3
"""Xiaomi Book 14 settings-key daemon.

Watches the "Xiaomi Book 14 Settings Key" input device (created by the
xiaomi-book14 kernel module from XGNS mailbox events EVFN 0x25/0x26) and
runs a configurable command on each keypress.

The device is grabbed exclusively (EVIOCGRAB): the keycode KEY_CONFIG maps
to XF86Tools, which many desktops pre-bind (KDE opens System Settings).

Command resolution (first hit wins):
  1. $XIAOMI_SETTINGS_KEY_CMD (path to a script)
  2. <session user>/.config/xiaomi-settings-key/command.sh
  3. /etc/xiaomi-settings-key/command.sh   (shipped default: konsole)

The command runs inside the active graphical session (Wayland or X11) as
that session's user. The session user is auto-detected via loginctl, or
forced with $XIAOMI_KEY_USER.
"""

import os
import pwd
import re
import struct
import subprocess
import sys
import time

DEVICE_NAME = "Xiaomi Book 14 Settings Key"
KEY_CONFIG = 171  # EV_KEY code reported by the module
SYSTEM_COMMAND = "/etc/xiaomi-settings-key/command.sh"
DEFAULT_COMMAND = "konsole\n"

EVENT_STRUCT = "llHHi"  # struct input_event: timeval, type, code, value
EVENT_SIZE = struct.calcsize(EVENT_STRUCT)
EVIOCGRAB = 0x40044590  # _IOC(_IOC_WRITE, 'E', 0x90, sizeof(int))


def find_event_node():
    """Locate /dev/input/eventN for our device via /proc/bus/input/devices."""
    try:
        with open("/proc/bus/input/devices") as f:
            blocks = f.read().split("\n\n")
        for block in blocks:
            if f'N: Name="{DEVICE_NAME}"' in block:
                m = re.search(r"event(\d+)", block)
                if m:
                    return f"/dev/input/event{m.group(1)}"
    except OSError:
        pass
    return None


def detect_session_user():
    """User of the active graphical session (Class=user, Type=wayland/x11)."""
    forced = os.environ.get("XIAOMI_KEY_USER")
    if forced:
        return forced
    try:
        out = subprocess.run(
            ["loginctl", "list-sessions", "--no-legend"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        for line in out.splitlines():
            sid = line.split()[0]
            props = subprocess.run(
                ["loginctl", "show-session", sid,
                 "-p", "Class", "-p", "Type", "-p", "Name", "-p", "Active"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            p = dict(l.split("=", 1) for l in props.splitlines() if "=" in l)
            if (p.get("Class") == "user" and p.get("Active") == "yes"
                    and p.get("Type") in ("wayland", "x11")):
                return p.get("Name")
    except (OSError, subprocess.SubprocessError, IndexError):
        pass
    return None


def session_environ(uid):
    """Clone the graphical session's environment from a live user process.

    Lets launched apps (konsole) pick up the real theme/scale/DBus setup,
    identical to launching from the desktop itself.
    """
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            if os.stat(f"/proc/{pid}").st_uid != uid:
                continue
            with open(f"/proc/{pid}/environ", "rb") as f:
                raw = f.read()
            env = dict(
                item.split(b"=", 1)
                for item in raw.split(b"\0")
                if b"=" in item
            )
            if (b"DBUS_SESSION_BUS_ADDRESS" in env
                    and (b"WAYLAND_DISPLAY" in env or b"DISPLAY" in env)):
                clean = {k.decode(): v.decode() for k, v in env.items()}
                # fd-inheritance vars are only valid for the process itself
                for k in ("WAYLAND_SOCKET", "LISTEN_FDS", "LISTEN_PID",
                          "LISTEN_FDNAMES"):
                    clean.pop(k, None)
                return clean
        except (OSError, UnicodeDecodeError):
            continue
    return None


def resolve_command(user):
    env_cmd = os.environ.get("XIAOMI_SETTINGS_KEY_CMD")
    if env_cmd:
        return env_cmd
    if user:
        user_cmd = os.path.join(
            pwd.getpwnam(user).pw_dir, ".config/xiaomi-settings-key/command.sh")
        if os.path.exists(user_cmd):
            return user_cmd
    return SYSTEM_COMMAND


def run_command():
    if os.geteuid() != 0:
        # unprivileged mode: just run the user's own config
        cmd = resolve_command(None)
        argv, env = ["/bin/sh", cmd], None
    else:
        user = detect_session_user()
        if not user:
            print("no active graphical session; ignoring press",
                  file=sys.stderr, flush=True)
            return
        uid = pwd.getpwnam(user).pw_uid
        env = session_environ(uid)
        if env is None:  # no live session process: minimal fallback
            env = {
                "HOME": pwd.getpwnam(user).pw_dir,
                "XDG_RUNTIME_DIR": f"/run/user/{uid}",
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{uid}/bus",
                "WAYLAND_DISPLAY": "wayland-0",
                "DISPLAY": ":0",
            }
        cmd = resolve_command(user)
        argv = ["runuser", "-u", user, "--", "/bin/sh", cmd]
    try:
        subprocess.Popen(argv, env=env)
        print(f"ran {cmd} as {user if os.geteuid() == 0 else 'self'}",
              flush=True)
    except OSError as e:
        print(f"failed to run {cmd}: {e}", file=sys.stderr, flush=True)


def ensure_user_default():
    """Unprivileged mode only: seed ~/.config default on first run."""
    path = os.path.expanduser("~/.config/xiaomi-settings-key/command.sh")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(DEFAULT_COMMAND)
        os.chmod(path, 0o755)


def main():
    if os.geteuid() != 0:
        ensure_user_default()
    while True:
        node = find_event_node()
        if node is None:
            time.sleep(2)
            continue
        try:
            fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            time.sleep(2)
            continue
        try:
            import fcntl
            fcntl.ioctl(fd, EVIOCGRAB, 1)  # exclusive: DE never sees the key
        except OSError as e:
            print(f"EVIOCGRAB failed: {e}", file=sys.stderr, flush=True)
        print(f"watching {node}", flush=True)
        try:
            import select
            while True:
                r, _, _ = select.select([fd], [], [], 5)
                if fd not in r:
                    continue
                data = os.read(fd, EVENT_SIZE * 8)
                if len(data) < EVENT_SIZE:
                    break  # device gone (module reload)
                for off in range(0, len(data) - EVENT_SIZE + 1, EVENT_SIZE):
                    _, _, ev_type, code, value = struct.unpack_from(
                        EVENT_STRUCT, data, off)
                    if ev_type == 1 and code == KEY_CONFIG and value == 1:
                        print("settings key pressed", flush=True)
                        run_command()
        except OSError:
            pass
        finally:
            os.close(fd)
        time.sleep(1)  # re-scan for the device


if __name__ == "__main__":
    main()
