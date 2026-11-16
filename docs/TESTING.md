# FosOS ISO testing

Development images are built in Debian WSL and tested in Hyper-V. A release
image is built again on the dedicated Debian VM, then put through the same
Hyper-V check before it is written to USB. See [the build guide](BUILDING.md).

## Hyper-V smoke test

1. In Hyper-V Manager, create a Generation 2 virtual machine with 4 GB RAM and

   two virtual processors. Add a virtual hard disk when you want to install.
2. Attach `output/FosOS-trixie-amd64.iso` as a virtual DVD. Add a virtual hard

   disk of at least 16 GB when you want to test installation.
3. In the VM firmware settings, turn off Secure Boot and put the DVD drive

   first in the boot order. Hyper-V Generation 2 enables Secure Boot by
     default, and this live image is not set up to boot with it.
4. Start the VM and boot into the live environment.
5. On the GRUB menu, confirm the Dawn Aperture splash, **FosOS** title,

   dark menu styling, and a **FosOS Live** entry. Press Enter (or wait ~8s).
6. Confirm the live image autologins to **FosOS Desktop** (taskbar, Start,

   drawn wallpaper). Verify Firefox, Files, Terminal, screenshot tool,
     network, audio, shutdown, and restart.
7. Sign out once and confirm the greeter is the two-column FosOS Sign in

   screen (not the old Greybird GTK greeter). Confirm the bottom-right
     power button offers Shut down, Restart, and Suspend. Sign back in as `user`.
8. Press Ctrl+Alt+F2 and confirm the recovery console accepts the live

   account. Ctrl+Alt+F7 returns to the desktop.

The live image automatically signs in Debian Live's temporary `user` account
through LightDM. The password is `live`, for `sudo` and the recovery console.
Console auto-login is intentionally disabled, preventing a TTY login path from
interrupting the graphical session. Installation removes that automatic login
and creates the account chosen in the installer. The root account stays
locked; the new account can use `sudo`.

## Install test

1. Boot the live image with a virtual hard disk attached.
2. Choose **Install FosOS**. Pick a language, keyboard, disk, and account.

   Erase the disk for a first install. Encryption is optional.
3. When the installer finishes, restart, detach the ISO, and boot the disk.
4. Sign in as the account you created. The FosOS greeter must show the

   two-column Sign in layout, and the session default must be
     **FosOS Desktop**. Welcome should show the network status. Install updates
     if the network is up, open the guide, then finish setup.
5. To reinstall, boot the ISO again and erase the disk.

Firefox is the only browser. The installer does not offer another one.

## FosOS Desktop session

FosOS Desktop is the only full desktop session. FosOS Recovery and text
consoles are the fallback. See [FosOS Desktop](DESKTOP.md) and
[RECOVERY.md](RECOVERY.md).

Before booting a VM, run the headless check in Debian WSL:

```bash
sudo bash scripts/test-desktop.sh
```

Review the screenshots in `output/desktop/`. Then, in Hyper-V:

1. Boot the live image. It must autologin to **FosOS Desktop**.
2. Check the taskbar, the Start menu (Super+Space), search, All apps, and the

   Files, Terminal, Firefox and Settings pins.
3. Open and minimize windows from the taskbar. Use Alt+Tab and Super+Left.
4. Switch workspaces with Super+1…4 or the pager. Move a window with

   Super+Shift+2 and confirm it leaves the taskbar on Desktop 1.
5. Press Super+L. Unlock with the account password (`live` on the live

   image). Confirm Start > Lock and the Power menu Lock entry also lock
     the session.
6. Run `notify-send Test "Hello"` in a terminal. The popup appears above the

   taskbar and stays in the bell menu.
7. Check the volume slider, the network menu and the calendar. On a laptop,

   confirm battery and brightness icons appear and their menus work.
8. Open Settings. Each tile opens its tool. About shows the system details.
9. Sign out from the Start menu. Sign in to **FosOS Recovery** and confirm a

   terminal opens under Openbox. Sign out and return to **FosOS Desktop**.
     Also check Ctrl+Alt+F2 for a text console.

On a machine with two monitors, confirm a taskbar on each display and that
windows appear on the taskbar for the monitor they sit on.

On an installed system, repeat the checks with the installed account.

## Phase 6 / 7 soak checklist

Run this on a Hyper-V (or hardware) install before shipping a release ISO.
After Phase 7, rebuild the ISO first, then record its size in
[ISO-SIZE.md](ISO-SIZE.md).

- [x] Fresh login to FosOS Desktop (live and installed)
- [x] FosOS greeter two-column Sign in with no session picker (always Desktop)
- [x] Greeter / lock bottom-right power menu (Shut down, Restart, Suspend)
- [x] Lock and unlock (Super+L, idle lock if practical)
- [ ] Display settings (`arandr`) change and apply
- [x] Settings: keyboard, mouse, default apps, power panels
- [ ] Screenshot: Print / Shift+Print → file under Pictures
- [x] Multi-monitor: panel per display, windows on the correct taskbar
- [x] Network connect / disconnect from the panel menu
- [ ] Audio volume and mute
- [ ] Notifications (`notify-send`) and the bell menu
- [x] Shutdown, reboot, and suspend / resume
- [x] `fos update` / `fos upgrade` (or `apt`) of FosOS packages
- [ ] Failed-session recovery: kill `fosos-shell` until the recovery terminal
  ```
  appears, run `fosos-shell`, then verify **FosOS Recovery** and a TTY
  ```
