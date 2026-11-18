"""Build the portable executable, the store-ready extension archive, and a
platform distribution zip.

Usage: python tools/build_portable.py [--skip-exe]
Windows, macOS and Linux are supported; PyInstaller is required for the binary.
"""

from __future__ import annotations

import argparse
import platform
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
def _converter_repo() -> Path:
    for candidate in (ROOT / "vendor" / "LCSC_Kicad_import", ROOT.parent / "LCSC_Kicad_import"):
        if (candidate / "plugins" / "lcsc_project_import.py").is_file():
            return candidate
    return ROOT / "vendor" / "LCSC_Kicad_import"


IMPORT_REPO = _converter_repo()
PLUGINS = IMPORT_REPO / "plugins"
EASYEDA = PLUGINS / "easyeda2kicad"
EXTENSION = ROOT / "extension"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
QUICKSTART = ROOT / "docs" / "使用说明.txt"
NAME = "LCSC-KiCad-Bridge"
BINARY = NAME + (".exe" if sys.platform == "win32" else "")


def version() -> str:
    text = (ROOT / "server" / "bridge_server.py").read_text(encoding="utf-8")
    match = re.search(r'^VERSION = "([^"]+)"', text, re.M)
    if not match:
        raise SystemExit("VERSION not found in server/bridge_server.py")
    return match.group(1)


def platform_slug() -> str:
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
    if sys.platform == "win32":
        return f"windows-{arch}"
    if sys.platform == "darwin":
        return f"macos-{arch}"
    return f"linux-{arch}"


def require_converter() -> None:
    for path in (PLUGINS / "lcsc_project_import.py", EASYEDA / "easyeda2kicad" / "__init__.py"):
        if not path.is_file():
            raise SystemExit(f"missing converter file: {path}\nrun: git submodule update --init --recursive")


def build_exe() -> Path:
    require_converter()
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
        "--name", NAME, "--console",
        "--distpath", str(DIST), "--workpath", str(BUILD), "--specpath", str(BUILD),
        "--paths", str(PLUGINS), "--paths", str(EASYEDA),
        "--collect-submodules", "easyeda2kicad",
        "--hidden-import", "lcsc_project_import",
        "--hidden-import", "impart_easyeda",
        "--hidden-import", "lcsc_download_cache",
        "--hidden-import", "lcsc_model_download",
        str(ROOT / "server" / "bridge_server.py"),
    ]
    print(" ".join(command), flush=True)
    subprocess.run(command, check=True)
    binary = DIST / BINARY
    if not binary.is_file():
        raise SystemExit("PyInstaller finished without producing the executable")
    return binary


def extension_zip() -> Path:
    target = DIST / "extension-store.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(EXTENSION.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(EXTENSION).as_posix())
    return target


def bundle(binary: Path) -> Path:
    target = DIST / f"{NAME}-{version()}-{platform_slug()}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(binary, BINARY)
        if QUICKSTART.is_file():
            archive.write(QUICKSTART, "使用说明.txt")
        for path in sorted(EXTENSION.rglob("*")):
            if path.is_file():
                archive.write(path, f"extension/{path.relative_to(EXTENSION).as_posix()}")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-exe", action="store_true", help="only rebuild the extension archive")
    args = parser.parse_args()
    DIST.mkdir(exist_ok=True)
    archive = extension_zip()
    print(f"extension: {archive} ({archive.stat().st_size} bytes)", flush=True)
    if args.skip_exe:
        return 0
    binary = build_exe()
    print(f"binary: {binary} ({binary.stat().st_size} bytes)", flush=True)
    package = bundle(binary)
    print(f"bundle: {package} ({package.stat().st_size} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
