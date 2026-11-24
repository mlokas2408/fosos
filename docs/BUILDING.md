# Building a FosOS ISO

FosOS images are built only on Debian 13 (Trixie). Ubuntu's packaged
`live-build` is an obsolete 3.0 release. It does not support the UEFI GRUB
configuration required by FosOS, and `scripts/build-iso.sh` stops if it detects
that version.

| When | Where to build | Where to test |
| --- | --- | --- |
| Development and pre-release | Debian 13 WSL | Hyper-V on the same Windows machine |
| Release | A dedicated Debian 13 VM | Hyper-V, then USB on selected hardware |

The release builder stays a clean VM so packages from a daily-use system cannot
leak into the image. Development builds use the same script and the same
Debian mirrors; they differ only in the machine that runs the build.

The build script removes live-build's generated configuration directories
before every build. Tracked FosOS package lists and included files are kept.

The first images target amd64 machines that boot using UEFI. They are hybrid
ISOs (`--binary-images iso-hybrid --bootloaders "grub-pc grub-efi"`): the same
file boots in a VM and can be written with Balena Etcher or `dd` to USB.
`grub-pc` is included so the ISO carries an MBR/partition table Etcher
expects; supported hardware remains UEFI-only (legacy BIOS is not a test
target). `--uefi-secure-boot enable` installs Microsoft-trusted `shim` and
Debian-signed GRUB on the EFI path. Installed systems hide the GRUB menu
(`GRUB_TIMEOUT_STYLE=hidden`) and show Dawn Aperture Plymouth until the
greeter; hold Shift to open GRUB. Live bootappend includes `quiet splash`.
Shut down and restart use the same Plymouth splash with Shutting down /
Restarting titles (not console stop text). Early KMS (`fosos-kms` modules)
plus `plymouth.force-frame-buffer-on-boot` keep the graphical theme when the
GPU driver is late (Debian kernels lack SimpleDRM).
After a build, `file output/FosOS-trixie-amd64.iso` should mention
`DOS/MBR boot sector`. If Etcher says “Missing partition table”, the image
is not hybrid — rebuild; do not Continue past that warning for laptop USB.

## Prerequisites

On either builder, confirm Debian 13 and install the ISO tools:

```bash
grep VERSION_CODENAME /etc/os-release
sudo apt update
sudo apt install --yes live-build debootstrap debian-archive-keyring xorriso squashfs-tools
```

`VERSION_CODENAME` must be `trixie`.

## Development build (Debian WSL)

Use this path while iterating. The repository can stay on the Windows
filesystem. live-build cannot reliably run its chroot there, so the build
runs in a Linux-native scratch directory and the finished ISO is copied back
to `output/`.

From the repository root inside the WSL distro:

```bash
sudo bash scripts/check-build-config.sh
sudo FOSOS_WORK_DIR=/var/tmp/fosos-live-build bash scripts/build-iso.sh
```

Attach `output/FosOS-trixie-amd64.iso` to a Hyper-V virtual machine, as
described in [the testing guide](TESTING.md).

## Release build (dedicated Debian VM)

Build a release image only on a Debian 13 VM that is not a daily-use install.
Clone this repository onto the VM's own disk, then run:

```bash
sudo bash scripts/check-build-config.sh
sudo bash scripts/build-iso.sh
```

The default Debian suite is `trixie`. Override it only for controlled porting
work:

```bash
sudo FOSOS_DEBIAN_SUITE=trixie bash scripts/build-iso.sh
```

## Output

Both paths produce:

```text
output/FosOS-trixie-amd64.iso
```

## What the image includes

- FosOS Desktop as the only full login session (Openbox + FosOS shell), with
  FosOS Recovery (Openbox + terminal) as the greeter fallback
- A FosOS GRUB live menu (Dawn Aperture splash, dark theme, FosOS Live
  entries) and the FosOS LightDM greeter (`fosos-greeter`, two-column
  Sign in; `lightdm-gtk-greeter` kept as emergency fallback on FosOS/Adwaita).
  Regenerate the splash with `node scripts/_render_grub_splash.mjs` after
  logo changes; live-build reads `config/bootloaders/grub-pc/` for both
  BIOS and UEFI
- Install FosOS, a Calamares installer for language, keyboard, disk,
  optional encryption, and the account that owns the installed system
- A first-login welcome screen for network status, the FosOS guide, and updates
- First-party Files, Terminal, Notepad, Settings, screenshot, lock screen and
  notifications (no XFCE session or xfce4-* Depends)
- Remote Desktop: outbound FreeRDP client; inbound xrdp host (off until
  Settings enables it; separate FosOS Desktop session)
- A FosOS archive key and the `fos` command for update, upgrade, install,
  remove, and repair
- Firefox ESR as the preinstalled browser
- NetworkManager with Wi-Fi powersave disabled, PipeWire audio, Bluetooth,
  power defaults, archive utility, screenshot tool, and a recovery console
  on Ctrl+Alt+F2
- Laptop Wi-Fi firmware from `non-free-firmware` (`firmware-iwlwifi`,
  Realtek/Atheros/Broadcom/MediaTek/misc, plus `wireless-regdb`); listed
  explicitly because `--firmware-chroot` stays false
- No XFCE login session; no Git, Node.js, Docker, compilers, language SDKs,
  Chrome, or other development stack by default

The installer is Calamares. FosOS packages are published separately to the
public archive at `https://mlokas2408.github.io/fosos-apt`. The image installs
`fosos-archive-keyring`, which points APT at the stable suite. New packages
go to testing first. The keyboard layout default on the live image is US; the
installer asks again for the installed system.

Boot the image in Hyper-V before writing it to a USB drive. See
[the testing guide](TESTING.md). After a release rebuild, record the ISO
byte size in [ISO-SIZE.md](ISO-SIZE.md).

## Package archive

Prefer GitHub Actions so any machine can publish without a local signing key
or reprepro database. Open **Actions → APT publish → Run workflow**, choose
`publish` or `promote`, and optionally limit the package list. `publish` builds
packages into testing, runs `scripts/test-apt-archive.sh`, and pushes the
`fosos-apt` checkout. Run `promote` afterward to copy those packages to stable
and push again. The public URL is
`https://mlokas2408.github.io/fosos-apt`.

### One-time Actions secrets

Create these repository secrets on `fosos` (never commit them):

| Secret | Purpose |
|--------|---------|
| `FOSOS_APT_SIGNING_KEY` | Armored private archive signing key |
| `FOSOS_APT_PUSH_TOKEN` | Token with `contents: write` on `MLOKAS2408/fosos-apt` |

Export the existing key once from the machine that first published:

```bash
sudo gpg --homedir /root/.local/share/fosos/archive-gnupg \
  --export-secret-keys --armor archive@fosos.local
```

Paste that armored block into `FOSOS_APT_SIGNING_KEY`. The private key must
never enter git.

### Local publish

You can still publish from Debian 13 with `gnupg` and `reprepro`. Point
`FOSOS_APT_DIR` at a pulled `fosos-apt` checkout and keep the matching private
key in `FOSOS_GNUPGHOME` (default `/root/.local/share/fosos/archive-gnupg`).
Each run rebuilds the local reprepro work database from that public checkout,
so you do not need to copy `/var/tmp/fosos-apt` between machines.

```bash
sudo bash scripts/apt-archive.sh publish
sudo bash scripts/test-apt-archive.sh
sudo bash scripts/apt-archive.sh promote
```

Then push the `fosos-apt` checkout so GitHub Pages serves the update from the
`main` branch root.
