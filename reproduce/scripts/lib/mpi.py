#!/usr/bin/env python3
"""S-01: report actual MPI linkage; never guess compatibility from directory prefixes.
Verify match output plus mpi_smoke.log. No writes or execution of solver binaries.
Rollback: select a previous launcher configuration, not a different policy.
"""
import os
import ctypes
from pathlib import Path
import re
import shutil
import subprocess
import sys


def launchers():
    found = set()
    for directory in os.get_exec_path():
        for name in ("mpirun", "mpiexec"):
            path = Path(directory) / name
            if path.is_file() and os.access(path, os.X_OK):
                found.add(str(path.resolve()))
    return sorted(found)


def linked(path):
    call = subprocess.run(["ldd", path], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if "not found" in call.stdout:
        raise RuntimeError(f"Unresolved dependency: {path}\n{call.stdout}")
    libs = set()
    for line in call.stdout.splitlines():
        match = re.search(r"\blib(?:mpi|mpich)(?:\.so[^ ]*)?\s+=>\s+(\S+)", line)
        if match:
            libs.add(str(Path(match[1]).resolve()))
    return libs


def main():
    if sys.argv[1] == "library-version":
        libs = linked(sys.argv[2])
        if len(libs) != 1:
            raise RuntimeError("Cannot identify the actual MPI library before launch")
        lib = ctypes.CDLL(next(iter(libs)))
        output, length = ctypes.create_string_buffer(16384), ctypes.c_int()
        # MPI_Get_library_version is permitted before MPI_Init; no ranks launched.
        fn = lib.MPI_Get_library_version
        fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
        if fn(output, ctypes.byref(length)) != 0:
            raise RuntimeError("MPI library version query failed")
        print(output.value.decode(errors="replace"))
        return
    if sys.argv[1] == "launchers":
        print("\n".join(launchers()))
        return
    if sys.argv[1] == "inventory":
        for path in launchers():
            r = subprocess.run([path, "--version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
            print(path, "\n", r.stdout[:2000])
        return
    if sys.argv[1] == "version":
        launcher = Path(sys.argv[2]).read_text()
        runtime = Path(sys.argv[3]).read_text()
        l = re.search(r"(?:Open MPI|OpenRTE|Open RTE)[^\d]*(\d+)", launcher)
        r = re.search(r"Open MPI[^\d]*(\d+)", runtime)
        if l and r and l[1] != r[1]:
            raise RuntimeError("Launcher and MPI library report different Open MPI major versions")
        print("MPI launcher/runtime major version:", l[1] if l else "UNKNOWN", r[1] if r else "UNKNOWN")
        return
    smoke = linked(sys.argv[2])
    targets = set()
    for path in sys.argv[3:]:
        libs = linked(path)
        targets.update(libs)
        print(f"MPI linkage {path}: {sorted(libs) or 'UNKNOWN/static'}")
    print(f"MPI probe linkage: {sorted(smoke) or 'UNKNOWN/static'}")
    if len(smoke) != 1 or targets != smoke:
        raise RuntimeError("MPI linkage mismatch/unknown: configure matching MPICC/MPIEXEC; static MPI requires explicit investigation")
    print("MPI probe and host objects resolve the same MPI library; runtime collective smoke follows")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"MPI ERROR: {error}", file=sys.stderr)
        sys.exit(2)
