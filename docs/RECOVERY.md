# FosOS Desktop recovery and rollback

FosOS Desktop is the only full desktop session. When it fails, use
**FosOS Recovery** on the LightDM greeter (Openbox + terminal) or a text
console. XFCE is not shipped.

## Switch to FosOS Recovery at the next login

1. Sign out (Start → Sign out), or press Ctrl+Alt+F2 and reboot if the
   graphical session is stuck.
2. On the LightDM greeter, open the session menu.
3. Choose **FosOS Recovery**.
4. Sign in. A terminal opens with restart hints. Run `fosos-shell` to try
   the panel again, or `openbox --exit` to return to the greeter.

LightDM remembers the last session per account in `~/.dmrc`. Choose
**FosOS Desktop** again when you want the full shell.

## Text console

1. Press Ctrl+Alt+F2 (or F3…F6).
2. Sign in with your account.
3. Diagnose or repair packages, then return with Ctrl+Alt+F1:

```bash
fos update
fos upgrade
# or
sudo apt update
sudo apt install --reinstall fosos-desktop
sudo systemctl restart lightdm
```

On the live image the account is `user` / password `live`.

## Shell crashed (no taskbar)

Openbox may still be running. Keybindings still work:

| Keys | Action |
| --- | --- |
| Ctrl+Alt+T | Terminal |
| Super+E | Files |
| openbox --exit | Sign out |

If the shell gave up after repeated crashes, FosOS opens a recovery terminal
and writes `~/.config/fosos-desktop/shell-failed`. In that terminal:

```bash
fosos-shell
```

If it keeps dying, sign out and use **FosOS Recovery** or a TTY, then update.

## Lock screen will not unlock

1. Switch to a text console with Ctrl+Alt+F2.
2. Sign in with your account.
3. End the locker and return to the graphical seat:

```bash
pkill -x fosos-lock
sudo loginctl unlock-sessions
```

4. Switch back with Ctrl+Alt+F1. If the session is still stuck, reboot:
   `sudo systemctl reboot`.

## Restore FosOS Desktop as the default

```bash
# /etc/lightdm/lightdm.conf.d/50-fosos-default-session.conf
[Seat:*]
user-session=fosos-desktop
```

That file ships in the `fosos-desktop` package.

## Roll back a bad package upgrade

```bash
# From FosOS Recovery or a TTY
apt-cache policy fosos-desktop
sudo apt install fosos-desktop=<previous-version>
```

Prefer promoting only packages that passed the [testing guide](TESTING.md)
soak. ISOs are for fresh installs; day-to-day fixes come through APT.

## When to file a bug

Collect `~/.config/fosos-desktop/shell-failed`, the output of
`journalctl --user -b`, and whether FosOS Recovery still works. Reinstall or
USB tests must not use a disk that holds data you need.
