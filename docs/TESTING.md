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
5. Verify the FosOS wallpaper, login appearance, terminal, Firefox, file
   manager, screenshot tool, network applet, audio controls, shutdown, and
   restart.
6. Press Ctrl+Alt+F2 and confirm the recovery console accepts the live
   account. Ctrl+Alt+F1 returns to the desktop.

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
4. Sign in as the account you created. Welcome should show the network status.
   Install updates if the network is up, open the guide, then finish setup.
5. To reinstall, boot the ISO again and erase the disk.

Firefox is the only browser. The installer does not offer another one.

## FosOS Desktop session

FosOS Desktop is experimental. XFCE must stay the default. See
[FosOS Desktop](DESKTOP.md) for its shortcuts and conventions.

Before booting a VM, run the headless check in Debian WSL:

```bash
sudo bash scripts/test-desktop.sh
```

Review the screenshots in `output/desktop/`. Then, in Hyper-V:

1. Boot the live image. It must still sign in to XFCE automatically.
2. Sign out. On the login screen, open the session menu and choose
   **FosOS Desktop (experimental)**. Sign in as `user` with password `live`.
3. Check the taskbar, the Start menu (Super+Space), search, All apps, and the
   Files, Terminal, Firefox and Settings pins.
4. Open and minimize windows from the taskbar. Use Alt+Tab and Super+Left.
5. Run `notify-send Test "Hello"` in a terminal. The popup appears above the
   taskbar and stays in the bell menu.
6. Check the volume slider, the network menu and the calendar.
7. Open Settings. Each tile opens its tool. About shows the system details.
8. Sign out from the Start menu. Sign in to **Xfce Session** and confirm XFCE
   looks the same as before.

On an installed system, repeat steps 2 to 8 with the installed account.

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
repeat the Hyper-V smoke test with that image. Do not publish an ISO that was
built only in WSL.

## Physical USB smoke test

After the release image passes in Hyper-V, write the hybrid ISO to a
disposable USB stick using Rufus or Balena Etcher. Boot it in UEFI mode and
test networking, display output, keyboard, touchpad, audio, suspend, and
boot/reboot behavior. Never test the installer against a disk containing
data you need.
