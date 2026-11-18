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

## Installer: filesystem.squashfs does not exist

Calamares expects `/run/live/medium/live/filesystem.squashfs`. On some USB
boots Debian live-boot only mounts the stick at `/lib/live/mount/medium`
(or leaves `/run/live/medium` empty/wrong). `fosos-installer` **1.0.2+**
fixes this in `fosos-calamares` before Calamares starts.

**On the live laptop right now** (account `user` / `live`), before Install
FosOS again:

```bash
ls /lib/live/mount/medium/live/filesystem.squashfs
# If that path is missing, the USB write is wrong — remake with Etcher/dd.

sudo mkdir -p /run/live/medium
# If something is already mounted there but incomplete:
findmnt /run/live/medium && sudo umount /run/live/medium
sudo mount --bind /lib/live/mount/medium /run/live/medium
ls /run/live/medium/live/filesystem.squashfs
```

Then start **Install FosOS** again (do not launch plain `calamares`).

Prefer writing the hybrid ISO with Balena Etcher or `dd`. Rufus in
**ISO mode** can break the live layout; use **DD image mode** if you use Rufus.

If **Etcher** shows **Missing partition table** when you select the ISO, that
image is not hybrid (older builds used `grub-efi` only). Rebuild with
`scripts/build-iso.sh` (bootloaders `grub-pc grub-efi`), confirm
`file …iso` mentions `DOS/MBR`, then flash again — do not rely on Continue.

## Settings freezes when enabling Remote Desktop

Older builds ran `pkexec` synchronously inside Settings, which blocked the
UI (mouse still moved). Update `fosos-desktop` or rebuild the ISO. Escape
with Ctrl+Alt+F2, then `pkill -x fosos-settings` or `sudo systemctl restart
lightdm`.

## Hyper-V: desktop visible, mouse/keyboard frozen

Usually the legacy `hyperv_fb` framebuffer. FosOS images blacklist it and
prefer `hyperv_drm`. On an old ISO, Ctrl+Alt+F2 (`user` / `live`) then:

```bash
cat /proc/fb
# Expect hyperv_drmdrmfb after a fixed image, not hyperv_fb
sudo systemctl restart lightdm
```

Or reboot and at GRUB append `module_blacklist=hyperv_fb` once, then rebuild
the ISO so the live hook and bootappend include the fix.

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
