# FosOS

FosOS is a lightweight, Debian Stable-based desktop operating system for
personal and internal company use. Its first usable release uses a branded
XFCE desktop and Firefox, while FosOS Desktop is developed as a separate,
opt-in session.

This repository contains the FosOS source, packaging, and reproducible ISO
build configuration. The `mockup/` directory is the visual reference for FosOS
Desktop. It is not built or shipped.

## Current status

The live image is a branded XFCE desktop with a graphical installer, a
first-login welcome, and the FosOS package archive. FosOS Desktop, the custom
session, ships as an experimental choice on the login screen; XFCE stays the
default. Development images are built in Debian WSL and tested in Hyper-V.
Release images are built on a dedicated Debian 13 VM, then tested again before
they are written to USB.

See [the implementation plan](PLAN.md), [the build guide](docs/BUILDING.md),
[the testing guide](docs/TESTING.md), and [FosOS Desktop](docs/DESKTOP.md)
before building an image.

## Quick start

On Debian 13 WSL, from the repository root:

```bash
sudo FOSOS_WORK_DIR=/var/tmp/fosos-live-build bash scripts/build-iso.sh
```

The generated ISO is written to `output/`. Release builds use a dedicated
Debian VM and are described in [the build guide](docs/BUILDING.md).
