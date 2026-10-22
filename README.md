# Lattice — Materials Discovery Studio

A local research dashboard for proposing crystalline materials, testing their physics, checking known structures, and critiquing the next hypothesis.

**Research software, not a discovery certificate.** Synthesis generation is currently paused. Predicted properties, unresolved evidence and failed checks remain visible. This is an independent implementation, not the official Discovered Materials benchmark or an implementation of Google DeepMind’s AlphaEvolve.

## What it does

- Displays periodic structures, relaxation progress, properties, failed checks and source evidence in a live dashboard.
- Proposes hypotheses through a bounded population loop with parent lineage, mutation rationale, tradeoffs and a separate critic. Model opinions cannot overwrite evaluator-owned physics.
- Runs PET-MAD relaxation, Phonopy vibrations and finite-strain elasticity; optionally estimates thermal conductivity with phono3py.
- Imports versioned JARVIS/OQMD snapshots for indexed composition and structure matching. The tested snapshots contain 907,259 reference records, not globally distinct experimental materials.
- Searches a shared SQLite FTS5/BM25 literature memory. Abstracts, full text and prior computational notes retain separate provenance. Exact citation checks establish traceability, not scientific entailment.
- Connects to Materials Project with an optional API key. No match in a bounded search is treated as proof of world novelty.

## Quick start

Use Python 3.12. From the repository root:

```bash
python3.12 -m venv .bench-venv
.bench-venv/bin/python -m pip install -e './bench[simulation,thermal,openai,test]'
cd bench
../.bench-venv/bin/mdb-studio --port 8768
```

Open **http://127.0.0.1:8768/**. The **API key** button configures the model provider and optional Materials Project access. Keys are session-only by default; choosing local persistence writes the ignored `.env` file. The server binds to loopback.

**Run silicon control** exercises the real simulator without a model API key. **Start discovery** makes provider requests within the configured call/token budget. The first simulator run may download model weights. Configure the objective, elements, model and budgets in [`bench/discovery.json`](bench/discovery.json). Synthesis remains disabled unless explicitly enabled in that configuration.

## Import the reference libraries

Selected [published run reports](reports/README.md) include the Astra campaign, earlier discovery runs, structures, numerical results and validation. Full working run directories, downloaded archives and databases are not included. From `bench/`:

```bash
../.bench-venv/bin/python scripts/import_open_data.py --kind materials --download
../.bench-venv/bin/python scripts/import_open_data.py --kind literature --download
```

The importer verifies publisher checksums and stores snapshot provenance. Allow roughly 1 GB of disk space for these archives and indexes, plus environments and model weights. Dataset versions, licenses and source URLs are in [`bench/open-snapshots.json`](bench/open-snapshots.json).

## Test

```bash
# From bench/
../.bench-venv/bin/python -m pytest -q

# After importing material data; optional real simulator controls
../.bench-venv/bin/mdb validate --output runs/validation --simulate --cases 12
```

Current local verification: **67 unit/integration tests**, **72/72 known-reference recognition checks**, and real silicon/diamond simulator controls. These are software and execution checks, not an accuracy calibration, blind discovery benchmark or SOTA result. Browser checks that require local historical runs are separate from the unit suite.

A [GitHub Actions template](docs/CI.md) is included; hosted CI is not enabled yet.

## Scientific limits

Static dielectric prediction/DFPT, a complete consistent-energy competing-phase hull, a second potential cross-check and experimental validation are not yet integrated. Small imaginary phonon modes remain unresolved; severe instability blocks downstream screening. Formal oxidation-state counting checks a proposed rationale, without treating every nonzero nominal charge as proof a covalent material cannot exist. Imported DFT energies are never mixed into a PET-MAD hull.

The search cannot currently certify a useful new material or a feasible synthesis route. Missing calculations and unsupported claims stay explicit.

## Project layout

- [`bench/DISCOVERY.md`](bench/DISCOVERY.md): pipeline, configuration, memory, critic, physics and limitations.
- [`bench/src/mdb_harness`](bench/src/mdb_harness): current implementation and dashboard.
- [`bench/tests`](bench/tests): deterministic and scripted integration tests.
- [`bench/README.md`](bench/README.md): independent public benchmark audit and comparison tools.
- [`ALLOY_PROTOTYPE.md`](ALLOY_PROTOTYPE.md): earlier Al–Sc/Kawin/pycalphad prototype in the root Python package; separate from the current studio.
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md): bundled third-party data attribution and downloaded-resource provenance.
