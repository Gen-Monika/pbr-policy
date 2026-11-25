#!/usr/bin/env python3
"""Install documented host integrations idempotently, with preflight and backups.

Only verified upstream baselines produce introduction patches. New project-owned
headers are copied separately; historical incremental diffs stay separate. ASPECT
solver/core use official v2.4.0 baselines recorded in build-sources.json.
Verify source_changes.json and build_report.txt. Rollback: restore listed backups
to their exact original locations; do not reset or clean a whole source tree.
"""
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys


def sha(data):
    return hashlib.sha256(data).hexdigest()


def apply_unified(data, patch, reverse=False):
    """Exact context only; unique anchors allow harmless upstream line shifts."""
    lines = data.decode("utf-8").splitlines(keepends=True)
    diff = patch.read_text(encoding="utf-8").splitlines(keepends=True)
    if reverse:
        for n in range(2, len(diff)):
            line = diff[n]
            if line.startswith("@@"):
                diff[n] = re.sub(r"@@ -(\d+(?:,\d+)?) \+(\d+(?:,\d+)?) @@",
                                 lambda m: f"@@ -{m[2]} +{m[1]} @@", line)
            elif line.startswith("+"):
                diff[n] = "-" + line[1:]
            elif line.startswith("-"):
                diff[n] = "+" + line[1:]
    i, search_from, delta = 2, 0, 0
    while i < len(diff):
        if not diff[i].startswith("@@"):
            i += 1
            continue
        header = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", diff[i])
        if not header:
            raise ValueError(f"Invalid hunk: {patch}")
        i += 1
        old, new = [], []
        while i < len(diff) and not diff[i].startswith("@@"):
            line = diff[i]
            if line.startswith("\\"):
                raise ValueError("No-newline patches need explicit handling")
            if line[:1] in (" ", "-"):
                old.append(line[1:])
            if line[:1] in (" ", "+"):
                new.append(line[1:])
            i += 1
        if len(old) != int(header[2] or 1) or len(new) != int(header[4] or 1):
            raise ValueError(f"Hunk count mismatch: {patch}")
        expected_pos = int(header[1]) - 1 + delta
        if expected_pos >= search_from and lines[expected_pos:expected_pos + len(old)] == old:
            positions = [expected_pos]
        else:
            positions = [n for n in range(search_from, len(lines) - len(old) + 1) if lines[n:n + len(old)] == old]
        if len(positions) != 1:
            raise ValueError(f"Patch context missing/ambiguous ({len(positions)} matches): {patch}")
        pos = positions[0]
        lines[pos:pos + len(old)] = new
        search_from = pos + len(new)
        delta = pos - (int(header[1]) - 1) + len(new) - len(old)
    return "".join(lines).encode("utf-8")


def install(host, package, source, job):
    contrib = package / "contrib"
    spec = json.loads((contrib / "build-sources.json").read_text())[host]
    updates, records = [], []
    for rel, required in spec.get("required_prepatched", {}).items():
        path = source / rel
        if not path.is_file() or sha(path.read_bytes()) != required:
            raise ValueError(f"ASPECT integration not established: {rel}. No upstream baseline was supplied; use the documented prepatched tree or provide its official baseline. No diff is fabricated.")
    for item in spec["files"]:
        path = source / item["target"]
        data = path.read_bytes()
        if sha(data) == item["after_sha256"]:
            records.append({"file": str(path), "state": "already_current", "sha256": sha(data)})
            continue
        try:
            new = apply_unified(data, contrib / item["patch"])
        except ValueError as forward_error:
            try:
                apply_unified(data, contrib / item["patch"], reverse=True)
            except ValueError:
                raise forward_error
            records.append({"file": str(path), "state": "already_patched_exact_context", "sha256": sha(data)})
            continue
        if sha(data) == item["before_sha256"] and sha(new) != item["after_sha256"]:
            raise ValueError(f"Patch result differs from supplied integration: {path}")
        updates.append((path, data, new))
    if "header" in spec:
        path = source / spec["header_target"]
        new = (contrib / spec["header"]).read_bytes()
        old = path.read_bytes() if path.exists() else None
        if old != new:
            if old is not None and sha(old) not in spec["previous_header_sha256"]:
                raise ValueError(f"Unrecognized local policy header: {path}; retain it and select a clean or documented source tree")
            updates.append((path, old, new))
    # All files have been checked before the first source mutation.
    for path, old, new in updates:
        backup = None
        if old is not None:
            backup = job / "source-backups" / path.relative_to(source)
            backup.parent.mkdir(parents=True, exist_ok=True)
            with backup.open("xb") as f:
                f.write(old)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(new)
        records.append({"file": str(path), "backup": str(backup) if backup else None,
                        "before_sha256": sha(old) if old is not None else None,
                        "after_sha256": sha(new), "state": "updated"})
    (job / "source_changes.json").write_text(json.dumps(records, indent=2) + "\n")
    print(f"{host}: source integration checked; {len(updates)} files updated")


def cache(source, build):
    path = build / "CMakeCache.txt"
    if not path.exists():
        return
    values = {}
    for line in path.read_text(errors="replace").splitlines():
        match = re.match(r"([^:#]+):[^=]+=(.*)", line)
        if match:
            values[match[1]] = match[2]
    if Path(values.get("CMAKE_HOME_DIRECTORY", "")).resolve() != source.resolve():
        raise ValueError("CMake cache belongs to a different source; select a new BUILD directory")
    for var, env in [("CMAKE_C_COMPILER", "CC"), ("CMAKE_CXX_COMPILER", "CXX"), ("CMAKE_Fortran_COMPILER", "FC")]:
        desired = os.environ.get(env)
        if desired and var in values:
            desired = shutil.which(desired) or desired
            if Path(values[var]).resolve() != Path(desired).resolve():
                raise ValueError(f"Compiler differs from existing {var}; select a new BUILD directory")


def copy_sources(source, dest, job):
    # Only project-owned plugin sources; no full host tree, .git or evidence copy.
    state_file = dest / "pbr-source-state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    paths = [p for p in source.rglob("*") if p.is_file() and p.suffix in (".C", ".H") or p.is_file() and p.parent.name == "Make"]
    updates = []
    for path in paths:
        rel = str(path.relative_to(source))
        out = dest / rel
        new = path.read_bytes()
        old = out.read_bytes() if out.exists() else None
        if old is not None and old != new and sha(old) != state.get(rel):
            raise ValueError(f"Local edits in build copy: {out}; select a fresh BUILD directory")
        updates.append((out, rel, old, new))
    for out, rel, old, new in updates:
        if old != new:
            if old is not None:
                backup = job / "plugin-source-backups" / rel
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes(old)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(new)
        state[rel] = sha(new)
    state_file.write_text(json.dumps(state, indent=2) + "\n")


if __name__ == "__main__":
    try:
        if sys.argv[1] == "cache": cache(Path(sys.argv[2]), Path(sys.argv[3]))
        elif sys.argv[1] == "copy": copy_sources(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
        else: install(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
    except (ValueError, OSError) as error:
        print(f"SOURCE ERROR: {error}", file=sys.stderr)
        sys.exit(2)
