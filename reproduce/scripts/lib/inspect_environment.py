#!/usr/bin/env python3
"""Read toolchain/version facts without starting a host solver or dumping the environment.
Records recommendations, not version admission gates. Verify build_report.txt.
Rollback: select the previous reporter; this module modifies no inputs or policies.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def command(args):
    try:
        r = subprocess.run(args, text=True, errors="replace", stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=10)
        return r.stdout.strip()[:1500] if r.returncode == 0 else "UNKNOWN"
    except (OSError, subprocess.TimeoutExpired):
        return "UNKNOWN"


def report(host):
    print("\nVERSION/TOOLCHAIN FACTS (versions below are recommendations, never equality gates)")
    for name in ("gcc", "g++", "gfortran", "cmake", "make", "mpicc", "mpicxx", "mpifort"):
        path = shutil.which(name)
        if path:
            print(f"{name}: {path}: {command([path, '--version']).splitlines()[0]}")
            if name.startswith("mpi"):
                print(f"{name} backend: {command([path, '--showme:command'])}")
    source = os.environ.get(f"PBR_{host.upper()}_SRC")
    source_text = ""
    if source:
        print("source:", source)
        print("source revision:", command(["git", "-C", source, "describe", "--always", "--dirty"]))
        for rel in ("CMakeLists.txt", "Project.toml", "include/aspect/global.h"):
            path = Path(source) / rel
            if path.is_file():
                content = path.read_text(errors="replace")
                source_text += content + "\n"
                lines = [s.strip() for s in content.splitlines()
                         if re.search(r"(?:ASPECT_VERSION|ELMER_FEM_(?:MAJOR|MINOR)_VERSION|^version\s*=)", s, re.I)]
                for line in lines[:12]:
                    print(f"{rel}: {line}")
    recommendations = {"aspect": "ASPECT 2.4.0 / deal.II 9.3.2 / Trilinos 13.2.0 / p4est 2.2.0",
                       "lamem": "LaMEM 3.3.0 (Julia only for optional checkgetrestore)", "elmer": "Elmer 26.2",
                       "moose": "documented MOOSE checkout / its libMesh and PETSc / reference Open MPI 5.0.10",
                       "openfoam": "OpenFOAM OpenCFD v2406 / PETSc 3.25 series"}
    print("Suggested (used in evidence):", recommendations.get(host, "see selected hosts"))
    actual, suggested = None, {"aspect": "2.4.0", "lamem": "3.3.0", "elmer": "26.2"}.get(host)
    if host == "lamem":
        m = re.search(r'^version\s*=\s*"([^"]+)"', source_text, re.M)
        actual = m[1] if m else None
    elif host == "elmer":
        parts = [re.search(r"ELMER_FEM_" + part + r"_VERSION\s+\"?(\d+)", source_text) for part in ("MAJOR", "MINOR")]
        actual = ".".join(m[1] for m in parts) if all(parts) else None
    elif host == "aspect":
        m = re.search(r'ASPECT_VERSION\s+"?([\d]+\.[\d]+\.[\d]+)', source_text)
        actual = m[1] if m else None
    if suggested:
        print("Host detected version:", actual or "UNKNOWN (inspect source revision and build output)")
        if actual and actual != suggested:
            print("WARNING: host differs from suggested version; counts may differ; assess comparability")
    if host == "openfoam":
        version = os.environ.get("WM_PROJECT_VERSION", "UNKNOWN")
        print("OpenFOAM actual:", version)
        if version.lstrip("vV") != "2406":
            print("WARNING: different OpenFOAM version; API/input compatibility and counts require evaluation")
    pdir = os.environ.get("PETSC_DIR")
    if pdir:
        paths = [Path(pdir) / os.environ.get("PETSC_ARCH", "") / "include", Path(pdir) / "include"]
        found = set()
        for include in paths:
            for name in ("petscversion.h", "petscconf.h"):
                path = include / name
                if path.is_file() and path.resolve() not in found:
                    found.add(path.resolve())
                    text = path.read_text(errors="replace")
                    for line in text.splitlines():
                        if re.match(r"#define PETSC_(?:VERSION_(?:MAJOR|MINOR|SUBMINOR)|USE_(?:COMPLEX|64BIT_INDICES|REAL_)|HAVE_MPIUNI)", line):
                            print(f"{path}: {line}")
                    if name == "petscversion.h":
                        m = re.search(r"#define PETSC_VERSION_MINOR\s+(\d+)", text)
                        if m and m[1] != "25":
                            print("WARNING: different PETSc version; repeated counts may differ; assess comparability")
    launcher = os.environ.get(f"PBR_{host.upper()}_MPIEXEC")
    print("Selected launcher:", launcher or "UNRESOLVED (runtime selection must be unambiguous)")
    if launcher:
        print(command([launcher, "--version"]))


if __name__ == "__main__":
    report(sys.argv[1])
