# FosOS

FosOS is a lightweight, Debian Stable-based desktop operating system for
personal and internal company use. FosOS Desktop is the only full desktop
session; FosOS Recovery (Openbox + terminal) and text consoles are the
fallback.

This repository contains the FosOS source, packaging, and reproducible ISO
build configuration. The `mockup/` directory is the visual reference for
FosOS Desktop. It is not built or shipped.

## Current status

The live image boots into FosOS Desktop with a graphical installer, a
first-login welcome, and the FosOS package archive. XFCE is not shipped
(Phase 7); settings and screenshots are FosOS-owned or light tools
(`arandr`, `scrot`, `xsettingsd`). Development images are built in Debian WSL
and tested in Hyper-V. Release images are built on a dedicated Debian 13 VM,
then tested again before they are written to USB.

See [the implementation plan](PLAN.md), [release notes](docs/RELEASE-NOTES.md),
[recovery guide](docs/RECOVERY.md), [the build guide](docs/BUILDING.md),
[the testing guide](docs/TESTING.md), and [FosOS Desktop](docs/DESKTOP.md)
before building an image.

## Quick start

On Debian 13 WSL, from the repository root:

```bash
sudo FOSOS_WORK_DIR=/var/tmp/fosos-live-build bash scripts/build-iso.sh
```

The generated ISO is written to `output/`. Release builds use a dedicated
Debian VM and are described in [the build guide](docs/BUILDING.md).
