#!/usr/bin/env python3
"""Offline packaging checks; no solvers, network, or expected/ writes.
Run with Python >=3.8; PBR_TEST_BASH selects Bash on Windows. Fixtures remain in
the repository tmp/ directory for inspection. Linux-only process tests are skipped
elsewhere. These are infrastructure checks, not server/physics acceptance.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
import uuid

PACKAGE = Path(__file__).resolve().parents[2]
REPO = PACKAGE.parent
HANDOFF = REPO / "docs/handoff/c1b_source_20261107"
FIXTURES = REPO / "tmp/d0_stage2_20261107/tests" / uuid.uuid4().hex
FIXTURES.mkdir(parents=True)


def module(name):
    spec = importlib.util.spec_from_file_location(name, PACKAGE / "scripts/lib" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


sources, runtime = module("sources"), module("pbr")


class PackagingTests(unittest.TestCase):
    def folder(self):
        path = FIXTURES / uuid.uuid4().hex
        path.mkdir()
        return path

    def test_patch_outputs_and_second_application(self):
        records = json.loads((PACKAGE / "contrib/build-sources.json").read_text())
        for host, record in records.items():
            self.assertNotIn("\\", record.get("header", ""))
            for item in record["files"]:
                self.assertNotIn("\\", item["patch"])
            root, first, second = self.folder(), self.folder(), self.folder()
            for item in record["files"]:
                name = Path(item["target"]).name
                dest = root / item["target"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                baseline = HANDOFF / host / (name + ".orig")
                if baseline.exists():
                    data = baseline.read_bytes()
                else:
                    # core/solver official files were fetched and checked separately.
                    # Recover that exact fixture offline; the published upstream hash
                    # prevents treating the already-patched handoff as a clean source.
                    data = sources.apply_unified((HANDOFF / host / name).read_bytes(),
                                                 PACKAGE / "contrib" / item["patch"], reverse=True)
                    self.assertEqual(sources.sha(data), item["before_sha256"])
                dest.write_bytes(data)
            for rel in record.get("required_prepatched", {}):
                dest = root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes((HANDOFF / host / Path(rel).name).read_bytes())
            sources.install(host, PACKAGE, root, first)
            for item in record["files"]:
                self.assertEqual(sources.sha((root / item["target"]).read_bytes()), item["after_sha256"])
            sources.install(host, PACKAGE, root, second)
            self.assertFalse((second / "source-backups").exists())

    def test_unknown_header_preflight_changes_nothing(self):
        root, job = self.folder(), self.folder()
        target = root / "framework/src/systems/NonlinearSystem.C"
        target.parent.mkdir(parents=True)
        original = (HANDOFF / "moose/NonlinearSystem.C.orig").read_bytes()
        target.write_bytes(original)
        header = root / "framework/include/utils/pbr_policy.h"
        header.parent.mkdir(parents=True)
        header.write_text("local changes must be retained\n")
        with self.assertRaisesRegex(ValueError, "Unrecognized"):
            sources.install("moose", PACKAGE, root, job)
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(header.read_text(), "local changes must be retained\n")

    def test_compatible_upstream_line_shift_remains_idempotent(self):
        root, job = self.folder(), self.folder()
        target = root / "framework/src/systems/NonlinearSystem.C"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"// compatible upstream comment\n" + (HANDOFF / "moose/NonlinearSystem.C.orig").read_bytes())
        sources.install("moose", PACKAGE, root, job)
        after = target.read_bytes()
        sources.install("moose", PACKAGE, root, self.folder())
        self.assertEqual(target.read_bytes(), after)

    def test_aspect_missing_source_is_rejected(self):
        with self.assertRaises(FileNotFoundError):
            sources.install("aspect", PACKAGE, self.folder(), self.folder())

    def test_config_precedence_paths_and_host_isolation(self):
        root = self.folder()
        (root / "cases").mkdir(); (root / "config").mkdir()
        shutil.copyfile(PACKAGE / "config/site.sh", root / "config/site.sh")
        (root / "config/site.local.sh").write_text("NP=3\nPBR_MOOSE_PETSC_DIR=/local/moose\nPBR_LAMEM_PETSC_DIR=/local/lamem\n")
        bash = os.environ.get("PBR_TEST_BASH", "bash")
        script = 'source "$1"; pbr_load_config moose "PBR_ROOT=$2" NP=5; printf "%s|%s|%s|%s" "$NP" "$PBR_MOOSE_PETSC_DIR" "$PBR_LAMEM_PETSC_DIR" "$PBR_BUILD_ROOT"'
        env = {**os.environ, "NP": "4", "PBR_MOOSE_PETSC_DIR": "/env/moose", "PBR_OUTPUT_ROOT": "/output with spaces"}
        for key in ("PBR_ROOT", "PBR_SITE", "PBR_BUILD_ROOT"):
            env.pop(key, None)
        result = subprocess.run([bash, "--noprofile", "--norc", "-c", script, "--",
                                 str(PACKAGE / "scripts/lib/common.sh"), str(root)], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "5|/env/moose|/local/lamem|/output with spaces/builds")

    def test_vendor_hook_arguments_and_loader_path_isolation(self):
        root = self.folder()
        hook = root / "vendor.sh"
        hook.write_text('[[ $# == 0 ]] || exit 71\nexport LD_LIBRARY_PATH=/vendor/lib\n')
        bash = os.environ.get("PBR_TEST_BASH", "bash")
        script = ('source "$1"; PBR_HOST=aspect; PBR_JOB=$2; THREADS=1; '
                  'PBR_ASPECT_ENV_MODE=hook; PBR_ASPECT_ENV_SCRIPT=$3; '
                  'PBR_ASPECT_LD_LIBRARY_PATH=/host/lib; '
                  'LD_LIBRARY_PATH=/inherited/conda; activate_env; '
                  'printf "%s" "$LD_LIBRARY_PATH"')
        result = subprocess.run([bash, "--noprofile", "--norc", "-c", script, "--",
                                 str(PACKAGE / "scripts/lib/common.sh"), str(root), str(hook)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "/host/lib")

    def prepare(self, host, **values):
        path = self.folder()
        env = dict(PROFILE="historical", POLICY="online", K="1", CASE="blankenbach", NSTEPS="", CFG="fx")
        env.update(values)
        with patch.dict(os.environ, env):
            runtime.prepare(argparse.Namespace(host=host, package=str(PACKAGE), directory=str(path)))
        return path

    def test_elmer_actual_switch_and_startinfo(self):
        for policy in ("online", "off", "fixed"):
            job = self.prepare("elmer", POLICY=policy)
            text = (job / "case/stabilized.sif").read_text()
            self.assertEqual(text.count("Linear System Precondition Online"), 1)
            self.assertIn("Online = Logical " + ("True" if policy == "online" else "False"), text)
            self.assertEqual((job / "case/ELMERSOLVER_STARTINFO").read_text().strip(), "stabilized.sif")
        with self.assertRaises(ValueError):
            self.prepare("elmer", POLICY="fixed", K="3")

    def test_named_windows(self):
        for profile, endpoint in (("historical", "0.1"), ("c1b", "0.03")):
            job = self.prepare("aspect", PROFILE=profile)
            text = (job / "case/case.prm").read_text()
            self.assertEqual(text.count("set End time"), 1)
            self.assertIn("set End time = " + endpoint, text)
        job = self.prepare("lamem", PROFILE="c1b")
        text = (job / "case/case.dat").read_text()
        self.assertRegex(text, r"nstep_max\s*=\s*120")
        self.assertRegex(text, r"nstep_out\s*=\s*100000")

    def test_original_inputs_and_expected_unchanged(self):
        before = {p: p.read_bytes() for p in (PACKAGE / "expected").iterdir() if p.is_file()}
        source = PACKAGE / "cases/elmer/fssa_perlin2d/stabilized.sif"
        original = source.read_bytes()
        self.prepare("elmer", POLICY="off")
        self.assertEqual(source.read_bytes(), original)
        self.assertTrue(all(p.read_bytes() == content for p, content in before.items()))

    def test_final_input_manifest_and_protected_paths(self):
        job = self.prepare("elmer", POLICY="off")
        generated = job / "case/mesh2D/partitioning.8"
        generated.mkdir()
        (generated / "part.1.header").write_text("fixture partition\n")
        runtime.effective_inputs(job)
        recorded = json.loads((job / "inputs.json").read_text())
        self.assertIn(str(Path("mesh2D/partitioning.8/part.1.header")), recorded["final_changed"])
        with self.assertRaisesRegex(ValueError, "protected"):
            runtime.check_paths(PACKAGE, [PACKAGE / "expected/new-run"])
        runtime.check_paths(PACKAGE, [job])

    def test_stop_marker_blocks_descendant_and_next_command(self):
        parent, child = self.folder(), None
        child = parent / "worker/r2"; child.mkdir(parents=True)
        (parent / "status.json").write_text('{"finished":false}')
        runtime.manage(argparse.Namespace(directory=str(parent), job_action="stop", grace=0.1))
        self.assertTrue(runtime.stop_requested(child))
        args = argparse.Namespace(directory=str(child), name="solve", timeout=5, grace=0.1,
                                  command=[sys.executable, "-c", "raise RuntimeError('must not run')"])
        self.assertEqual(runtime.execute(args), 143)
        self.assertFalse((child / "solve.log").exists())

    def make_trace_job(self, np=1):
        job = self.folder(); (job / "case").mkdir()
        (job / "solve.log").write_text("Time Step 404, time = 100\nFinished Executing\n")
        (job / "execution-solve.json").write_text('{"returncode":0,"timed_out":false}')
        for rank in range(np):
            name = "pbr.csv" + (f".r{rank}" if np > 1 else "")
            (job / "case" / name).write_text("step,rebuild,its,build_ms,solve_ms\n0,1,2,1.0,2.0\n")
        return job

    def test_rank_suffix_missing_trace_is_failure(self):
        job = self.make_trace_job(1)
        with patch.dict(os.environ, dict(NP="2", PROFILE="c1b", POLICY="online", PBR_ALIGN="on")):
            rc = runtime.summarize(argparse.Namespace(host="moose", package=str(PACKAGE), directory=str(job)))
        self.assertNotEqual(rc, 0)

    def test_identical_off_timings_are_diagnostic_not_failure(self):
        job = self.make_trace_job(2)
        with patch.dict(os.environ, dict(NP="2", PROFILE="c1b", POLICY="online", PBR_ALIGN="off")):
            rc = runtime.summarize(argparse.Namespace(host="moose", package=str(PACKAGE), directory=str(job)))
        self.assertEqual(rc, 0)
        result = json.loads((job / "result.json").read_text())
        self.assertTrue(result["timing_columns_identical"])

    def test_headerless_openfoam_counts_and_serial_baseline(self):
        job = self.folder(); (job / "case/system").mkdir(parents=True)
        (job / "case/system/controlDict").write_text("endTime 344;\n")
        (job / "solve.log").write_text("".join(f"Time = {i}\n" for i in range(1,345)) + "Solving for p_rgh, No Iterations 7957\nEnd\n")
        (job / "execution-solve.json").write_text('{"returncode":0,"timed_out":false}')
        row = ["0"] * 25; row[24] = "1031"
        (job / "case/pbr_pc.csv").write_text(",".join(row)+"\n")
        env = dict(NP="1", PROFILE="historical", POLICY="online", PBR_MODE="K1", CHECK_EXPECTED="1", CFG="fx")
        with patch.dict(os.environ, env):
            self.assertEqual(runtime.summarize(argparse.Namespace(host="openfoam", package=str(PACKAGE), directory=str(job))), 0)
        result = json.loads((job / "result.json").read_text())
        self.assertEqual(result["traces"][0]["data_rows"], 1)
        self.assertEqual(result["traces"][0]["total_builds"], 1031)
        with patch.dict(os.environ, {**env, "NP": "4"}):
            with self.assertRaisesRegex(ValueError, "serial"):
                runtime.summarize(argparse.Namespace(host="openfoam", package=str(PACKAGE), directory=str(job)))

    @unittest.skipUnless(sys.platform == "linux", "Linux process sessions required")
    def test_process_failure_and_timeout_rc(self):
        for code, timeout, expected in [("raise SystemExit(83)", 5, 83), ("import time;time.sleep(10)", 0.2, 124)]:
            job = self.folder()
            args = argparse.Namespace(directory=str(job), name="solve", timeout=timeout, grace=0.1, command=[sys.executable, "-c", code])
            self.assertEqual(runtime.execute(args), expected)
            record = json.loads((job / "execution-solve.json").read_text())
            self.assertEqual(record["returncode"], expected)


if __name__ == "__main__":
    print("Retained test fixtures:", FIXTURES)
    unittest.main()
