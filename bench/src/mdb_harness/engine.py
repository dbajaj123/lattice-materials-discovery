from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from .novelty import StructureRegistry
from .schema import Gate, PhysicsResult, Proposal, physics_gates, synthesis_checks


def dump(path: Path, value):
    from .live_events import atomic_json
    atomic_json(path,value)


class Engine:
    """Bounded operator-owned evaluator; the agent cannot supply grading results."""

    def __init__(self, root: Path, *, max_screen_calls=8, timeout=240, backend="none", elastic=False, thermal=False):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_screen_calls = max_screen_calls
        self.timeout = timeout
        self.backend = backend
        self.elastic = elastic
        self.thermal = thermal
        self.registry = StructureRegistry()
        self.screen_calls = 0
        self.submitted = set()
        self.events = []
        self.notes = []
        self.proposals = {}
        self.results = {}
        self.recipe_revisions = {}
        self.source_hash = hashlib.sha256(b"".join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py')))).hexdigest()
        if (self.root / "manifest.json").exists():
            raise ValueError("Run directory exists; choose a fresh directory to preserve the audit trail")
        self.source_dir = self.root / 'source'
        package = self.source_dir / 'mdb_harness'
        package.mkdir(parents=True)
        for source in sorted(Path(__file__).parent.glob('*.py')):
            shutil.copy2(source, package / source.name)
        dump(self.root / "manifest.json", {
            "created_at": datetime.now(timezone.utc).isoformat(), "source_sha256": self.source_hash,
            "backend": backend, "max_screen_calls": max_screen_calls, "timeout_seconds": timeout,
            "elastic": elastic, "thermal": thermal, "official_comparable": False,
            "protocol": "current-public-methods-local-reconstruction",
            "packages": {p: importlib.metadata.version(p) for p in ['pymatgen', 'ase', 'phonopy', 'inspect-ai']},
        })

    def record(self, action: str, data: dict):
        row = {"sequence": len(self.events), "time": datetime.now(timezone.utc).isoformat(), "action": action, **data}
        self.events.append(row)
        with (self.root / "events.jsonl").open("a") as handle:
            handle.write(json.dumps(row, allow_nan=False) + "\n")

    def screen(self, payload: dict):
        if self.screen_calls >= self.max_screen_calls:
            return {"error": "Screening budget exhausted", "screen_calls": self.screen_calls}
        self.screen_calls += 1  # Invalid proposals and repeated calls consume budget.
        try:
            proposal = Proposal.model_validate(payload)
        except Exception as exc:
            response = {"error": str(exc), "screen_calls": self.screen_calls}
            self.record("invalid_proposal", response)
            return response
        cid = hashlib.sha256(json.dumps(proposal.model_dump(), sort_keys=True).encode()).hexdigest()[:16]
        duplicate = self.registry.register(cid, proposal.crystal.structure())
        self.proposals[cid] = proposal
        workdir = self.root / "candidates" / cid
        dump(workdir / "proposal.json", proposal.model_dump())
        if duplicate:
            response = {"candidate_id": cid, "duplicate_of": duplicate, "eligible": False,
                        "reason": "Equivalent structure already screened; no additional candidate credit"}
            self.record("duplicate", response)
            return response
        start = time.monotonic()
        if self.backend == "petmad":
            command = [sys.executable, "-m", "mdb_harness.cli", "_physics", str(workdir / "proposal.json"), str(workdir)]
            if self.elastic:
                command.append("--elastic")
            if self.thermal:
                command.append("--thermal")
            try:
                with (workdir / "worker.log").open("w") as log:
                    environment = dict(os.environ)
                    environment['PYTHONPATH'] = str(self.source_dir)
                    completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=self.timeout, env=environment)
                if completed.returncode:
                    raise RuntimeError(f"Simulation worker exited {completed.returncode}; see worker.log")
                result = PhysicsResult.model_validate_json((workdir / "physics.json").read_text())
                if result.input_digest != proposal.crystal.digest():
                    raise ValueError("Simulator output belongs to a different input structure")
            except (subprocess.TimeoutExpired, RuntimeError, ValueError, OSError) as exc:
                result = PhysicsResult(status="failed", backend="petmad", input_digest=proposal.crystal.digest(), warnings=[str(exc)])
                partial=workdir/'physics-partial.json'
                if partial.exists():
                    checkpoint=PhysicsResult.model_validate_json(partial.read_text())
                    if checkpoint.input_digest==proposal.crystal.digest():
                        checkpoint.warnings.append('Worker stopped after partial physics: '+str(exc))
                        result=checkpoint
        else:
            result = PhysicsResult(status="partial", backend="unconfigured", input_digest=proposal.crystal.digest(),
                                   warnings=["No simulation backend configured; all scientific properties remain unknown"])
        gates = physics_gates(result)
        if self.backend == "none":
            gates[0] = Gate(name="relaxation", status="unknown", reason="No simulator configured")
        relaxed_duplicate = None
        if result.relaxed is not None:
            # Input registry does not replace a separate relaxed-structure registry.
            for prior_id, previous in self.results.items():
                previous_crystal = previous.get("physics", {}).get("relaxed")
                if previous_crystal:
                    from .schema import Crystal
                    if self.registry.matcher.fit(result.relaxed.structure(), Crystal.model_validate(previous_crystal).structure()):
                        relaxed_duplicate = prior_id
                        break
        gates.extend([
            Gate(name="literature_novelty", status="unknown", reason="No independent dated literature novelty review"),
            Gate(name="synthesis_plausibility", status="unknown", reason="Official expert-calibrated rubric and reviewer unavailable"),
        ])
        response = {"candidate_id": cid, "screen_calls": self.screen_calls,
                    "elapsed_seconds": time.monotonic() - start, "physics": result.model_dump(),
                    "gates": [g.model_dump() for g in gates], "synthesis_steps": synthesis_checks(proposal),
                    "relaxed_duplicate_of": relaxed_duplicate,
                    "eligible": all(g.status == "pass" for g in gates) and relaxed_duplicate is None,
                    "official_comparable": False}
        self.results[cid] = response
        dump(workdir / "evaluation.json", response)
        self.record("screen", {"candidate_id": cid, "elapsed_seconds": response['elapsed_seconds'], "eligible": response['eligible']})
        return response

    def revise_synthesis(self, candidate_id: str, steps: list[dict], closest_prior_art: list[str]):
        if candidate_id not in self.results:
            return {'error':'Candidate has no existing evaluation'}
        revision = self.recipe_revisions.get(candidate_id, 0) + 1
        if revision > 3:
            return {'error':'Recipe revision budget exhausted for this structure'}
        payload = self.proposals[candidate_id].model_dump()
        payload.update(synthesis=steps, closest_prior_art=closest_prior_art)
        try:
            proposal = Proposal.model_validate(payload)
        except ValueError as exc:
            return {'error':str(exc)}
        self.recipe_revisions[candidate_id] = revision
        self.proposals[candidate_id] = proposal
        result = self.results[candidate_id]
        result['synthesis_steps'] = synthesis_checks(proposal)
        result['recipe_revision'] = revision
        result['eligible'] = False  # A changed recipe always needs an independent review.
        for gate in result['gates']:
            if gate['name'] == 'synthesis_plausibility':
                gate.update(status='unknown', reason='Revised recipe requires independent review')
        dump(self.root / 'candidates' / candidate_id / f'recipe-revision-{revision}.json', proposal.model_dump())
        dump(self.root / 'candidates' / candidate_id / 'evaluation.json', result)
        self.record('revise_synthesis', {'candidate_id':candidate_id,'revision':revision})
        return {'candidate_id':candidate_id, 'revision':revision, 'synthesis_steps':result['synthesis_steps'],
                'eligible':False, 'additional_material_credit':False}

    def submit(self, candidate_id: str):
        if candidate_id not in self.results:
            return {"error": "Candidate has no independent evaluation"}
        repeated = candidate_id in self.submitted
        self.submitted.add(candidate_id)
        result = {"candidate_id": candidate_id, "recorded": not repeated,
                  "eligible": self.results[candidate_id]['eligible'], "official_comparable": False}
        self.record("submit", result)
        dump(self.root / "summary.json", self.state())
        return result

    def remember(self, hypothesis: str, evidence: str, next_test: str):
        note = {"hypothesis": hypothesis, "evidence": evidence, "next_test": next_test}
        self.notes.append(note)
        dump(self.root / "notebook.json", self.notes)
        self.record("notebook", note)
        return {"saved": len(self.notes)}

    def state(self):
        return {"screen_calls": self.screen_calls, "max_screen_calls": self.max_screen_calls,
                "submitted": sorted(self.submitted), "eligible_count": sum(self.results[c]['eligible'] for c in self.submitted),
                "notes": self.notes[-12:], "official_comparable": False,
                "candidates": [{"id": cid, "name": self.proposals[cid].name, "gates": r['gates']} for cid, r in self.results.items()]}
