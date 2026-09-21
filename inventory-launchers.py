"""Inspect desktop launchers without running applications or shell commands."""

from __future__ import annotations

import argparse
import configparser
import os
from pathlib import Path
import re
import shlex
import shutil
import sys


def launcher_directories() -> list[Path]:
    """Return common and configured XDG application directories."""
    home = Path.home()
    data_home = os.environ.get("XDG_DATA_HOME") or str(home / ".local/share")
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    roots = [Path(data_home), *(Path(p) for p in data_dirs.split(":") if p)]
    roots += [Path("/var/lib/snapd/desktop"), Path("/var/lib/flatpak/exports/share"),
              home / ".local/share/flatpak/exports/share"]
    return list(dict.fromkeys(root / "applications" for root in roots if root.is_absolute()))


def read_entry(path: Path) -> dict[str, str]:
    """Read only the main Desktop Entry group, preserving raw Exec syntax."""
    parser = configparser.ConfigParser(interpolation=None, delimiters=("=",), strict=True)
    parser.optionxform = str
    with path.open(encoding="utf-8-sig") as source:
        parser.read_file(source)
    return dict(parser.items("Desktop Entry")) if parser.has_section("Desktop Entry") else {}


def executable_path(exec_value: str) -> str:
    """Resolve a simple first executable; leave complex Exec quoting unresolved."""
    match = re.match(r'''^(?:"([^"\\%`$]+)"|([^\s"'\\%`$><|&;()=]+))(?=\s|$)''', exec_value.strip())
    if not match:
        return ""
    first = match.group(1) or match.group(2)
    if "/" in first and not os.path.isabs(first):
        return ""
    located = shutil.which(first)
    return os.path.abspath(located) if located else ""


def printable(value: str) -> str:
    """Escape control characters so metadata cannot manipulate terminal output."""
    return "".join(c if c.isprintable() else f"\\x{ord(c):02x}" for c in value)


def describe(path: Path, entry: dict[str, str], italian: bool) -> str:
    """Format paths, raw Exec and an explicit launcher command as a readable card."""
    def text(it: str, en: str) -> str:
        return it if italian else en

    path = path.absolute()
    raw = entry.get("Exec", "")
    executable = executable_path(raw)
    gio = shutil.which("gio")
    launch = shlex.join([os.path.abspath(gio), "launch", str(path)]) if gio else text(
        "gio non trovato: richiede libglib2.0-bin", "gio not found: requires libglib2.0-bin")
    fields = [
        ("NAME", entry.get("Name", path.stem)),
        ("DESKTOP FILE", str(path)),
        ("EXEC (RAW)", raw or text("assente: controllare D-Bus", "absent: check D-Bus")),
        ("EXECUTABLE", executable or text("non risolto: assente o sintassi complessa", "unresolved: missing or complex syntax")),
        ("TRYEXEC", entry.get("TryExec", "—")),
        ("TERMINAL", entry.get("Terminal", "false")),
        ("DBUS ACTIVATABLE", entry.get("DBusActivatable", "false")),
        ("NO DISPLAY", entry.get("NoDisplay", "false")),
        ("WORKING DIR", entry.get("Path", "—")),
        ("LAUNCH", launch),
    ]
    return "\n".join(f"{label:18} {printable(value)}" for label, value in fields)


def main() -> None:
    """Print candidate launchers; --match filters name, command and desktop path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", choices=("it", "en"), default="it")
    parser.add_argument("--match", default="")
    parser.add_argument("--directory", type=Path, action="append", help="Scan only these directories")
    args = parser.parse_args()
    candidates: set[Path] = set()
    for root in args.directory or launcher_directories():
        if root.is_dir():
            candidates.update(p.absolute() for p in root.rglob("*.desktop") if p.is_file())
    found = 0
    for path in sorted(candidates):
        try:
            entry = read_entry(path)
        except (OSError, UnicodeError, configparser.Error) as error:
            print(f"SKIP {printable(str(path))}: {printable(str(error))}", file=sys.stderr)
            continue
        if entry.get("Type") != "Application" or entry.get("Hidden") == "true":
            continue
        haystack = " ".join([entry.get("Name", ""), entry.get("Exec", ""), str(path)])
        if args.match.casefold() not in haystack.casefold():
            continue
        found += 1
        print(f"\n[{found:03}] " + "─" * 55)
        print(describe(path, entry, args.lang == "it"))
    print(f"\nTOTAL: {found}")


if __name__ == "__main__":
    main()
