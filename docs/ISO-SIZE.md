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
| Post–Phase 7 (after your rebuild) | _TBD_ | | | Rebuild with 7a–7c package list + `fosos-desktop` 1.2.0 / `fosos-theme` 0.4.0 |

## What was removed from the image path

Dropped from the live package list and/or package Depends (Phase 7a–7b):

- `xfce4` metapackage and XFCE session stack
- `thunar`, `mousepad`, `xfce4-terminal`
- `xfce4-notifyd`, `xfce4-pulseaudio-plugin`
- `xfce4-settings`, `xfce4-power-manager`, `xfce4-screenshooter`
- `xfdesktop4` (theme Depends)

Still present for the greeter only (not an XFCE session):

- `greybird-gtk-theme`
- `elementary-xfce-icon-theme`

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

Squashfs savings on the ISO are smaller than the sum of Installed-Size, but
dropping the full XFCE session stack is still a clear reduction.

## Expected direction

The post–Phase 7 ISO should be **clearly smaller** than a Phase 6 image that
shipped the full XFCE session. Exact MiB saved depends on mirror package
versions and squashfs compression; always compare two ISOs built with the
same `scripts/build-iso.sh` on the same builder.

## Soak

After the rebuild, run the Phase 7 soak in [TESTING.md](TESTING.md)
(Recovery session + TTY, no Xfce Session entry).
