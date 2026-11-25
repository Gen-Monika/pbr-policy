#!/usr/bin/env python3
"""Runtime plumbing, not a solver or policy implementation (Python >= 3.8).

Fixes S-04/05/06 and B-02/03/04/05/06: independent jobs, explicit return codes,
process-group ownership, trace schema and completion checks. Verify status.json,
execution-*.json and result.json. Roll back by selecting previous scripts; retain
job directories. No cleanup/deletion, credential reading, or network operations.
"""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time


def write_json(path, value):
    path = Path(path)
    pending = path.with_name(path.name + f".pending-{os.getpid()}")
    pending.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pending.replace(path)  # readers never observe a half-written status record


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resources():
    cpus = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)
    memory = None
    try:
        m = re.search(r"MemAvailable:\s+(\d+)", Path("/proc/meminfo").read_text())
        memory = int(m[1]) * 1024
    except (OSError, TypeError):
        pass
    # Check both unified and legacy hierarchies, including parent quotas.
    roots = [Path("/sys/fs/cgroup")]
    try:
        for line in Path("/proc/self/cgroup").read_text().splitlines():
            _, controllers, rel = line.split(":", 2)
            bases = [Path("/sys/fs/cgroup")] if not controllers else [Path("/sys/fs/cgroup") / x for x in controllers.split(",")]
            for base in bases:
                node = base / rel.lstrip("/")
                while node == base or base in node.parents:
                    roots.append(node)
                    if node == base:
                        break
                    node = node.parent
    except OSError:
        pass
    for root in set(roots):
        try:
            quota, period = (root / "cpu.max").read_text().split()
            if quota != "max":
                cpus = min(cpus, max(1, int(quota) // int(period)))
        except (OSError, ValueError):
            pass
        try:
            quota = int((root / "cpu.cfs_quota_us").read_text())
            period = int((root / "cpu.cfs_period_us").read_text())
            if quota > 0:
                cpus = min(cpus, max(1, quota // period))
        except (OSError, ValueError):
            pass
        for lim_name, used_name in [("memory.max", "memory.current"), ("memory.limit_in_bytes", "memory.usage_in_bytes")]:
            try:
                limit = int((root / lim_name).read_text())
                available = max(0, limit - int((root / used_name).read_text()))
                memory = min(memory, available) if memory is not None else available
            except (OSError, ValueError):
                pass
    return {"available_cpus": cpus, "available_memory_bytes": memory,
            "default_np": min(8, cpus),
            "default_jobs": min(8, cpus, max(1, (memory or 2**30) // (2 * 2**30)))}


def process_identity(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return {"pid": pid, "pgid": os.getpgid(pid), "start_ticks": fields[19]}
    except (OSError, IndexError):
        return {"pid": pid, "pgid": None, "start_ticks": None}


def stop_requested(directory):
    root = Path(directory).resolve()
    return any((parent / "stop-requested.json").is_file() for parent in (root, *root.parents))


def check_paths(package, paths):
    package = Path(package).resolve()
    protected = [package / name for name in ("expected", "cases", "contrib", "scripts", "config")]
    for item in paths:
        if not item:
            continue
        target = Path(item).resolve()
        if target == package or any(target == root or root in target.parents for root in protected):
            raise ValueError(f"Output/build path overlaps protected package content: {target}")


def effective_inputs(directory):
    job = Path(directory)
    path = job / "inputs.json"
    record = json.loads(path.read_text())
    record["final_sha256"] = {str(p.relative_to(job / "case")): fingerprint(p)
                              for p in (job / "case").rglob("*") if p.is_file()}
    record["final_changed"] = [p for p, sha in record["final_sha256"].items()
                               if record["original_sha256"].get(p) != sha]
    write_json(path, record)


def terminate_owned(identity, grace):
    identity = {key: identity.get(key) for key in ("pid", "pgid", "start_ticks")}
    pid = identity["pid"]
    current = process_identity(pid)
    if current["start_ticks"] is None and not Path(f"/proc/{pid}").exists():
        return  # already exited; never signal a replacement process
    if not identity.get("start_ticks") or current != identity or current["pgid"] != pid:
        raise RuntimeError("Process identity changed or is unknown; refusing to signal")
    os.killpg(pid, signal.SIGTERM)
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def execute(args):
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise ValueError("Empty command")
    job = Path(args.directory)
    if stop_requested(job):
        return 143
    meta = job / ("execution-" + args.name + ".json")
    log = job / (args.name + ".log")
    if meta.exists() or log.exists():
        raise RuntimeError(f"Refusing to overwrite execution record: {args.name}")
    record = {"command": command, "cwd": os.getcwd(), "timeout_s": args.timeout,
              "started_unix": time.time(), "finished": False, "timed_out": False}
    start = time.monotonic()
    with log.open("xb") as out:
        child = subprocess.Popen(command, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        identity = process_identity(child.pid)
        record.update(identity)
        write_json(meta, record)
        interrupted = []

        def stop(signum, _frame):
            interrupted.append(signum)
            terminate_owned(identity, args.grace)

        previous = {s: signal.signal(s, stop) for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
        try:
            while child.poll() is None:
                if stop_requested(job):
                    interrupted.append(signal.SIGTERM)
                    terminate_owned(identity, args.grace)
                    child.wait()
                    break
                if args.timeout > 0 and time.monotonic() - start >= args.timeout:
                    record["timed_out"] = True
                    terminate_owned(identity, args.grace)
                    child.wait()
                    break
                try:
                    child.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
        native_rc = child.returncode
        rc = 124 if record["timed_out"] else (128 + interrupted[-1] if interrupted else (native_rc if native_rc >= 0 else 128 - native_rc))
        record.update(finished=True, child_returncode=native_rc, returncode=rc,
                      wall_seconds=time.monotonic() - start, ended_unix=time.time())
        write_json(meta, record)
    return rc


def background(args):
    job = Path(args.directory)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    log = job / "background.log"
    with log.open("xb") as out:
        # start_new_session gives setsid semantics; ignore HUP for SSH disconnects.
        def detached():
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out,
                                 stderr=subprocess.STDOUT, start_new_session=True, preexec_fn=detached)
    write_json(job / "background.json", dict(process_identity(child.pid), command=command))
    print(f"Background controller: {job}; worker: {job / 'worker'}; pid={child.pid}")


def manage(args):
    root = Path(args.directory).resolve()
    if args.job_action == "stop":
        if not (root / "status.json").is_file():
            raise ValueError("Not a recorded PBR job directory")
        write_json(root / "stop-requested.json", {"requested_unix": time.time()})
        # Prefer the currently running command's own session, not name matching.
        records = list(root.rglob("execution-*.json"))
        for path in records:
            item = json.loads(path.read_text())
            if not item.get("finished"):
                terminate_owned(item, args.grace)  # select identity fields below
        print("Stop requested; owned commands are stopped and subsequent batch entries are disabled.")
        return 0
    deadline = time.monotonic() + args.wait
    while True:
        paths = list(root.rglob("status.json"))
        items = [{"file": str(p), **json.loads(p.read_text())} for p in paths]
        print(json.dumps(items, ensure_ascii=False))
        worker_pending = (root / "background.json").exists() and not (root / "worker/status.json").exists()
        if args.job_action == "status":
            return 0
        if items and not worker_pending and all(x.get("finished") for x in items):
            return next((x["wrapper_returncode"] for x in items if x.get("wrapper_returncode")), 0)
        if time.monotonic() >= deadline:
            return 124
        time.sleep(min(2, max(0, deadline - time.monotonic())))


def replace_one(text, pattern, replacement):
    text, count = re.subn(pattern, replacement, text, flags=re.M)
    if count != 1:
        raise ValueError(f"Expected one input anchor, found {count}: {pattern}")
    return text


def prepare(args):
    root, target = Path(args.package), Path(args.directory) / "case"
    host, profile = args.host, os.environ["PROFILE"]
    if profile not in ("historical", "c1b"):
        raise ValueError("PROFILE must be historical or c1b")
    if host == "openfoam":
        source = root / "cases/openfoam" / os.environ["CFG"]
    elif host == "aspect":
        source = root / "cases/aspect" / ("blankenbach" if os.environ["CASE"] == "blankenbach" else "tosi")
    else:
        source = root / "cases" / {"moose": "moose", "lamem": "lamem/rifting2d", "elmer": "elmer/fssa_perlin2d"}[host]
    shutil.copytree(source, target)
    before = {str(p.relative_to(target)): fingerprint(p) for p in target.rglob("*") if p.is_file()}
    if host == "aspect" and os.environ["CASE"] == "blankenbach":
        path = target / "case.prm"
        text = path.read_text()
        # Replace duplicate declarations by a single effective declaration.
        text = re.sub(r"^set End time\s*=.*\n?", "", text, flags=re.M)
        text += "\nset End time = " + ("0.03" if profile == "c1b" else "0.1") + "\n"
        path.write_text(text)
    elif host == "lamem":
        src = target / "Rifting2D_MultigridSolver.dat"
        text = src.read_text()
        steps = os.environ.get("NSTEPS") or ("120" if profile == "c1b" else "200")
        if not steps.isdigit() or int(steps) < 1:
            raise ValueError("NSTEPS must be a positive integer")
        text = replace_one(text, r"^(\s*nstep_max\s*=\s*)\d+", lambda m: m[1] + steps)
        if profile == "c1b":
            text = replace_one(text, r"^(\s*nstep_out\s*=\s*)\d+", lambda m: m[1] + "100000")
        (target / "case.dat").write_text(text)
    elif host == "elmer":
        path = target / "stabilized.sif"
        text = path.read_text()
        text = replace_one(text, r"^(\s*Max Output Level\s*=\s*)\d+", lambda m: m[1] + "8")
        policy = os.environ["POLICY"]
        if policy not in ("off", "online", "fixed") or (policy == "fixed" and os.environ["K"] != "1"):
            raise ValueError("Elmer supports online, off, or native fixed K=1 only")
        match = re.search(r"^Solver\s+2\s*$.*?^End\s*$", text, re.M | re.S | re.I)
        if not match or not re.search(r'Equation\s*=\s*"Stokes-Vec"', match[0]):
            raise ValueError("Elmer Stokes-Vec Solver 2 anchor missing")
        block = re.sub(r"^\s*Linear System (?:Precondition Online|Timing|Residual Output)\s*=.*\n", "", match[0], flags=re.M | re.I)
        additions = "\n  Linear System Precondition Online = Logical " + ("True" if policy == "online" else "False")
        additions += "\n  Linear System Timing = Logical True\n  Linear System Residual Output = Integer 1\n"
        block = re.sub(r"^End\s*$", additions + "End", block, flags=re.M | re.I)
        text = text[:match.start()] + block + text[match.end():]
        path.write_text(text)
        (target / "ELMERSOLVER_STARTINFO").write_text("stabilized.sif\n")
    after = {str(p.relative_to(target)): fingerprint(p) for p in target.rglob("*") if p.is_file()}
    write_json(Path(args.directory) / "inputs.json", {"host": host, "profile": profile,
               "source": str(source), "original_sha256": before, "effective_sha256": after,
               "changed": [p for p in after if before.get(p) != after[p]]})


def summarize(args):
    job = Path(args.directory)
    case = job / "case"
    host = args.host
    result = {"host": host, "np": int(os.environ["NP"]), "profile": os.environ["PROFILE"],
              "trace_complete": False, "simulation_complete": False, "reference_accuracy": "not_checked",
              "expected_match": "not_checked", "traces": []}
    log = (job / "solve.log").read_text(errors="replace") if (job / "solve.log").exists() else ""
    record_path = job / "execution-solve.json"
    execution = json.loads(record_path.read_text()) if record_path.exists() else {}
    result["solver_returncode"] = execution.get("returncode")
    result["timed_out"] = execution.get("timed_out", False)
    markers = {"moose": r"Finished Executing", "aspect": r"Termination requested by criterion: end time",
               "elmer": r"ALL DONE", "lamem": r"(?:SIMULATION DONE|Simulation completed)", "openfoam": r"^End\s*$"}
    result["simulation_complete"] = bool(re.search(markers[host], log, re.M)) and execution.get("returncode") == 0
    if host == "moose":
        times = re.findall(r"Time Step\s+\d+.*?time\s*=\s*([\d.eE+-]+)", log)
        result["last_time"] = float(times[-1]) if times else None
        result["simulation_complete"] &= bool(times and float(times[-1]) >= 100 - 1e-8)
    if host == "elmer":
        if re.search(r"(?:FAILED|failed its reference)", log):
            result["reference_accuracy"] = "FAILED"
        elif re.search(r"PASSED", log):
            result["reference_accuracy"] = "PASSED_logged_check_only"
        result["partition"] = f"geometric -partition {os.environ['NP']} 1 1" if result["np"] > 1 else "serial"
    stem = {"moose": "pbr.csv", "lamem": "pbr.csv", "aspect": "trace.csv", "elmer": "pbr_trace.csv", "openfoam": "pbr_pc.csv"}[host]
    paths = [case / (stem + (f".r{r}" if result["np"] > 1 else "")) for r in range(result["np"])]
    decisions, timings = [], []
    for path in paths:
        if not path.is_file():
            continue
        with path.open(newline="") as stream:
            if host == "openfoam":
                rows = list(csv.reader(stream))
                fields = ["headerless_25_column_PC_trace"]
            else:
                reader = csv.DictReader(stream)
                rows = list(reader)
                fields = reader.fieldnames or []
                if not {"rebuild", "its", "build_ms", "solve_ms"}.issubset(fields):
                    raise ValueError(f"Unexpected trace schema: {path}")
        info = {"file": str(path), "data_rows": len(rows), "columns": fields}
        if host == "openfoam":
            if any(len(row) != 25 for row in rows):
                raise ValueError(f"Malformed OpenFOAM PC trace: {path}")
            info["total_builds"] = max((int(row[24]) for row in rows), default=0)
            info["rebuild_steps"] = len({r[0] for r in rows if float(r[6]) >= 0 and r[8] == "0"})
        else:
            info["decision_rebuilds"] = sum(float(r.get("rebuild") or 0) > 0 for r in rows)
            info["build_ms_positive_rows"] = sum(float(r.get("build_ms") or 0) > 0 for r in rows)
            info["total_its"] = sum(float(r.get("its") or 0) for r in rows)
            decisions.append([r.get("rebuild") for r in rows])
            timings.append([r.get("solve_ms") for r in rows])
        result["traces"].append(info)
    required = os.environ["POLICY"] != "off"
    if host == "elmer":
        required = os.environ["POLICY"] == "online"
    if host == "openfoam":
        required = os.environ.get("PBR_MODE") != "DIC"
    result["trace_required"] = required
    result["trace_complete"] = not required or (len(result["traces"]) == result["np"] and all(t["data_rows"] > 0 for t in result["traces"]))
    if decisions:
        result["same_rank_row_counts"] = len({len(r) for r in decisions}) == 1
        result["trace_complete"] &= result["same_rank_row_counts"]
        result["same_rank_decisions"] = all(r == decisions[0] for r in decisions)
        result["timing_columns_identical"] = len(timings) > 1 and all(r == timings[0] for r in timings)
        if os.environ.get("PBR_ALIGN") == "off" and result["timing_columns_identical"]:
            result["timing_note"] = "Inspect alignment/clock resolution: identical timing columns alone are not a proof"
    if host == "openfoam":
        result["steps"] = len(re.findall(r"^Time = ", log, re.M))
        result["total_its"] = sum(map(int, re.findall(r"Solving for p_rgh.*?No Iterations (\d+)", log)))
        result["fatal"] = bool(re.search(r"FOAM FATAL", log))
        result["simulation_complete"] &= not result["fatal"] and result["steps"] > 0
        control = (case / "system/controlDict").read_text()
        end = re.search(r"^\s*endTime\s+([\d.eE+-]+)\s*;", control, re.M)
        times = re.findall(r"^Time = ([\d.eE+-]+)", log, re.M)
        result["last_time"] = float(times[-1]) if times else None
        if end:
            result["simulation_complete"] &= bool(times and float(times[-1]) >= float(end[1]) - max(1e-8, abs(float(end[1])) * 1e-6))
        if os.environ.get("CHECK_EXPECTED") == "1":
            if result["np"] != 1 or result["profile"] != "historical" or os.environ.get("PBR_MODE") not in ("K1", "K3", "DIC"):
                raise ValueError("expected comparison only supports historical serial fixed/DIC runs")
            with (Path(args.package) / "expected/openfoam_iters.csv").open(newline="") as f:
                baseline = next(r for r in csv.DictReader(f) if r["config"] == os.environ["CFG"] and r["mode"] == os.environ["PBR_MODE"])
            result["expected_match"] = result["total_its"] == int(baseline["iters_exact"]) and result["steps"] == int(baseline["steps_exact"])
            if os.environ["PBR_MODE"] != "DIC":
                with (Path(args.package) / "expected/openfoam.csv").open(newline="") as f:
                    baseline_pc = next(r for r in csv.DictReader(f) if r["config"] == os.environ["CFG"] and r["mode"] == os.environ["PBR_MODE"])
                result["expected_match"] &= bool(result["traces"] and result["traces"][0]["total_builds"] == int(baseline_pc["nbuild_exact"]))
    write_json(job / "result.json", result)
    print(json.dumps(result, ensure_ascii=False))
    ok = result["simulation_complete"] and result["trace_complete"] and result["expected_match"] is not False
    if host != "openfoam" and os.environ.get("PBR_ALIGN") == "on":
        ok &= result.get("same_rank_decisions", True)
    return 0 if ok else 3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("resources")
    p = sub.add_parser("check-paths"); p.add_argument("package"); p.add_argument("paths", nargs="*")
    p = sub.add_parser("check-stop"); p.add_argument("directory")
    p = sub.add_parser("effective-inputs"); p.add_argument("directory")
    c = sub.add_parser("configuration"); c.add_argument("path"); c.add_argument("keys", nargs="*")
    s = sub.add_parser("status"); s.add_argument("directory"); s.add_argument("rc", type=int)
    for name in ("execute", "background"):
        p = sub.add_parser(name); p.add_argument("directory")
        if name == "execute":
            p.add_argument("name"); p.add_argument("timeout", type=float); p.add_argument("grace", type=float)
        p.add_argument("command", nargs=argparse.REMAINDER)
    m = sub.add_parser("job"); m.add_argument("job_action", choices=["status", "wait", "stop"])
    m.add_argument("directory"); m.add_argument("--wait", type=float, default=30); m.add_argument("--grace", type=float, default=15)
    for name in ("prepare", "summarize"):
        p = sub.add_parser(name); p.add_argument("host"); p.add_argument("package"); p.add_argument("directory")
    args = parser.parse_args()
    if args.action == "resources": print(json.dumps(resources()))
    elif args.action == "check-paths": check_paths(args.package, args.paths)
    elif args.action == "check-stop": return 143 if stop_requested(args.directory) else 0
    elif args.action == "effective-inputs": effective_inputs(args.directory)
    elif args.action == "configuration": write_json(args.path, {k: os.environ.get(k) for k in args.keys})
    elif args.action == "status": write_json(Path(args.directory) / "status.json", {"finished": True, "wrapper_returncode": args.rc, "ended_unix": time.time()})
    elif args.action == "execute": return execute(args)
    elif args.action == "background": return background(args)
    elif args.action == "job": return manage(args)
    elif args.action == "prepare": return prepare(args)
    elif args.action == "summarize": return summarize(args)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, StopIteration) as error:
        print(f"PBR ERROR: {error}", file=sys.stderr)
        sys.exit(2)
