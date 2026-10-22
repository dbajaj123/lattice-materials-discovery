# Material Discovery Bench harness

**Live dashboard:** http://127.0.0.1:8768/ · Launch from this directory with `../.bench-venv/bin/mdb-studio --port 8768`. Start/stop real calculations, inspect rotating crystal structures, and follow evidence-graded synthesis route diagrams. The silicon control needs no model key; discovery uses `bench/.env`.

**Start here for our own discovery pipeline: [DISCOVERY.md](DISCOVERY.md).** It connects a 907,259-record reference library, searchable literature memory, population-based proposals, simulations, and a physics critic. Synthesis is currently paused. It can operate independently of the unavailable official benchmark source. The rest of this document describes the benchmark audit and comparison tooling.

For the missing dielectric evaluator, see [the Quantum ESPRESSO integration workflow](DFPT.md). DFPT is not connected yet. The shipped discovery configuration now requests thermal transport after stable screening; displacement budgets, timeouts and disabled calculations are reported separately. Enabling transport does not guarantee that a candidate fits the computational budget.

**Choose models in Run settings:** enter `provider/model-id` for the proposer and optionally a separate critic; an empty critic field follows the proposer. OpenAI, Anthropic, Google and OpenRouter keys can be configured from the API key dialog. Settings persist locally in ignored `runs/studio-settings.json`. Explicit dashboard choices override environment model defaults and are frozen into each new run. Saving settings makes no provider request and does not verify model access. Existing runs keep their original models.

The **What can we test?** panel distinguishes available geometry, energy/force/stress, phonon and elastic evaluations from budget-limited lattice thermal conductivity and unavailable dielectric/electronic/hull workflows. Bulk modulus and Poisson ratio are derived from isotropic elastic moduli, not independent validation. All atomistic outputs are model predictions. Run settings expose both simulator timeout and maximum anharmonic displacements; increasing either does not establish physical convergence. Synthesis stays paused.

The goal is a useful new chip material with a defensible synthesis route, and an eventual matched-budget comparison with Material Discovery Bench. This directory is the new project direction. The older Al–Sc prototype is separate.

**Status: working independent development harness; exact upstream port and official SOTA evaluation blocked on unavailable upstream assets.**

The repository linked by the publisher, <https://github.com/advaith-dm/materials-autoresearch>, returned 404 through GitHub, its API, and git. The account's public repository listing was empty. We imported the accessible public release and implemented an independent harness from documented methods. We have not obtained or copied the official evaluator source, recipe rubrics, or dielectric weights. This is not an official benchmark implementation.

## What runs

- Public snapshot importer with SHA-256 verification. JSON embedded in JavaScript is parsed as data, never evaluated as code.
- Audit of 531 released rows, 193 formula strings and their structures/recipes. Published verdicts: 478 refuse, 52 unlikely, 1 attempt. These are historical, selected release rows, not new discoveries or a complete attempt denominator.
- Pymatgen structure matching across primitive cells, reordered sites and supercells. At the local tolerance, the release forms 426 global structural groups. This grouping spans models and runs; it is not a count of within-run cheating.
- Inspect agent task with baseline and synthesis-first strategies; literature retrieval, crystal construction, simulation, persistent research notes, route revisions, and submission tools.
- Real PET-MAD 1.0.2 relaxation, Phonopy finite-displacement phonons and optional finite-strain relaxed-ion elastic calculations. Missing conductivity and dielectric predictions remain unknown.
- Operator-owned simulation outputs, independent of agent proposals. Missing novelty/synthesis reviews prevent discovery credit. Raw host shell execution is not exposed to the agent.
- Per-run frozen Python source, configuration and event logs; worker time limits; invalid/repeated proposals consume budget. Three route revisions can reuse physics without generating extra material credit.
- Offline interactive report with property comparisons, published recipe verdicts and a selectable 3D crystal viewer.

## Environment and commands

The separate environment is `../.bench-venv` (Python 3.12). From this directory:

```bash
../.bench-venv/bin/mdb doctor
../.bench-venv/bin/mdb audit data/public-20261023 --output runs/release-audit.json
../.bench-venv/bin/mdb report data/public-20261023 runs/release-audit.json --output runs/report.html
../.bench-venv/bin/python -m pytest -q
../.bench-venv/bin/python scripts/check_agent.py
```

The report is at `runs/report.html`. The scripted agent test uses Inspect's mock provider: it verifies actual tool dispatch, screening, submission and scoring, without calling a paid model. It is not an agent-performance result.

A real local control calculation:

```bash
../.bench-venv/bin/mdb screen examples/silicon-control.json \
  --output runs/new-silicon-control --backend petmad --elastic --timeout 300
```

