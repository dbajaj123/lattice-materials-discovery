"""Isolated, bounded simulator jobs with content-addressed artifacts."""
from __future__ import annotations
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .schema import Candidate, SimulationSettings


def source_fingerprint():
    root = Path(__file__).parent
    digest = hashlib.sha256()
    # UI/search changes do not invalidate expensive physical evaluations.
    sources = [root/name for name in ("schema.py", "simulator.py", "grading.py", "runner.py", "cli.py")]
    sources += [root/"data"/name for name in ("AlScZr.tdb", "database-provenance.json")]
    for p in sources:
        digest.update(p.name.encode())
        digest.update(p.read_bytes())
    for name in ("kawin", "pycalphad", "numpy", "scipy"):
        digest.update(f"{name}={importlib.metadata.version(name)}".encode())
    return digest.hexdigest()


def run_id(candidate, settings):
    physical = {k: v for k,v in candidate.model_dump().items() if k not in ("name", "hypothesis", "evidence_ids")}
    payload = {"candidate": physical, "settings": settings.model_dump(), "source": source_fingerprint()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]


def run_candidate(candidate: Candidate, root: Path, settings=None, timeout_s=180, retry_failed=False):
    settings = settings or SimulationSettings()
    identity = run_id(candidate, settings)
    evaluator_fingerprint = source_fingerprint()
    folder = Path(root)/"evaluations"/identity
    folder.mkdir(parents=True, exist_ok=True)
    output = folder/"result.json"
    if output.exists():
        result = json.loads(output.read_text())
        if result.get("status") != "failed" or not retry_failed:
            result["cache_hit"] = True
            result["candidate"] = candidate.model_dump()
            return result
        # Retain the failed attempt when explicitly retrying a cached job.
        attempt = 1
        while (folder/f"failed-attempt-{attempt}.json").exists():
            attempt += 1
        output.replace(folder/f"failed-attempt-{attempt}.json")
    request = folder/"request.json"
    request.write_text(json.dumps({"candidate": candidate.model_dump(), "settings": settings.model_dump()}, indent=2))
    snapshot = folder/"source"
    shutil.copytree(Path(__file__).parent, snapshot/"alloy_discovery", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    command = [sys.executable, "-u", "-m", "alloy_discovery.cli", "_worker", str(request.resolve()), str(output.resolve())]
    env = dict(os.environ, MPLCONFIGDIR="/tmp/materials-discovery-mpl", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    env["PYTHONPATH"] = str(snapshot.resolve())
    with (folder/"worker.log").open("w") as log:
        try:
            process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=env, timeout=timeout_s)
            if process.returncode != 0:
                raise RuntimeError(f"Simulator exited {process.returncode}; inspect {folder/'worker.log'}")
        except (subprocess.TimeoutExpired, RuntimeError) as error:
            result = {"status": "failed", "candidate": candidate.model_dump(), "error": str(error),
                      "discovery_status": "not_eligible", "metrics": None, "trace": None,
                      "numerical": {"status": "indeterminate"}, "evidence": {}, "steps": []}
            progress_path = folder/"progress.json"
            if progress_path.exists():
                progress = json.loads(progress_path.read_text())
                result.update(steps=progress["completed_steps"], evidence=progress["evidence"],
                              provenance=progress["provenance"], equilibrium=progress["equilibrium"],
                              partial_progress=True)
            output.write_text(json.dumps(result, indent=2))
    result = json.loads(output.read_text())
    result.update(run_id=identity, source_fingerprint=evaluator_fingerprint, source_snapshot=str(snapshot.resolve()),
                  artifact_dir=str(folder.resolve()), cache_hit=False)
    output.write_text(json.dumps(result, indent=2, allow_nan=False))
    return result


def sensitivity(candidate, root, timeout_s=180):
    """Designed perturbations, NOT posterior samples or calibrated intervals."""
    scenarios = [
        ("nominal", SimulationSettings()),
        ("lower_interface_energy", SimulationSettings(gamma_j_m2=0.08)),
        ("higher_interface_energy", SimulationSettings(gamma_j_m2=0.12)),
        ("slower_diffusion", SimulationSettings(diffusivity_multiplier=0.5)),
        ("faster_diffusion", SimulationSettings(diffusivity_multiplier=2)),
        ("finer_discretization", SimulationSettings(bins=300, max_dt_fraction=0.01)),
    ]
    rows = []
    for label, settings in scenarios:
        result = run_candidate(candidate, root, settings, timeout_s)
        rows.append({"scenario": label, "run_id": result.get("run_id"), "status": result["status"],
                     "metrics": result.get("metrics"), "settings": settings.model_dump()})
    valid = [r["metrics"]["final_strength_increment_mpa"] for r in rows if r["status"] == "completed"]
    report = {"candidate": candidate.model_dump(), "scenarios": rows, "interval_kind": "designed_sensitivity_range",
              "calibrated": False, "coverage": None,
              "strength_range_mpa": [min(valid), max(valid)] if valid else None,
              "complete": len(valid) == len(rows),
              "limitation": "One-at-a-time parameter perturbations omit parameter correlations and model discrepancy. No probability of experimental success is estimated."}
    if rows[0]["status"] == rows[-1]["status"] == "completed":
        a, b = rows[0]["metrics"], rows[-1]["metrics"]
        errors = {key: abs(a[key]-b[key])/max(abs(b[key]), 1e-12) for key in ["final_strength_increment_mpa", "final_radius_nm", "final_volume_fraction"]}
        report["discretization"] = {"relative_changes": errors, "tolerance": 0.05,
                                     "status": "pass" if max(errors.values()) < 0.05 else "fail",
                                     "limitation": "Two-resolution comparison; not a proof of asymptotic convergence."}
    else:
        report["discretization"] = {"status": "indeterminate"}
    return report
