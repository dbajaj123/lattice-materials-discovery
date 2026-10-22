# Materials discovery

**Current direction:** our independent, literature-grounded discovery pipeline is in [bench/DISCOVERY.md](bench/DISCOVERY.md). It proposes crystalline chip materials, runs physics calculations and develops multiple synthesis routes with per-step evidence review. [bench/README.md](bench/README.md) contains the Discovered Materials benchmark audit and comparison tools. The Al–Sc work below is the earlier prototype, not an established discovery.

**Objective: identify a useful new alloy composition together with a plausible, evidence-supported synthesis and processing route.**

This first implementation commissions the evaluator on precipitation-strengthened aluminum alloys. It connects **real Kawin precipitation kinetics and pycalphad thermodynamics** to composition/route proposals, deterministic intermediate-step checks, a feedback search baseline, literature retrieval and interactive visualizations.

It does **not** establish a new material. Binary Al–Sc is a known calibration system. Al–Sc–Zr is a known family, and arbitrary differences in composition decimals do not establish novelty.

**Initial scientific finding:** fixed upstream parameters miss all three reported particle-radius ranges in the first literature comparison, with substantial number-density errors. The evaluator is functioning, but discovery rankings require calibration. See `runs/initial/experimental-comparison.json` and the dashboard. The two-stage ramp example completed with a larger wall-time budget.

## Run

Python 3.12 is recommended. The local `.venv` is already installed.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/alloy-discovery campaign --budget 4 --output runs/initial
.venv/bin/alloy-discovery report runs/initial/campaign.json --output runs/initial/report.html
.venv/bin/python -m http.server 8765 --bind 127.0.0.1 --directory runs/initial
```

Open `http://127.0.0.1:8765/report.html`. The HTML report is self-contained, including Plotly, and can also be opened directly from disk. It displays **actual cached simulator outputs**, not generated microscopy images.

For the reactive notebook:

```bash
.venv/bin/marimo run app.py --host 127.0.0.1 --port 8766 --headless
```

## Propose and evaluate

```bash
.venv/bin/alloy-discovery example examples/reference.json
.venv/bin/alloy-discovery evaluate examples/reference.json --output runs/reference
.venv/bin/alloy-discovery evaluate examples/two_stage.json --output runs/two-stage
.venv/bin/alloy-discovery evaluate examples/ternary.json --output runs/ternary
.venv/bin/alloy-discovery sensitivity examples/reference.json --output runs/initial
.venv/bin/alloy-discovery literature --output runs/initial
.venv/bin/alloy-discovery benchmark --output runs/initial
.venv/bin/alloy-discovery synthesis-route examples/two_stage.json --output runs/two-stage/synthesis-route.json
.venv/bin/alloy-discovery agent-context --campaign runs/initial/campaign.json
.venv/bin/python -m pytest -q
```

The candidate schema uses **atomic fractions summing to one**; neither weight percent nor atomic percent is silently accepted. Temperatures in proposals are °C, durations hours. The backend converts to Kelvin and seconds. A temperature change requires an explicit ramp duration.

`agent-context` exports the objective, JSON proposal schema, evidence and evaluation feedback for a reasoning agent. An external agent proposes a candidate, invokes `evaluate`, reads the complete result and chooses its next action. The built-in `feedback_heuristic` is deliberately labeled as a deterministic baseline; **no live LLM is connected or claimed**. An LLM cannot write its own scientific grades.

## What is implemented

- Binary Al–Sc: actual KWN kinetics, persistent particle populations across aging steps, and the upstream model for precipitation strengthening.
- Al–Sc–Zr: actual restricted-phase equilibrium calculations. Kinetics and strength remain unassessed because the bundled database does not supply a validated complete ternary mobility description. Binary strength parameters are not silently extrapolated.
- Per-step finite-value, positivity, normalized-composition, end-time and internal solute-balance checks. Numeric success and objective attainment are separate.
- Step endpoint particle distributions and downsampled trajectories that retain strength extrema and step endpoints.
- Matched proposal budgets for random and feedback baselines, deterministic seeds, Pareto filtering for strengthening/Sc content/processing time. Repeated and invalid evaluations consume proposal budget; cache hits are explicit.
- Isolated subprocess simulations with timeout, logs and content-addressed request/result records. Cache identity includes physical inputs, settings, evaluator code, database and key numerical library versions. New jobs execute a frozen source copy retained with their artifacts; early commissioning jobs predate source snapshots.
- Designed sensitivity perturbations for interfacial energy and diffusion, plus a two-resolution comparison. These are **sensitivity ranges, not calibrated confidence intervals**.
- Cached live Crossref metadata searches and curated source records. Search errors remain errors; no-results never means novel.
- Three published experimental endpoints with source location and explicit weight-to-atomic-fraction conversion; a fixed-parameter consistency comparison, not a blind validation or uncertainty calibration.
- A source-linked preparation analogue for binary compositions in the paper's range. Out-of-range or ternary compositions are flagged rather than inheriting that recipe.
- Standalone interactive HTML plus a marimo viewer. Changing dashboard controls reads stored results and does not launch simulations.