Output directories must be fresh. Initial model download needs network access and PET-MAD writes its normal platform cache. The control is known silicon, not a new material. The first successful calculation converged and returned a sampled minimum frequency near zero, Young's modulus about 177 GPa and shear modulus about 71 GPa. These are model outputs, not measurements. Thermal conductivity and dielectric response were unassessed.

To install on another machine:

```bash
python3.12 -m venv ../.bench-venv
../.bench-venv/bin/python -m pip install -e '.[simulation,test]'
```

`requirements-lock.txt` records the installed environment. Apple Silicon wheels were used here; portability requires checking compatible wheels on other platforms.

## Live agents and paired experiments

No model API credentials were available in this session. Configure the chosen Inspect provider's credentials in the process environment; do not put secrets in proposal files or logs. Exa search is used when `EXA_API_KEY` is present; otherwise the tool retrieves Crossref metadata, which cannot verify synthesis mechanisms or novelty.

```bash
../.bench-venv/bin/inspect eval src/mdb_harness/task.py@discovery \
  --model PROVIDER/MODEL \
  -T strategy=synthesis_first -T backend=petmad \
  -T token_budget=10000 -T screen_budget=8
```

Create a concrete matched-budget plan without making model calls:

```bash
../.bench-venv/bin/python scripts/compare_strategies.py \
  --model PROVIDER/MODEL --output runs/paired-plan
```

To execute a plan, use a fresh output directory and add `--execute`. The default is five seed pairs, 10,000 tokens and eight screening calls per run. This is an engineering pilot, not a comparison to the published 30–100M-token runs. A seed may not guarantee deterministic generations for every provider. Both strategies receive the same tool surface and budgets.

**Do not spend a leaderboard-scale budget until the missing evaluators are integrated.** Currently, unknown property/novelty/synthesis gates intentionally prevent every submission from receiving discovery credit. A zero local score indicates incomplete verification, not proof that every proposed material is scientifically worthless.

## Route to a defensible SOTA attempt

1. Obtain the publisher's runnable source revision, exact task/profile, model artifacts and complete grading rubrics. Reproduce a baseline under that evaluator before changing the agent.
2. Connect the official evaluator behind the existing proposal/evaluation boundary. Preserve official novelty definitions, tensor reductions, exclusions, numerical settings and grading isolation. Local strengthening of checks must not silently change the official score.
3. Run paired baseline versus synthesis-first investigations with matched model, tools, total token/compute budgets, data cutoff and grading. Keep published benchmark structures out of new-discovery submissions; retain failed and repeated attempts in denominators.
4. Improve phase-selective synthesis reasoning and failure-driven experiment selection. Preregister ablations of notebook use, early synthesis screening and route revision. Tune on development cases; reserve new independent cases for comparison.
5. Report unique qualifying candidate–route pairs per run and per budget, compute cost and uncertainty across runs. Use a blinded, independent synthesis review; self-critique is not a verdict. Compare the same statistic and budget with the official baseline before claiming an improvement.

## Scientific and comparison limits

- The current research page uses static dielectric constant and qualifying candidate counts. The older methods page describes high-frequency dielectric constant, Pareto hypervolume, a stagnation stopping condition and DFT verification. These are not interchangeable protocols. The current page also differs on strict versus inclusive threshold notation. Local gates use `kappa > 20`, `1 <= epsilon_static < 10`, `Y >= 20`, `G >= 6`, and sampled phonon minimum `>= -1 THz`; the lower epsilon bound and 400 C ceiling are explicit local assumptions, not a verified exact official configuration.
- The release field is named `epsInf`; its meaning must be resolved before applying current static-epsilon thresholds. The report preserves it as an unresolved exported field. Legacy hypervolume is an exploratory diagnostic only, not an official score.
- All public property rows were marked `mlip` or `mlip-verified`. Neither label establishes DFT or experimental validation. Published recipe verdicts do not establish successful synthesis.
- Finite phonon mesh/supercell checks are not a proof of global dynamic stability. Polar nonanalytic corrections, thermal-conductivity convergence and thin-film orientation effects are not covered by the control run. Elastic moduli are Voigt–Reuss–Hill aggregate estimates, not a specified device-film direction.
- The local per-step checks grade completeness and explicit temperature conflicts. They do not simulate reaction kinetics, prove phase formation, or assign calibrated success probabilities.
- Full official recipe rubrics, tensor-model checkpoints and evaluator settings are missing. A different dielectric predictor would be an alternate benchmark, not an exact port.
- Public data caches and generated reports are ignored by version control. No upstream code license was verified; this project does not represent the downloaded data as newly licensed source.

Primary sources: [current benchmark](https://discoveredmaterials.com/research/), [legacy methods](https://petmad.matforge.ai/bench/about.html), [PET-MAD](https://github.com/lab-cosmo/pet-mad), [Inspect](https://inspect.aisi.org.uk/agents.html).
