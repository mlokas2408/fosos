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
ISOs: the same ISO boots in a virtual machine and can be written directly to a
USB drive for a live session. Legacy BIOS boot is out of scope.

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
  Sign in; Greybird / elementary-xfce kept as fallback). Regenerate the
  splash with `node scripts/_render_grub_splash.mjs` after logo changes;
  live-build reads `config/bootloaders/grub-pc/` for both BIOS and UEFI
- Install FosOS, a Calamares installer for language, keyboard, disk,
  optional encryption, and the account that owns the installed system
- A first-login welcome screen for network status, the FosOS guide, and updates
- First-party Files, Terminal, Notepad, Settings, screenshot, lock screen and
  notifications (no XFCE session or xfce4-* Depends)
- A FosOS archive key and the `fos` command for update, upgrade, install,
  remove, and repair
- Firefox ESR as the preinstalled browser
- NetworkManager with Wi-Fi powersave disabled, PipeWire audio, Bluetooth,
  power defaults, archive utility, screenshot tool, firmware, and a recovery
  console on Ctrl+Alt+F2
- No XFCE login session; no Git, Node.js, Docker, compilers, language SDKs,
  Chrome, or other development stack by default

The installer is Calamares. FosOS packages are published separately to the
public archive at `https://mlokas2408.github.io/fosos-apt`. The image installs
`fosos-archive-keyring`, which points APT at the stable suite. New packages
go to testing first. The keyboard layout default on the live image is US; the
installer asks again for the installed system.

Boot the image in Hyper-V before writing it to a USB drive. See
[the testing guide](TESTING.md). After a Phase 7 rebuild, record the ISO
byte size in [ISO-SIZE.md](ISO-SIZE.md).

## Package archive

Publish from Debian 13, where `gnupg` and `reprepro` are installed. The signing
private key is created on the first publish and stored in
`/root/.local/share/fosos/archive-gnupg`. It is not written to either git
repository.

```bash
sudo bash scripts/apt-archive.sh publish
sudo bash scripts/test-apt-archive.sh
sudo bash scripts/apt-archive.sh promote
```

`publish` builds the FosOS packages and puts them in the testing suite.
`promote` copies those exact packages to stable. The public files land in the
`fosos-apt` checkout beside this repository. Push that checkout and serve it
with GitHub Pages from the `main` branch root before an installed system can
download it. The public URL is `https://mlokas2408.github.io/fosos-apt`.
