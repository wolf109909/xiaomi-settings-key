# xiaomi-settings-key — userspace handler for the Xiaomi Book Pro 14 "settings" key

Makes the dedicated **settings key** (top-right of the keyboard, next to the
power button) on the Xiaomi Book Pro 14 2026 useful on Linux: each press runs
a **user-configurable command** (default: `konsole`).

Requires the sibling **[xiaomi-book14-dkms](../xiaomi-book14-dkms)** kernel
module, which turns the EC hotkey into an input device
(`Xiaomi Book 14 Settings Key`, keycode `KEY_CONFIG`).

## Hardware event path (reverse engineered)

The settings key is an **EC hotkey**, not a regular keyboard-matrix scancode:

1. Press → EC firmware writes the **XGNS mailbox** (shared BIOS↔OS block,
   phys `0x6FDB8000`, defined in SSDT24 `WMID`):
   - `EVTP` (off `0x24`) = `0x01` (hotkey class)
   - `EVFN` (off `0x25`) = `0x25` on **press**, `0x26` on **release**
2. On Windows, the EC also raises an EC query (`_Q15` press / `_Q16` release);
   the AML handler calls `WMID.QV20(1, 0x25|0x26)` → `Notify(WMID, 0x20)` →
   WMI event GUID `46C93E13-EE9B-4262-8488-563BCA757FEF`, which Xiaomi PC
   Manager consumes (`_WED(0x20)` → `EVBU = [1, EVFN, data]`).
3. On Linux the AML path is dead (`ECON` undefined → ACPI EC never binds),
   but the EC writes the mailbox **independently of** AML, so polling the
   mailbox is sufficient — no WMI, no EC driver needed.

Verified by live capture: `dmesg` shows
`xiaomi_book14: mbox event: EVTP=01 EVFN=25` on press and `EVFN=26` on
release (hold repeats `0x25`, release emits `0x26`). The kernel module polls
the mailbox every 50 ms (`mbox_poll_ms`) because the EC only holds `EVFN`
for the duration of the physical press; a slower poll would miss quick taps.
Measured: 12/12 typing-speed taps detected end-to-end.

## Why a daemon instead of a desktop keybinding

`KEY_CONFIG` (171) maps to `XF86Tools`, which KDE Plasma (and other DEs)
pre-bind — Plasma opens System Settings. This daemon **grabs the input
device exclusively** (`EVIOCGRAB`), so the desktop never sees the key and
only your command runs.

## What it does

- Finds the `Xiaomi Book 14 Settings Key` device by name
  (survives module reloads / changing event nodes).
- On each keypress, runs the configured command **inside the active graphical
  session** (Wayland or X11) as that session's user, with the session's full
  environment cloned (correct theme, scaling, DBus) — apps behave exactly as
  if launched from the desktop.
- Session user is auto-detected via `loginctl` (works for any logged-in
  user, not hardcoded).

## Install (Arch / CachyOS)

```sh
git clone <this repo>
cd xiaomi-settings-key
makepkg -si
sudo systemctl enable --now xiaomi-settings-key.service
```

The package installs:
- `/usr/bin/xiaomi-settings-keyd` — the daemon
- `/usr/lib/systemd/system/xiaomi-settings-key.service` — system service
- `/usr/lib/udev/rules.d/99-xiaomi-settings-key.rules` — `uaccess` tag on the
  device (allows unprivileged/user-service use if desired)
- `/etc/xiaomi-settings-key/command.sh` — default command (`konsole`)

## Configuration

Command resolution (first hit wins):

1. `$XIAOMI_SETTINGS_KEY_CMD` (environment override, useful for testing)
2. `~/.config/xiaomi-settings-key/command.sh` of the session user
3. `/etc/xiaomi-settings-key/command.sh` (system default)

The file is executed with `/bin/sh` on every keypress. Examples:

```sh
konsole                                   # default
notify-send "Settings key" "Hello"        # test
my-toggle-script.sh                       # anything
```

Force a specific user instead of auto-detection: set `XIAOMI_KEY_USER=<name>`
in the service (`systemctl edit xiaomi-settings-key`).

## Logs / debugging

```sh
journalctl -u xiaomi-settings-key.service -f
evtest /dev/input/eventN   # device "Xiaomi Book 14 Settings Key", code 171
dmesg | grep 'mbox event'  # EVFN=25 press / EVFN=26 release
```

## Uninstall

```sh
sudo systemctl disable --now xiaomi-settings-key.service
sudo pacman -R xiaomi-settings-key
```

## License

GPL-2.0-or-later