- [x] Greeter is fosos-greeter (not gtk-greeter) and has no Xfce Session entry
- [ ] Post–Phase 7 ISO size recorded in [ISO-SIZE.md](ISO-SIZE.md)
- [ ] Rollback path in [RECOVERY.md](RECOVERY.md) reviewed

## Phase 8 muscle-memory checklist

- [ ] Super tap opens Start; Super+E / Super+I / Super+L still work
- [ ] Super+R Run launches a command or app; Escape closes
- [ ] Super+X quick links (Terminal, Files, Settings, Run, Lock, power)
- [ ] Alt+Tab shows icon+title switcher; release Alt focuses the selection
- [ ] Super+Shift+S (and Shift+Print) captures a region
- [ ] Drag a window titlebar to the top edge maximizes; drag down restores
- [ ] Taskbar: one window minimizes when focused; several windows cycle

## Phase 9 taskbar / Start checklist

- [ ] Taskbar right-click: Pin / Unpin, Open new window, Close window(s)
- [ ] Drag pinned taskbar icons to reorder; order survives restart
- [ ] Middle-click a pinned/running app opens another window
- [ ] Start search finds an app, a settings panel, and a recent file
- [ ] Recommended shows recent files/folders; All apps has A–Z headings
- [ ] Account button menu: home, Lock, Sign out

## Phase 10 Quick Settings / Notification Center checklist

- [ ] Click volume, network, battery or brightness → one Quick Settings panel
- [ ] Wi-Fi / Bluetooth / mute tiles and volume / brightness sliders work
- [ ] Win+A opens Quick Settings; Settings / Sound… / Network… footers work
- [ ] Clock or bell opens calendar + notification history
- [ ] Win+N opens Notification Center; Clear all clears history and toasts
- [ ] Click a history item focuses / activates the related app when possible
- [ ] `notify-send` still shows a toast popup

## Phase 11 Files Explorer checklist

- [ ] Ctrl+C / Ctrl+X / Ctrl+V copy, cut and paste between folders
- [ ] Ctrl+click and Shift+click multi-select; Ctrl+A selects all
- [ ] Delete moves to Recycle Bin; restore from Recycle Bin works
- [ ] Sidebar and desktop Recycle Bin open the trash folder
- [ ] F2 renames; Alt+Up goes up; Ctrl+L edits the path
- [ ] Context menu: Open with, Properties, Copy path, Open Terminal here
- [ ] Drag files onto a folder or into another Files window / listing

## Phase 12 desktop checklist

- [ ] Right-click empty desktop: Refresh, Display settings, Personalize,
      New folder, Open Files here, Open Terminal here
- [ ] New folder creates under `~/Desktop` and opens Files there
- [ ] Icons: Home, Computer, Files, Recycle Bin; drag and restart keeps place
- [ ] Personalize → single-click opens icons with one click; double-click mode
      still needs two clicks
- [ ] Reset icon positions + Refresh / F5 re-stacks the default column
- [ ] Win+D Show Desktop and Dawn Aperture watermark still work

## Phase 13 multitasking checklist

- [ ] Win+Z opens snap layouts; picking a cell tiles the focused window
- [ ] After placing one region, focusing another window fills the next region
- [ ] Right-click the titlebar maximize button opens the same layouts picker
- [ ] Win+Tab shows Task View with all four desktops and their windows
- [ ] Click a window in Task View to switch; Escape closes
- [ ] Right-click a Task View window → Move to Desktop N
- [ ] Taskbar right-click → Move to → Desktop N (single-window groups)
- [ ] Drag window to left/right edge → half; to a corner → quarter; top → max

## Phase 14 Settings checklist

- [ ] Settings → Wallpaper changes the drawn desktop theme; Apply refreshes
- [ ] Taskbar toggles hide/show desktop switcher, clock date, notification bell
- [ ] Notifications → Do not disturb hides toasts; history still in Win+N
- [ ] Display / Sound / Network / Bluetooth pages open the system tools
- [ ] Updates shows last refresh, upgradable estimate, reboot required when set
- [ ] Check for updates / Install updates open a Terminal with `fos …`
- [ ] About lists storage mounts; Storage page matches
- [ ] Default apps includes PDF, Archives, Images

## Package upgrade

On an installed system with a network connection:

```bash
fos update
fos upgrade
```

`fos remove fosos-cli` removes the helper and leaves APT in place.
`fos install fosos-cli` puts it back. If a package install stops halfway,
`fos repair` finishes or undoes it. A package is published to testing first.
Promote it only after this upgrade path has been tried, then let `fos upgrade`
take it from stable.

## Release check

Before tagging a release, rebuild the ISO on the dedicated Debian 13 VM and
repeat the Hyper-V smoke test and Phase 6 soak with that image. Do not publish
an ISO that was built only in WSL. Record the result against
[RELEASE-NOTES.md](RELEASE-NOTES.md).

## Physical USB smoke test

After the release image passes in Hyper-V, write the hybrid ISO to a
disposable USB stick using Rufus or Balena Etcher. Boot it in UEFI mode and
test networking, display output, keyboard, touchpad, audio, suspend, and
boot/reboot behavior. Never test the installer against a disk containing
data you need.
