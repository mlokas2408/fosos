# FosOS Desktop recovery and rollback

FosOS Desktop is the only full desktop session. When it fails, use
**FosOS Recovery** on the LightDM greeter (Openbox + terminal) or a text
console. XFCE is not shipped.

## Switch to FosOS Recovery at the next login

The FosOS greeter has no session picker; LightDM defaults to **FosOS Desktop**.
To use Recovery once:

1. Sign out, or press Ctrl+Alt+F2 if the graphical session is stuck.
2. From a text console (Ctrl+Alt+F2), as your account:

```bash
mkdir -p "$HOME"
printf '%s\n' '[Desktop]' 'Session=fosos-recovery' > "$HOME/.dmrc"
sudo systemctl restart lightdm
```

3. Sign in on the greeter. A terminal opens with restart hints. Run
   `fosos-shell` to try the panel again, or `openbox --exit` to return
   to the greeter.

To return to the full desktop afterward:

```bash
printf '%s\n' '[Desktop]' 'Session=fosos-desktop' > "$HOME/.dmrc"
```

Or use the text console alone without Recovery (next section).

## Text console

1. Press Ctrl+Alt+F2 (or F3…F6).
2. Sign in with your account.
3. Diagnose or repair packages, then return with Ctrl+Alt+F7:

```bash
fos update
fos upgrade
# or
sudo apt update
sudo apt install --reinstall fosos-desktop
sudo systemctl restart lightdm
```

On the live image the account is `user` / password `live`.

## Black screen after Welcome / Install (live)

Openbox may be running without the FosOS shell. On Ctrl+Alt+F2 (`user` / `live`):

```bash
cat ~/.config/fosos-desktop/shell.log
cat ~/.config/fosos-desktop/shell-crash.log
fosos-shell &
```

Switch back with Ctrl+Alt+F7. If the taskbar returns, rebuild the ISO with
`fosos-desktop` **1.3.2+**.

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

4. Switch back with Ctrl+Alt+F7. If the session is still stuck, reboot:
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
