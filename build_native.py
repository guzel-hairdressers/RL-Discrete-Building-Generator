#!/usr/bin/env python3
"""Build Module Lab's small native geometry library on Linux or macOS."""

from __future__ import annotations

import argparse
import ctypes
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


ABI_VERSION = 3
BASE_DIR = Path(__file__).resolve().parent
SOURCE = BASE_DIR / "fast_geometry.c"


def output_path() -> Path:
    if sys.platform == "darwin":
        return BASE_DIR / "libfast_geometry.dylib"
    if sys.platform.startswith("linux"):
        return BASE_DIR / "libfast_geometry.so"
    raise SystemExit("native geometry builds are supported on Linux and macOS")


def compiler_command() -> list[str]:
    configured = os.environ.get("CC", "").strip()
    if configured:
        return shlex.split(configured)
    preferred = ("clang", "cc", "gcc") if sys.platform == "darwin" else ("cc", "clang", "gcc")
    for candidate in preferred:
        resolved = shutil.which(candidate)
        if resolved:
            return [resolved]
    raise SystemExit("no C compiler found; set CC to a C11 compiler")


def build(debug: bool = False) -> Path:
    destination = output_path()
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    command = compiler_command() + [
        "-std=c11",
        "-fPIC",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-pedantic",
        "-O0" if debug else "-O3",
    ]
    if debug:
        command.append("-g")
    if sys.platform == "darwin":
        command.extend(["-dynamiclib", "-o", str(temporary), str(SOURCE)])
    else:
        command.extend(["-shared", "-o", str(temporary), str(SOURCE), "-lm"])

    try:
        subprocess.run(command, cwd=BASE_DIR, check=True)
        library = ctypes.CDLL(str(temporary))
        library.fast_geometry_abi_version.argtypes = []
        library.fast_geometry_abi_version.restype = ctypes.c_int
        actual_abi = int(library.fast_geometry_abi_version())
        if actual_abi != ABI_VERSION:
            raise RuntimeError(
                f"built native ABI {actual_abi}, expected ABI {ABI_VERSION}"
            )
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", action="store_true", help="remove the platform library and exit")
    parser.add_argument("--debug", action="store_true", help="build an unoptimized library with debug symbols")
    arguments = parser.parse_args()
    destination = output_path()
    if arguments.clean:
        destination.unlink(missing_ok=True)
        print(f"removed {destination}")
        return 0
    built = build(debug=arguments.debug)
    print(f"built {built} (ABI {ABI_VERSION})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
