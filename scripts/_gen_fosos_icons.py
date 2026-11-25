#!/usr/bin/env python3
"""Generate sharp filled icons for FosOS files and folders.

Drawn on a 16×16 grid so list rows (16px) and icon view (32/48/96) land on
whole pixels. Corners are square, matching the desktop. Bodies are two-tone
paper and shade; color is only used where a file type is identified by it.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "packages/fosos-desktop/usr/share/icons/FosOS"

PAPER = "#fafafa"
SHADE = "#a1a1aa"
INK = "#171717"
RED = "#e11d48"
GREEN = "#15803d"
AMBER = "#d97706"
TERM = "#4ade80"
BLUE = "#2563eb"


def svg(*parts: str) -> str:
    body = "\n".join(parts)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" '
        'viewBox="0 0 16 16">\n'
        f"{body}\n"
        "</svg>\n"
    )


def fill(d: str, color: str) -> str:
    return f'  <path fill="{color}" d="{d}"/>'


def page(*marks: str) -> str:
    """Document with a sharp folded corner."""
    return svg(
        fill("M3 1h7l4 4v10H3z", PAPER),
        fill("M10 1v4h4z", SHADE),
        *marks,
    )


def hollow_page() -> str:
    return svg(
        fill("M3 1h7l4 4v10H3V1zm1 1h5v3h3v8H4V2z", PAPER),
    )


def folder(*marks: str, tab: str = SHADE) -> str:
    """Inset face so the shade reads as an edge, not a flat slab."""
    return svg(
        fill("M1 5h14v10H1z", SHADE),
        fill("M1 2h6l2 3H1z", tab),
        fill("M2 7h12v7H2z", PAPER),
        *marks,
    )


def open_folder() -> str:
    return svg(
        fill("M2 2h5l2 2h4v3H2z", SHADE),
        fill("M1 6h14v8H1z", SHADE),
        fill("M2 8h12v5H2z", PAPER),
    )


def main() -> None:
    for sub in ("places", "mimetypes", "apps", "actions", "status", "devices"):
        (BASE / "scalable" / sub).mkdir(parents=True, exist_ok=True)

    icons: dict[tuple[str, str], str] = {}

    plain = folder()
    icons[("places", "folder")] = plain
    icons[("places", "inode-directory")] = plain
    icons[("mimetypes", "inode-directory")] = plain
    icons[("places", "folder-open")] = open_folder()
    icons[("places", "folder-documents")] = folder(
        fill("M5 8h4l2 2v4H5z", INK),
        fill("M9 8v2h2z", PAPER),
    )
    icons[("places", "folder-download")] = folder(
        fill("M7 8h2v2H7z", INK),
        fill("M5 10h6l-3 3z", INK),
        tab=GREEN,
    )
    icons[("places", "folder-pictures")] = folder(
        fill("M5 8h6v6H5z", INK),
        fill("M6 9h4v4H6z", PAPER),
        fill("M6 9h2v2H6z", AMBER),
        tab=BLUE,
    )
    icons[("places", "folder-music")] = folder(
        fill("M5 11h2V8h5v2H9v3H5z", INK),
        tab=AMBER,
    )
    icons[("places", "folder-videos")] = folder(
        fill("M5 8l5 3-5 3z", INK),
        tab=RED,
    )
    icons[("places", "folder-publicshare")] = folder(
        fill("M6 8h4v2H6z", INK),
        fill("M4 11h3v2H4z", INK),
        fill("M9 11h3v2H9z", INK),
    )
    icons[("places", "folder-remote")] = folder(
        fill("M5 9h3v2H5z", INK),
        fill("M7 8l4 3-4 2z", INK),
    )
    icons[("places", "folder-saved-search")] = folder(
        fill("M4 8h5v5H4z", INK),
        fill("M5 9h3v3H5z", PAPER),
        fill("M9 11h3v2H9z", INK),
    )

    icons[("places", "user-home")] = svg(
        fill("M1 8 8 2l7 6v1H1z", SHADE),
        fill("M3 9h10v6H3z", PAPER),
        fill("M7 11h2v4H7z", INK),
    )
    desktop = svg(
        fill("M1 2h14v9H1z", PAPER),
        fill("M2 3h12v7H2z", INK),
        fill("M7 11h2v1H7z", PAPER),
        fill("M4 12h8v2H4z", PAPER),
    )
    icons[("places", "user-desktop")] = desktop
    icons[("devices", "computer")] = desktop
    icons[("devices", "video-display")] = desktop

    icons[("places", "user-trash")] = svg(
        fill("M4 5h8l-1 9H5z", SHADE),
        fill("M6 2h4v2H6z", PAPER),
        fill("M2 4h12v2H2z", PAPER),
        fill("M6 8h1v4H6z", INK),
        fill("M9 8h1v4H9z", INK),
    )
    icons[("places", "user-trash-full")] = svg(
        fill("M4 6h8l-1 8H5z", SHADE),
        fill("M4 1h3v5H4z", PAPER),
        fill("M8 2h4v4H8z", SHADE),
        fill("M2 5h12v2H2z", PAPER),
        fill("M6 9h1v3H6z", INK),
        fill("M9 9h1v3H9z", INK),
    )
    icons[("places", "user-bookmarks")] = svg(
        fill("M4 1h8v13l-4-3-4 3z", PAPER),
        fill("M6 4h4v1H6z", INK),
    )
    icons[("places", "network-workgroup")] = svg(
        fill("M5 3h6v2H5z", SHADE),
        fill("M7 5h2v5H7z", SHADE),
        fill("M1 2h4v4H1z", PAPER),
        fill("M11 2h4v4h-4z", PAPER),
        fill("M6 10h4v4H6z", PAPER),
    )
    icons[("places", "network-server")] = svg(
        fill("M2 1h12v3H2z", PAPER),
        fill("M2 6h12v3H2z", PAPER),
        fill("M2 11h12v3H2z", PAPER),
        fill("M4 2h2v1H4z", GREEN),
        fill("M4 7h2v1H4z", GREEN),
        fill("M4 12h2v1H4z", GREEN),
    )

    text = page(
        fill("M5 8h7v1H5z", INK),
        fill("M5 10h7v1H5z", INK),
        fill("M5 12h5v1H5z", INK),
    )
    for name in (
        "text-x-generic",
        "text-x-generic-template",
        "text-plain",
        "text-x-todo-txt",
        "text-x-patch",
        "text-x-diff",
        "application-rtf",
        "application-msword",
        "application-vnd.oasis.opendocument.text",
        "x-office-document",
    ):
        icons[("mimetypes", name)] = text

    icons[("mimetypes", "text-markdown")] = page(
        fill("M5 7h7v2H5z", INK),
        fill("M5 10h7v1H5z", INK),
        fill("M5 12h5v1H5z", INK),
    )

    code = page(
        fill("M5 7h2v1H5z", INK),
        fill("M5 7h1v6H5z", INK),
        fill("M5 12h2v1H5z", INK),
        fill("M9 7h2v1H9z", INK),
        fill("M10 7h1v6H10z", INK),
        fill("M9 12h2v1H9z", INK),
    )
    for name in (
        "text-html",
        "text-css",
        "application-xml",
        "text-xml",
        "application-json",
        "application-javascript",
        "text-javascript",
        "text-x-python",
        "text-x-java",
        "text-x-csrc",
        "text-x-chdr",
        "text-x-c++src",
        "application-x-php",
    ):
        icons[("mimetypes", name)] = code

    script = page(
        fill("M5 8h2v1H5z", INK),
        fill("M6 9h2v1H6z", INK),
        fill("M7 10h2v1H7z", INK),
        fill("M6 11h2v1H6z", INK),
        fill("M5 12h2v1H5z", INK),
        fill("M10 12h3v1H10z", INK),
    )
    for name in ("text-x-script", "application-x-shellscript"):
        icons[("mimetypes", name)] = script

    pdf = page(fill("M3 11h11v4H3z", RED))
    for name in ("application-pdf", "application-x-pdf"):
        icons[("mimetypes", name)] = pdf

    blank = page()
    for name in ("application-x-generic", "unknown"):
        icons[("mimetypes", name)] = blank
    icons[("mimetypes", "application-x-zerosize")] = hollow_page()

    sheet = page(
        fill("M5 7h7v1H5z", GREEN),
        fill("M5 9h7v1H5z", GREEN),
        fill("M5 11h7v1H5z", GREEN),
        fill("M5 13h7v1H5z", GREEN),
        fill("M8 7h1v7H8z", GREEN),
    )
    for name in (
        "application-vnd.ms-excel",
        "application-vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application-vnd.oasis.opendocument.spreadsheet",
        "x-office-spreadsheet",
        "text-csv",
    ):
        icons[("mimetypes", name)] = sheet

    pres = page(
        fill("M5 7h7v5H5z", AMBER),
        fill("M6 13h5v1H6z", INK),
    )
    for name in (
        "application-vnd.ms-powerpoint",
        "application-vnd.openxmlformats-officedocument.presentationml.presentation",
        "application-vnd.oasis.opendocument.presentation",
        "x-office-presentation",
    ):
        icons[("mimetypes", name)] = pres

    img = svg(
        fill("M1 3h14v10H1z", PAPER),
        fill("M2 4h12v8H2z", INK),
        fill("M3 5h2v2H3z", AMBER),
        fill("M2 10l3-2 2 1 3-2 2 2v3H2z", PAPER),
    )
    for name in (
        "image-x-generic",
        "image-jpeg",
        "image-png",
        "image-svg+xml",
        "image-gif",
        "image-bmp",
        "image-tiff",
        "image-webp",
        "image-x-icon",
    ):
        icons[("mimetypes", name)] = img

    aud = svg(
        fill("M1 6h2v4H1z", PAPER),
        fill("M4 3h2v10H4z", PAPER),
        fill("M7 5h2v6H7z", PAPER),
        fill("M10 2h2v12h-2z", PAPER),
        fill("M13 4h2v8h-2z", PAPER),
    )
    for name in (
        "audio-x-generic",
        "audio-mpeg",
        "audio-flac",
        "audio-x-wav",
        "audio-ogg",
        "audio-x-m4a",
        "audio-aac",
        "audio-mp4",
    ):
        icons[("mimetypes", name)] = aud

    vid = svg(
        fill("M1 4h10v8H1z", PAPER),
        fill("M2 5h8v6H2z", INK),
        fill("M4 6l4 2-4 2z", PAPER),
        fill("M12 6l3-1v6l-3-1z", PAPER),
    )
    for name in (
        "video-x-generic",
        "video-mp4",
        "video-x-matroska",
        "video-ogg",
        "video-webm",
        "video-quicktime",
        "video-x-msvideo",
    ):
        icons[("mimetypes", name)] = vid

    pkg = svg(
        fill("M2 3h12v3H2z", PAPER),
        fill("M3 6h10v8H3z", SHADE),
        fill("M7 4h2v1H7z", INK),
    )
    for name in (
        "package-x-generic",
        "application-x-archive",
        "application-zip",
        "application-gzip",
        "application-x-tar",
        "application-x-compressed-tar",
        "application-x-bzip",
        "application-x-xz",
        "application-x-7z-compressed",
        "application-x-rar",
        "application-vnd.rar",
        "application-vnd.debian.binary-package",
        "application-x-deb",
    ):
        icons[("mimetypes", name)] = pkg

    exe = svg(
        fill("M2 2h12v12H2z", PAPER),
        fill("M4 4h8v8H4z", INK),
        fill("M6 6h4v4H6z", PAPER),
    )
    for name in ("application-x-executable", "application-x-desktop"):
        icons[("mimetypes", name)] = exe
    icons[("mimetypes", "application-octet-stream")] = page(
        fill("M6 8h4v5H6z", INK),
    )

    icons[("apps", "system-file-manager")] = plain
    icons[("apps", "utilities-terminal")] = svg(
        fill("M1 3h14v10H1z", PAPER),
        fill("M2 4h12v8H2z", INK),
        fill("M4 6h2v1H4z", TERM),
        fill("M5 7h2v1H5z", TERM),
        fill("M6 8h2v1H6z", TERM),
        fill("M5 9h2v1H5z", TERM),
        fill("M4 10h2v1H4z", TERM),
        fill("M9 10h4v1H9z", TERM),
    )
    browser = svg(
        fill("M1 2h14v12H1z", PAPER),
        fill("M1 2h14v3H1z", INK),
        fill("M3 3h1v1H3z", PAPER),
        fill("M5 3h1v1H5z", PAPER),
        fill("M7 3h1v1H7z", PAPER),
        fill("M5 7h6v5H5z", BLUE),
        fill("M6 8h4v3H6z", PAPER),
    )
    icons[("apps", "web-browser")] = browser
    icons[("apps", "firefox")] = browser
    icons[("apps", "firefox-esr")] = browser
    icons[("apps", "preferences-system")] = svg(
        fill("M1 4h14v1H1z", SHADE),
        fill("M1 8h14v1H1z", SHADE),
        fill("M1 12h14v1H1z", SHADE),
        fill("M3 2h3v5H3z", PAPER),
        fill("M9 6h3v5H9z", PAPER),
        fill("M5 10h3v4H5z", PAPER),
    )
    icons[("apps", "accessories-text-editor")] = text

    for (ctx, name), content in icons.items():
        path = BASE / "scalable" / ctx / f"{name}.svg"
        path.write_text(content, encoding="utf-8", newline="\n")

    print(f"wrote {len(icons)} icons under {BASE}")


if __name__ == "__main__":
    main()
