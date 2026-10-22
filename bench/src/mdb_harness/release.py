"""Import public JSON assignments without evaluating JavaScript."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

import requests
from pymatgen.core import Structure

from .novelty import StructureRegistry

BASE = "https://petmad.matforge.ai/bench/"
SOURCES = {
    "candidates.js": BASE + "data/candidates.js",
    "details.js": BASE + "data/details.js",
    "synthesis_grades.js": BASE + "data/synthesis_grades.js",
    "launched.js": BASE + "data/launched.js",
    "research.html": "https://discoveredmaterials.com/research/",
    "about.html": BASE + "about.html",
}


def assignment(text: str, name: str):
    match = re.search(r"window\." + re.escape(name) + r"\s*=\s*", text)
    if not match:
        raise ValueError(f"Missing assignment: {name}")
    value, end = json.JSONDecoder().raw_decode(text[match.end():])
    if not text[match.end() + end:].lstrip().startswith(";"):
        raise ValueError(f"Unexpected executable suffix after {name}")
    return value


def fetch_release(destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    if (destination / "manifest.json").exists():
        return verify_snapshot(destination)
    manifest = {"retrieved_at": datetime.now(timezone.utc).isoformat(), "files": {},
                "license": "No release license verified; local research cache, not vendored source",
                "official_repository": "https://github.com/advaith-dm/materials-autoresearch",
                "repository_status": "Public URL returned 404 on 2026-10-22"}
    for filename, url in SOURCES.items():
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        data = response.content
        (destination / filename).write_bytes(data)
        manifest["files"][filename] = {"url": url, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def verify_snapshot(path: Path):
    manifest = json.loads((path / "manifest.json").read_text())
    for name, metadata in manifest["files"].items():
        digest = hashlib.sha256((path / name).read_bytes()).hexdigest()
        if digest != metadata["sha256"]:
            raise ValueError(f"Snapshot checksum mismatch: {name}")
    return manifest


def hypervolume(points: list[tuple[float, float]]) -> float:
    """Union of rectangles from origin; no undocumented clipping to [0,1]."""
    if any(not math.isfinite(x) or not math.isfinite(y) or x < 0 or y < 0 for x, y in points):
        raise ValueError("Hypervolume requires finite nonnegative coordinates")
    area = height = 0.0
    previous_x = None
    for x, y in sorted(points, reverse=True):
        if previous_x is not None:
            area += (previous_x - x) * height
        height = max(height, y)
        previous_x = x
    return area + (previous_x or 0) * height


def load_release(path: Path):
    verify_snapshot(path)
    source = (path / "candidates.js").read_text()
    return {
        "candidates": assignment(source, "MDB_CANDIDATES"),
        "runs": assignment(source, "MDB_RUNS"),
        "models": assignment(source, "MDB_MODELS"),
        "details": assignment((path / "details.js").read_text(), "MDB_DETAILS"),
        "grades": assignment((path / "synthesis_grades.js").read_text(), "MDB_SYNTH_GRADES"),
        "launched": assignment((path / "launched.js").read_text(), "MDB_LAUNCHED"),
    }


def release_structure(record: dict) -> Structure:
    return Structure(record["lattice"], [x["el"] for x in record["sites"]], [x["f"] for x in record["sites"]])


def audit_release(path: Path, deduplicate: bool = True):
    release = load_release(path)
    candidates, details, grades = release["candidates"], release["details"], release["grades"]
    registry = StructureRegistry()
    duplicate_of, invalid = {}, {}
    per_model = defaultdict(list)
    for candidate in candidates:
        cid = candidate["id"]
        per_model[candidate["model"]].append(candidate)
        if deduplicate:
            try:
                structure = release_structure(details[cid]["structure"])
                prior = registry.register(cid, structure)
                if prior:
                    duplicate_of[cid] = prior
            except (ValueError, KeyError, TypeError) as exc:
                invalid[cid] = str(exc)
    models = []
    for model, rows in per_model.items():
        run_points = defaultdict(list)
        for row in rows:
            kappa, epsilon = row.get("kappa"), row.get("epsInf")
            if isinstance(kappa, (int, float)) and isinstance(epsilon, (int, float)) and kappa > 0 and epsilon > 0:
                run_points[row["run"]].append((kappa / 2200, 2.4 / epsilon))
        models.append({"model": model, "released_rows": len(rows), "formula_strings": len({r['formula'] for r in rows}),
                       "represented_runs": len({r['run'] for r in rows}),
                       "launched_runs_metadata": release["launched"].get(model),
                       "verdict_counts": dict(Counter(grades['byCandidate'].get(r['id'], 'missing') for r in rows)),
                       "legacy_field_hypervolume_by_represented_run": {k: hypervolume(v) for k, v in run_points.items()}})
    ids = {c['id'] for c in candidates}
    seen_in_run, repeats_in_run = set(), []
    if deduplicate:
        for row in candidates:
            if row['id'] in invalid:
                continue
            key = (row['model'], row['run'], duplicate_of.get(row['id'], row['id']))
            if key in seen_in_run:
                repeats_in_run.append(row['id'])
            seen_in_run.add(key)
    return {
        "kind": "public_release_audit_not_new_discovery", "official_comparable": False,
        "rows": len(candidates), "formula_strings": len({c['formula'] for c in candidates}),
        "provenance_counts": dict(Counter(c.get('provenance') for c in candidates)),
        "verdict_counts": dict(Counter(grades['byCandidate'].get(c['id'], 'missing') for c in candidates)),
        "grade_ids_without_candidate": sorted(set(grades['byCandidate']) - ids),
        "deduplication_performed": deduplicate, "duplicate_of": duplicate_of, "invalid_structures": invalid,
        "structural_groups": len(candidates) - len(duplicate_of) - len(invalid) if deduplicate else None,
        "equivalent_repeats_within_represented_runs": repeats_in_run if deduplicate else None,
        "publisher_known_overrides": grades.get('knownOverrides', []),
        "models": models,
        "limitations": [
            "Public release is a selected set, not all attempts; no hit-rate denominator or submission order is available here.",
            "epsInf field naming conflicts with current static-epsilon methods. Preserve the field; do not reinterpret it.",
            "Legacy hypervolume is a diagnostic over the exported field, not an official or current score.",
            "MLIP-verified is not DFT or experimental validation.",
            "Structure equivalence is tolerance-dependent; formula strings are not unique-material counts.",
            "Published candidates are development data and must not be submitted as new discoveries.",
        ],
    }
