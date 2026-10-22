# Our materials discovery pipeline

This document includes the original local installation’s verification results. Downloaded data, credentials and `runs/` artifacts are excluded from the public repository; the root README explains how to build a fresh installation.

This is an independent, executable research pipeline. Its first search space is **crystalline dielectrics for chip integration**, using B, C, N, Si, Al and O. The configuration can change the elements, objective, literature, seeds and search budget. Property backends must be validated for a new class before their scores are used there.

The current output is a candidate dossier: crystal structure, evaluator-computed properties, composition audit, closest known structures, cited literature, critic findings, parent lineage and the next discriminating test. **Synthesis generation is paused** (`synthesis_enabled: false`). Historical routes remain available as archived proposals. A dossier is not a discovery certificate.

## What Discovered Materials does, and what we replicate

Their [published research description](https://discoveredmaterials.com/research/) combines an agent with structure/property tools, a research notebook and synthesis assessment. Candidate structures are screened with an interatomic potential; separate calculations estimate properties; synthesis recipes receive a rubric-based review. Their description is enough to reproduce the broad research loop independently.

On 2026-10-23 local time, the linked repository, `advaith-dm/materials-autoresearch`, returned HTTP 404 through the GitHub API. An exact GitHub repository search returned zero results. No public official source was obtained. The public benchmark data is available separately and has already been imported for audit. It is **not injected into our discovery prompts**. We are not waiting for the official grader to operate our pipeline, and we cannot claim an exact port or a leaderboard comparison.

| Stage | Our implementation | What its result establishes |
|---|---|---|
| Literature | Shared condensed-matter abstract archive, live arXiv, Crossref, Europe PMC and local documents; SQLite FTS5/BM25 | The retrieved text and its source, not exhaustive coverage |
| Proposals | Population archive, Pareto/diversity selection, explicit parent IDs, mutation rationale, tradeoffs and physics critic | A chemically motivated hypothesis, not a calculated property |
| Structures | ASE and pymatgen; explicit CIF output and structure matching | A concrete periodic structure and detected duplicates |
| Physics | PET-MAD relaxation, Phonopy vibrations, finite-strain elasticity; optional phono3py transport | Model predictions with recorded settings and limitations |
| Prior structures | 907,259 local JARVIS/OQMD records, indexed composition lookup and structure matching; cached online APIs | Matches to retrieved structures; failed/bounded searches remain unresolved |
| Routes (paused) | Optional route generation, blocked by failed or unresolved relaxation/dynamic-stability checks | Proposed alternatives with explicit missing evidence |
| Review | Fresh model call, exact citation checks, six route criteria, intermediate-step assessments, deterministic temperature checks | An uncalibrated assessment requiring expert review |
| Feedback and display | Persisted candidate dossiers, next-experiment feedback, offline Plotly report | An inspectable and resumable research record |

The default reviewer uses a fresh call to the proposer model. It is correlated with the proposer, not an independent experimental judge. `review_model` can select a different configured model, but that alone does not calibrate certainty.

## Start once the model key is available

### Live discovery studio

The live dashboard is at **http://127.0.0.1:8768/**. To restart it from `bench/`:

```bash
../.bench-venv/bin/mdb-studio --port 8768
```

Use **Run silicon control** to watch a real PET-MAD calculation without a model key. **Start discovery** launches a fresh campaign using the configured key. **Run settings** controls rounds, candidate and route counts, token limit, simulation timeout and optional thermal transport. **Stop** terminates the campaign process group and retains completed artifacts; it does not undo API calls already sent. The campaign selector opens previous runs.

The dashboard streams persisted progress through server-sent events. Its crystal viewer updates during relaxation, supports cell repetition, rotation, geometric proximity guides and CIF export. Synthesis routes appear as connected intermediate-phase cards; selecting a step opens its conditions, competing phases, characterization, citation excerpts and review. Missing support remains visible. The silicon control has no agent-generated synthesis routes. Route renderer tests use explicitly labeled synthetic UI fixtures, never stored as discovery results.

Use the **API key** button to configure the model provider or the optional Materials Project key. The masked field is cleared after submission or closing the panel. By default, the key stays in the dashboard server's environment until it restarts. **Remember on this machine** saves it to `bench/.env` with owner-only permissions (0600); the file is not encrypted. Existing `.env` settings are preserved. A session-only override leaves any previously saved key unchanged. New runs use updated credentials; an already running process keeps its original environment. Saving a key does not test provider access or make any model request.

The server binds only to loopback, protects mutations with a per-session token and origin/host checks, and starts bounded subprocesses without exposing a shell to the browser. It is a local research interface, not an Internet deployment. Stored keys are never returned to the browser, included in run records, or saved in browser local/session storage. The dashboard returns only credential-presence indicators. Editing `bench/.env` directly remains supported.

Live run artifacts are in `runs/live/<run-id>/`. Existing prepared campaigns keep their frozen source; new dashboard launches use a fresh directory and the current code. Browser integration validation is recorded in `runs/studio-validation.json`, including a real thermal-control run, stop behavior, CIF download, route-step interactions and mobile layout.

### Command line

The Python 3.12 environment is already installed at `../.bench-venv`. On a new machine, create that environment and install with `../.bench-venv/bin/python -m pip install -e '.[simulation,thermal,openai,test]'`. From this directory:

```bash
cp .env.example .env
# Edit .env locally and set OPENAI_API_KEY.
../.bench-venv/bin/mdb discover run --config discovery.json --output runs/discovery-new
```

The configured model is `openai/gpt-5.4`; override `DISCOVERY_MODEL` in `.env` to change it. Other Inspect providers need their corresponding credentials and provider dependencies. An optional `DISCOVERY_REVIEW_MODEL` selects the reviewer. `MP_API_KEY` enables Materials Project, but it is not needed for the free literature and JARVIS/OQMD paths. Keys are read from the environment; they are not written into campaign configuration or model-call logs. Evidence excerpts are sent to the selected model provider when the campaign runs.

The prepared campaign at `runs/discovery` retains its earlier source snapshot. Use the live dashboard or a new output directory for the current code. If changing the configuration or Python source, use a **new output directory**; a campaign preserves its original configuration and source hash. It also freezes a copy of the package in its `source/` directory. Dependency versions are recorded in `requirements-lock.txt`; restoring a source snapshot alone does not restore the Python environment.

Prepare evidence without a model call, inspect status, or regenerate the report:

```bash
../.bench-venv/bin/mdb discover prepare --config discovery.json --output runs/discovery
../.bench-venv/bin/mdb discover status --output runs/discovery
../.bench-venv/bin/mdb discover report --output runs/discovery
```

Open `runs/discovery/report.html` directly, or use the running local server at `http://127.0.0.1:8767/discovery/report.html`. The report shows saved data; opening it does not launch computations or spend tokens.

The initial budget is two rounds of up to two candidates, at most 24 model attempts and 120,000 total tokens. With synthesis paused, the model proposes candidates and critiques the computed results; no route-generation/review calls run. Three route alternatives remain configured for a future explicitly enabled synthesis campaign. Input reservations are conservative, so the run may stop before that nominal candidate count. Invalid JSON repair attempts consume budget. Completed stages are cached and are not paid for again on resume. A budget-exhausted campaign requires a new, explicitly configured campaign to increase its frozen budget; simply rerunning does not increase it. Monetary cost depends on provider pricing.

## Literature and synthesis evidence

Add local PDF/text paths under `literature_files` in a new campaign configuration. Relative paths resolve against that configuration. Add known starting structures under `seed_cif_files`; built-in seeds are explicitly identified as known prototypes. Scanned PDFs require external OCR. There is no paywall bypass, patent search, comprehensive supplementary-data ingestion or claim of retrieving all literature. Europe PMC provides a useful accessible subset but is not a comprehensive materials-science index.

Every citation has a source ID, chunk ID and exact quotation. Text extraction stores page or section locations and hashes. Citation checks verify that the quotation exists; they do **not** prove that it entails the proposed chemistry. Metadata or an abstract cannot upgrade a synthesis claim to full-text-supported status.

Each proposed route states phase-selection reasoning, precursors, operations, intermediate phases, conditions, competing phases, equipment, characterization and failure conditions. Each step receives a model assessment plus deterministic checks. Missing evidence is `unknown`, conflicting conditions are `contradicted`, and supported assessments require valid full-text citations and complete step fields. No numeric synthesis probability is invented. All-supported routes become candidates for expert review, not automatically approved laboratory procedures. A route can remain incomplete when fewer alternatives are defensible.

Successful simulation of a final crystal does not simulate deposition chemistry, nucleation or growth. Those require mechanism-specific models and experimental evidence. The pipeline records that gap instead of deriving fabrication certainty from a stable relaxed structure.

## Physics and remaining validation

By default, relaxation, sampled phonons and elastic response run on CPU. Set `thermal: true` in a new configuration to enable PET-MAD force calculations with phono3py third-order force constants and three-phonon RTA conductivity. This is more expensive and bounded by the worker timeout, cell size and displacement budget. The reported conductivity is the minimum eigenvalue of the 300 K bulk tensor. The initial 2×2×2 supercell and 9×9×9 mesh are **not a converged transport calculation**, and film boundaries and interface scattering are absent.

The real silicon control in `runs/silicon-thermal` completed relaxation, vibrations, elasticity and transport. It produced approximately 176.9 GPa Young's modulus, 70.85 GPa shear modulus and 61.91 W/(m K) minimum thermal-tensor eigenvalue. These demonstrate execution of the simulation path; known silicon is not a discovered dielectric, and these numbers are not measurements or an accuracy validation.

Static dielectric response is still **unconfigured**. There is no functioning DFPT engine or validated dielectric predictor hidden behind the model key. Candidate dossiers emit pending validation-job descriptions for this work. Similarly, `hull.py` can calculate a hull from evaluator-owned entries with identical model/settings hashes and rejects mixed ML/DFT energies, but the campaign does not yet collect and calculate all competing phases automatically. A restricted supplied-reference hull does not certify global thermodynamic stability. A second potential cross-check is not yet integrated.

Database lookups cache each chemical system and retrieval settings. Page limits, skipped/disordered structures and errors are reported. The new local JARVIS/OQMD index works without network access. A known local structure match avoids unnecessary online calls. Successful online retrievals are reused across campaigns for seven days, keyed by chemical system and retrieval settings; each campaign retains its own dated cache. Earlier failed lookups remain historical evidence. Materials Project access was verified locally with a bounded five-record silicon query. Repository users must configure their own key. No-match is never automatically labeled globally novel.

Before selecting a discovery, we need converged and independently checked target properties, a sufficiently complete consistent-energy phase comparison, a focused prior-art review, and expert review of the proposed synthesis. Actual synthesis and characterization are the final validation.

## Artifacts and checks

Campaign output contains `evidence.sqlite`, source and query ledgers, seed structures, frozen code/configuration, model requests/responses and token accounting, raw physics outputs, CIF files, route portfolios, per-step reviews, candidate dossiers and `report.html`.

```bash
../.bench-venv/bin/python -m pytest -q
../.bench-venv/bin/python scripts/check_sources.py
../.bench-venv/bin/mdb screen examples/silicon-control.json \
  --output runs/a-fresh-silicon-control --backend petmad --elastic --thermal --timeout 300
```

Tests include an explicitly scripted known-silicon control with three unsupported route fixtures. That checks orchestration, persistence, citation safeguards, grading and resume behavior; it is not a model-performance result. The live source check and real PET-MAD calculation test separate external integrations. The new evolution/critic orchestration test uses scripted responses, not a paid model-performance evaluation. Real earlier campaign outputs remain preserved.

The [benchmark harness README](README.md) retains the public-release audit and matched-budget comparison tools. An eventual SOTA claim needs the exact official protocol and a fair baseline; our immediate objective is a defensible candidate and synthesis portfolio.


## Local libraries and reproducible imports

The installed snapshots contain **93,902 JARVIS records** and **813,357 OQMD records**, after identifier deduplication. Six invalid OQMD records were skipped. Missing nonfinite property components become null; nonfinite structure coordinates are rejected. Dataset IDs, archive SHA-256, publisher MD5, version, license and processed/skipped counts are retained in the SQLite manifest. These are calculated reference records, not 907,259 experimentally established or globally distinct materials.

The catalog is [`open-snapshots.json`](open-snapshots.json). Its sources are the official [JARVIS archive](https://doi.org/10.6084/m9.figshare.6815699), [OQMD distribution](https://doi.org/10.6084/m9.figshare.14206169), and [condensed-matter abstract archive](https://doi.org/10.6084/m9.figshare.22817651). The downloaded literature archive contains 137,927 rows that deduplicate to 87,148 source records. Additional live retrieval and read-only indexing of previous campaign evidence brought this installation to **87,258 source records, including 16 full texts**. Most records remain abstracts; this is not a full-text corpus of all materials literature.

```bash
../.bench-venv/bin/python scripts/import_open_data.py --kind materials --download
../.bench-venv/bin/python scripts/import_open_data.py --kind literature --download
```

The compressed archives occupy about 153 MB; the material index about 456 MiB and literature memory about 171 MiB on this machine. COD's larger archive was not imported. Materials Project is queried on demand, not bulk mirrored. Imported DFT energies never enter a PET-MAD phase hull.

`reference_library.py` uses reduced-composition indexes to narrow structure comparisons, with a default cap of 300 comparisons. Each result records whether that composition's lookup was exhausted. A missing match is always unresolved global novelty. Candidate properties come from its evaluator; reference values remain separate, with their original field names and provenance.

The shared memory stores source hashes, page/section chunks, a full-text inverted index and a separate computational-notes index. Candidate retrieval requires chemical names/formulas and physics-topic terms; single-letter element tokens and ambiguous “Al” are not used as broad literature filters. Matching chemical mentions is explicitly weaker than evidence for the exact phase. A campaign copies only selected original source/chunk records into its own ledger, retaining citation IDs. Completed candidate findings become labeled research notes; they cannot certify themselves as independent literature. Two existing candidate dossiers were also indexed through read-only access, so their failed checks can inform future proposals without rewriting the original runs. Context budgets and source diversity bound prompt sizes. A local chemical-system query was measured at roughly 46 ms before the final relevance tightening; latency is hardware/query dependent.

## Evolution, critic and selection metric

The loop is inspired by the propose–evaluate–select pattern of [AlphaEvolve](https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/). This is our implementation for material hypotheses, not AlphaEvolve source or an equivalent performance claim. It saves the entire population and uses nondominance ranking plus chemical-system diversity to choose parents. Failures remain available for repair; context contains bounded parent and failure summaries.

A child supplies parent IDs, a mutation operator, the parent's problem it addresses, physical mechanism, change rationale, expected tradeoffs and a falsification test. Parent IDs must point to previously evaluated candidates. An independent model request critiques the actual computed properties and relevant source excerpts. Its references are checked for valid evaluator fields or exact citation text; traceability does not verify its reasoning, and the critic cannot change numerical grades.

Selection uses three dimensions: (1) the fraction of six predicted physics checks passed, (2) the best uncalibrated route-support fraction, currently zero while synthesis is paused, and (3) negative failed-check count. The six checks are relaxation, sampled dynamic stability, Young modulus, shear modulus, thermal conductivity and static dielectric response. Unknown values receive no pass credit. Known structure equivalence is a failed novelty check. Hull and experimental synthesis remain unknown. No candidate can earn a validated-discovery label from these scores.

Imaginary modes below −1 THz reject the dynamic screen and skip subsequent elasticity/transport work. The interval [−1, −0.1) THz is unresolved and requires numerical convergence checks. These are operator screening tolerances, not universal physical stability criteria. The formal-charge audit reports its assumed oxidation states and charge residual; it challenges unsupported ionic/closed-shell reasoning without declaring every nonzero count physically impossible. Canonical composition is derived from the actual cell, and discrepancies in the proposer label are shown.

## Current verification and outstanding scientific work

`tests/test_grounding.py` checks malformed upstream values, composition/charge errors, unknown versus failed physics, critic isolation, chemical retrieval, exact citation preservation, two-round parent feedback, separate memory and the synthesis pause. The complete suite currently passes **49 tests**.

```bash
../.bench-venv/bin/mdb validate --output runs/a-fresh-validation --simulate --cases 12
```

`runs/grounding-validation-confirmed/validation.json` records **72/72 known-reference recognition checks**: 24 source records tested as original cells, translated cells and supercells. This is an invariance/recognition test, not blind LLM rediscovery. Real PET-MAD controls returned near-zero minimum phonon frequencies and valid moduli for diamond Si and C (Young modulus approximately 176.9 and 1059.1 GPa respectively). These are execution controls, not an accuracy benchmark. The earlier sandbox-blocked attempt remains in `runs/grounding-validation` with its failure logs.

The browser check `scripts/check_grounded_studio.py` verifies real historical instability and withheld-property labels, composition mismatch, budget explanations, the synthesis pause, both local searches and desktop/mobile rendering, without model calls. Original run files were not rewritten. The current dashboard adds a clearly labeled deterministic audit to legacy results.

Still required before claiming a useful discovery: converged DFT/DFPT validation, a sufficiently complete same-model reference hull, a second potential cross-check, calibrated property errors, blind rediscovery and matched-budget random/substitution baselines, focused exact-phase prior-art review, and experimental characterization. None of the software checks establishes synthesis feasibility, world novelty or SOTA performance.