## Interpretation and limits

1. The predicted MPa value is the **precipitation contribution**, not measured or total yield strength. Ductility, fracture, corrosion, fatigue, conductivity and cost are not modeled. Sc concentration is a resource-use axis, not a dollar cost model.
2. Aging starts from an **assumed homogeneous supersaturated FCC matrix**. A published thin-foil preparation route is attached as an analogue where composition permits. Initial heat-up, casting, solution treatment, quenching and availability of that starting state are not yet simulated. A full synthesis route therefore stays `conditional`. Variable-temperature calculations can be much slower than isothermal runs; increase `--timeout` for these. Use `--retry-failed` to retry a cached failed job. Completed step assessments are saved as `progress.json` during execution, including when a later step fails.
3. The database contains FCC_A1, AL3SC and AL3ZR. It lacks liquid and many possible competing phases. Its equilibria cannot certify a solidus, an exhaustive hull, or synthesis stability. Equilibrium phase amounts are mole fractions; KWN reports volume fractions under its own molar-volume convention.
4. Conservation checks use Kawin's internal concentration/volume convention. Passing them tests implementation consistency; it does not independently validate the physical model.
5. Screening bounds (0.03–0.30 at.% Sc, up to 0.20 at.% Zr, 250–450 °C) are software limits, **not validated applicability limits**. Bulk nucleation, spherical precipitates and upstream material parameters are assumptions. Dislocations, loss of coherency and other physics can invalidate extrapolation.
6. No experimental uncertainty model has been calibrated. Parameter perturbations omit correlations and model discrepancy. A two-resolution agreement is an initial numerical check, not proof of convergence.
7. Automated literature search currently retrieves metadata; one experimental paper's methods and numerical table have been manually reviewed. Comprehensive full-text, supplementary, patent and material-database comparisons remain outstanding. Valency MCP has not been connected.

## Evidence and reproducibility

See `src/alloy_discovery/data/evidence.json` for source roles and review status; `database-provenance.json` records the upstream database commit. The unmodified TDB and upstream license are included. `requirements-lock.txt` records the installed environment.

Core references:

- [Kawin model](https://doi.org/10.1016/j.actamat.2023.118988)
- [Upstream binary strength example](https://github.com/materialsgenomefoundation/kawin/blob/f0c347967fcfc18f6615cec205f584573606e100/examples/05_Strength_Modeling.ipynb)
- [Al3Sc experimental structural evolution](https://www.dunand.northwestern.edu/refs/files/Marquis-Nanoscale.pdf)
- [Experimental nucleation and coarsening](https://doi.org/10.1016/S0921-5093(01)01326-0)
- [Known Al–Sc–Zr precipitation pathways](https://arxiv.org/abs/cond-mat/0605738)
- [Prior Bayesian optimization of Al–Sc KWN processing](https://doi.org/10.3390/met12060975)

## Next work toward an actual discovery

1. **Establish trust:** expand the initial three-point literature comparison to independent trajectories with units, starting-state details and source locations. Fit on one subset; test coverage and errors on held-out compositions/temperatures. Include failed nucleation cases. Reject quantitative ranking where numerical resolution fails.
2. **Expand composition coverage:** obtain compatible assessed thermodynamic and mobility data for the chosen alloy additions; validate multicomponent kinetics, partitioning and mechanical models. Do not widen the search to unsupported elements.
3. **Complete the route:** model or document how the initial state can be made. Carry uncertainty through preparation, quench and aging. Attach sources and missing evidence to every operation.
4. **Connect reasoning:** give an LLM the existing proposal/evaluation contract, bounded tool budget and persistent evidence records. Require falsifiable hypotheses and evaluate against random, literature-retrieval and Bayesian-optimization baselines.
5. **Review novelty substantively:** compare composition ranges, tolerances, processing, microstructure and closest prior art. A new ratio inside an established alloy range is not enough. Freeze dated searches and review the top candidates manually.
6. **Select a candidate–route pair:** require robust improvements on defined useful properties, supported preparation steps and a characterization plan. Reserve “discovered material” for sufficient independent evidence.

The deliverable of this version is a functioning, inspectable foundation for that process, with its unsupported decisions visible.
