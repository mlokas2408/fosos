# FosOS ISO size (Phase 7c)

Phase 7 removes the XFCE login session and related packages so the live ISO
stays smaller. Compare sizes after each release rebuild on the dedicated
Debian 13 VM.

## How to measure

```bash
# After scripts/build-iso.sh
ls -lh output/FosOS-trixie-amd64.iso
stat -c '%n %s bytes' output/FosOS-trixie-amd64.iso
```

Record the result in the table below (and in release notes when tagging).

## Recorded sizes

| Build | Date | Bytes | MiB | Notes |
| --- | --- | ---: | ---: | --- |
| Pre–Phase 7 baseline (repo `output/`) | 2026-11-15 | 879394816 | ~839 | Existing ISO before 7c packaging cleanup; may still include Phase 6/7a content depending when it was built |
| Post–Phase 7c (WSL rebuild) | 2026-11-16 | 854405120 | ~815 | 7a–7c package list; `fosos-desktop` 1.3.5; `fosos-theme` 0.6.0 (no greybird/elementary); Dawn Aperture GRUB; −24 MiB vs baseline |
| Post–1.6.0 xrdp host (WSL) | 2026-11-17 | 886945792 | ~846 | `fosos-desktop` 1.6.0; xrdp + xorgxrdp replace freerdp3-shadow; +~31 MiB vs Phase 7c |

## What was removed from the image path

Dropped from the live package list and/or package Depends (Phase 7a–7b):

- `xfce4` metapackage and XFCE session stack
- `thunar`, `mousepad`, `xfce4-terminal`
- `xfce4-notifyd`, `xfce4-pulseaudio-plugin`
- `xfce4-settings`, `xfce4-power-manager`, `xfce4-screenshooter`
- `xfdesktop4` (theme Depends)

Dropped in Phase 7c (`fosos-theme` 0.6.0):

- `greybird-gtk-theme`
- `elementary-xfce-icon-theme` (~67 MiB Installed-Size; squashfs saving is smaller)

gtk-greeter remains installed as an emergency fallback and uses FosOS / Adwaita.

## Approximate payload removed (Debian Installed-Size, KiB)

Direct packages no longer pulled for the session (not counting the large
`xfce4` dependency tree such as `xfwm4` / `xfce4-panel`):

| Package | KiB |
| --- | ---: |
| thunar | 1238 |
| mousepad | 1914 |
| xfce4-settings | 5628 |
| xfce4-power-manager | 529 |
| xfce4-screenshooter | 953 |
| xfce4-terminal | 2212 |
| xfce4-notifyd | 1336 |
| xfce4-pulseaudio-plugin | 593 |
| xfdesktop4 | 875 |
| greybird-gtk-theme (7c) | 5415 |
| elementary-xfce-icon-theme (7c) | 67818 |

Squashfs savings on the ISO are smaller than the sum of Installed-Size, but
dropping the full XFCE session stack is still a clear reduction. The 2026-11-16
rebuild is **~24 MiB** smaller than the recorded pre–Phase 7 baseline.

## Remote Desktop packages (1.6.0)

Live package list (host off until Settings enables it):

| Package | Role |
| --- | --- |
| `xrdp` | Windows-like RDP host (separate session) |
| `xorgxrdp` | Xorg backend for xrdp sessions |
| `freerdp3-x11` | Outbound client for `fosos-remote` |

`freerdp3-shadow-x11` was removed in 1.6.0. Expect modest ISO growth versus
Phase 7c from xrdp/xorgxrdp; record the next rebuild size in the table above.

## Expected direction

The post–Phase 7 ISO should be **clearly smaller** than a Phase 6 image that
shipped the full XFCE session. Exact MiB saved depends on mirror package
versions and squashfs compression; always compare two ISOs built with the
same `scripts/build-iso.sh` on the same builder. Remote Desktop packages
will offset some of that reduction — compare before/after 1.6.0 explicitly.

## Soak

After the rebuild, run the Phase 7 soak in [TESTING.md](TESTING.md)
(Recovery session + TTY, no Xfce Session entry).
