#!/usr/bin/env python3
"""Generate monochrome outline icons for the FosOS Desktop session."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "packages/fosos-desktop/usr/share/icons/FosOS"
STROKE = "#fafafa"


def svg(body: str, size: int = 24, vb: int = 24) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {vb} {vb}" fill="none" stroke="{STROKE}" stroke-width="1.75" '
        'stroke-linecap="round" stroke-linejoin="round">\n'
        f"{body}\n"
        "</svg>\n"
    )


def main() -> None:
    for sub in ("places", "mimetypes", "apps", "actions", "status", "devices"):
        (BASE / "scalable" / sub).mkdir(parents=True, exist_ok=True)

    icons: dict[tuple[str, str], str] = {}

    folder = svg(
        '  <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/>'
    )
    icons[("places", "folder")] = folder
    icons[("places", "inode-directory")] = folder
    icons[("mimetypes", "inode-directory")] = folder
    for name in (
        "folder-documents",
        "folder-download",
        "folder-pictures",
        "folder-music",
        "folder-videos",
        "folder-publicshare",
        "folder-remote",
        "folder-saved-search",
        "folder-open",
    ):
        icons[("places", name)] = folder

    icons[("places", "user-home")] = svg(
        "  <path d=\"M3 11.5 12 4l9 7.5\"/>\n"
        "  <path d=\"M5 10.5V20h14v-9.5\"/>\n"
        "  <path d=\"M10 20v-6h4v6\"/>"
    )
    desktop = svg(
        "  <rect x=\"3\" y=\"4\" width=\"18\" height=\"12\" rx=\"1\"/>\n"
        "  <path d=\"M8 20h8\"/>\n"
        "  <path d=\"M12 16v4\"/>"
    )
    icons[("places", "user-desktop")] = desktop
    icons[("devices", "computer")] = desktop
    icons[("devices", "video-display")] = desktop

    trash = svg(
        "  <path d=\"M3 6h18\"/>\n"
        "  <path d=\"M8 6V4h8v2\"/>\n"
        "  <path d=\"M6 6l1 14h10l1-14\"/>\n"
        "  <path d=\"M10 10v6\"/>\n"
        "  <path d=\"M14 10v6\"/>"
    )
    icons[("places", "user-trash")] = trash
    icons[("places", "user-trash-full")] = trash

    network = svg(
        "  <circle cx=\"12\" cy=\"12\" r=\"3\"/>\n"
        "  <path d=\"M12 2v3\"/>\n"
        "  <path d=\"M12 19v3\"/>\n"
        "  <path d=\"M2 12h3\"/>\n"
        "  <path d=\"M19 12h3\"/>\n"
        "  <path d=\"M4.9 4.9l2.1 2.1\"/>\n"
        "  <path d=\"M17 17l2.1 2.1\"/>\n"
        "  <path d=\"M4.9 19.1 7 17\"/>\n"
        "  <path d=\"M17 7l2.1-2.1\"/>"
    )
    icons[("places", "network-workgroup")] = network
    icons[("places", "network-server")] = network
    icons[("places", "user-bookmarks")] = svg('  <path d="M7 3h10v18l-5-3-5 3V3z"/>')

    doc = svg(
        "  <path d=\"M7 3h7l5 5v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z\"/>\n"
        "  <path d=\"M14 3v5h5\"/>\n"
        "  <path d=\"M9 13h6\"/>\n"
        "  <path d=\"M9 17h6\"/>"
    )
    for name in (
        "text-x-generic",
        "text-x-generic-template",
        "text-plain",
        "text-markdown",
        "text-x-script",
        "text-html",
        "application-rtf",
        "application-msword",
        "application-vnd.oasis.opendocument.text",
        "x-office-document",
        "application-x-zerosize",
        "application-pdf",
        "application-x-pdf",
        "application-x-generic",
        "unknown",
    ):
        icons[("mimetypes", name)] = doc

    sheet = svg(
        "  <path d=\"M7 3h7l5 5v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z\"/>\n"
        "  <path d=\"M14 3v5h5\"/>\n"
        "  <path d=\"M9 12h6\"/>\n"
        "  <path d=\"M9 15h6\"/>\n"
        "  <path d=\"M9 18h6\"/>\n"
        "  <path d=\"M12 12v6\"/>"
    )
    for name in (
        "application-vnd.ms-excel",
        "application-vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application-vnd.oasis.opendocument.spreadsheet",
        "x-office-spreadsheet",
        "text-csv",
    ):
        icons[("mimetypes", name)] = sheet

    pres = svg(
        "  <path d=\"M7 3h7l5 5v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z\"/>\n"
        "  <path d=\"M14 3v5h5\"/>\n"
        "  <rect x=\"8\" y=\"12\" width=\"8\" height=\"5\"/>"
    )
    for name in (
        "application-vnd.ms-powerpoint",
        "application-vnd.openxmlformats-officedocument.presentationml.presentation",
        "application-vnd.oasis.opendocument.presentation",
        "x-office-presentation",
    ):
        icons[("mimetypes", name)] = pres

    img = svg(
        "  <rect x=\"3\" y=\"5\" width=\"18\" height=\"14\" rx=\"1\"/>\n"
        "  <circle cx=\"9\" cy=\"10\" r=\"1.5\"/>\n"
        "  <path d=\"M3 16l5-4 4 3 3-2 6 4\"/>"
    )
    for name in (
        "image-x-generic",
        "image-jpeg",
        "image-png",
        "image-svg+xml",
        "image-gif",
        "image-bmp",
        "image-tiff",
    ):
        icons[("mimetypes", name)] = img

    aud = svg(
        "  <path d=\"M9 18V6l10-2v12\"/>\n"
        "  <circle cx=\"7\" cy=\"18\" r=\"2.5\"/>\n"
        "  <circle cx=\"17\" cy=\"16\" r=\"2.5\"/>"
    )
    for name in ("audio-x-generic", "audio-mpeg", "audio-flac", "audio-x-wav", "audio-ogg"):
        icons[("mimetypes", name)] = aud

    vid = svg(
        "  <rect x=\"3\" y=\"6\" width=\"14\" height=\"12\" rx=\"1\"/>\n"
        "  <path d=\"M17 10l4-2v8l-4-2z\"/>"
    )
    for name in ("video-x-generic", "video-mp4", "video-x-matroska", "video-ogg"):
        icons[("mimetypes", name)] = vid

    pkg = svg(
        "  <path d=\"M12 3 20 7.5v9L12 21 4 16.5v-9L12 3z\"/>\n"
        "  <path d=\"M12 12 20 7.5\"/>\n"
        "  <path d=\"M12 12v9\"/>\n"
        "  <path d=\"M12 12 4 7.5\"/>"
    )
    for name in (
        "package-x-generic",
        "application-x-archive",
        "application-zip",
        "application-gzip",
        "application-x-tar",
        "application-x-compressed-tar",
    ):
        icons[("mimetypes", name)] = pkg

    exe = svg(
        "  <rect x=\"4\" y=\"4\" width=\"16\" height=\"16\" rx=\"1\"/>\n"
        "  <path d=\"M8 12h8\"/>\n"
        "  <path d=\"M12 8v8\"/>"
    )
    for name in ("application-x-executable", "application-x-shellscript", "application-octet-stream"):
        icons[("mimetypes", name)] = exe

    icons[("apps", "system-file-manager")] = folder
    icons[("apps", "org.xfce.thunar")] = folder
    icons[("apps", "Thunar")] = folder
    terminal = svg(
        "  <rect x=\"3\" y=\"5\" width=\"18\" height=\"14\" rx=\"1\"/>\n"
        "  <path d=\"M7 10l3 2-3 2\"/>\n"
        "  <path d=\"M12 14h5\"/>"
    )
    icons[("apps", "utilities-terminal")] = terminal
    icons[("apps", "org.xfce.terminalemulator")] = terminal
    icons[("apps", "xfce4-terminal")] = terminal
    browser = svg(
        "  <circle cx=\"12\" cy=\"12\" r=\"9\"/>\n"
        "  <path d=\"M3 12h18\"/>\n"
        "  <path d=\"M12 3a14 14 0 0 1 0 18\"/>\n"
        "  <path d=\"M12 3a14 14 0 0 0 0 18\"/>"
    )
    icons[("apps", "web-browser")] = browser
    icons[("apps", "firefox")] = browser
    icons[("apps", "firefox-esr")] = browser
    icons[("apps", "preferences-system")] = network
    icons[("apps", "accessories-text-editor")] = doc
    icons[("apps", "org.xfce.mousepad")] = doc

    for (ctx, name), content in icons.items():
        path = BASE / "scalable" / ctx / f"{name}.svg"
        path.write_text(content, encoding="utf-8", newline="\n")

    print(f"wrote {len(icons)} icons under {BASE}")


if __name__ == "__main__":
    main()
