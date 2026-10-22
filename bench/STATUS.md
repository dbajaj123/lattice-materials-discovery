# Historical benchmark-port audit

This file records the initial benchmark audit. For the current 49-test studio, local libraries and synthesis pause, see [DISCOVERY.md](DISCOVERY.md). Local `runs/` artifacts mentioned below are not distributed with the repository.

The official repository link is unavailable. This is an independent development harness based on public methods and a preserved release snapshot. It has not beaten the benchmark or discovered a new material.

## Verified locally

- 15 unit/integration checks pass, covering structural supercells, distinct polymorphs, nonfinite geometry, fabricated score fields, epsilon-type confusion, threshold boundaries, budget consumption, route revisions, duplicate submissions and snapshot corruption.
- A scripted Inspect model completes a real tool loop: screen, submit, final response and scoring. It receives zero verified-discovery credit, as intended. This is an integration test, not a frontier-model run.
- PET-MAD 1.0.2 + ASE + Phonopy completed the silicon control, including internal relaxation at strained cells. This establishes that the real simulator path runs. It does not validate its accuracy for new compounds.
- Browser check passes candidate selection, all 531 released records, 3D crystal rendering, mobile width and JavaScript error checks.
- A paired strategy plan has been generated without calling a model provider.

## Public release audit

| Item | Result |
|---|---:|
| Released candidate rows | 531 |
| Distinct formula strings | 193 |
| Global structure groups at local matching tolerance | 426 |
| Repeated groups within represented model/run pairs | 20 |
| Publisher-labeled MLIP / MLIP-verified rows | 509 / 22 |
| Published recipe verdicts: refuse / unlikely / attempt | 478 / 52 / 1 |

Cross-model and cross-run repetition is expected; the 105 global collapses are not 105 examples of within-run misconduct. Matching tolerance is `ltol=0.1`, `stol=0.15`, `angle_tol=3`, `scale=False`, primitive reduction enabled and supercell matching enabled. This audit does not independently establish literature novelty or reproduce the official candidate count.

## Required before an official SOTA attempt

1. A working upstream source revision and licensed evaluator assets, including dielectric weights, thermal settings and full synthesis rubrics.
2. The exact benchmark profile and baseline logs: the current and legacy public methods disagree on dielectric objective and scoring.
3. Configured credentials for live model runs; none were present. The API keys themselves should stay in the local environment.

Artifacts: `runs/report.html`, `runs/dashboard.png`, `runs/release-audit.json`, `runs/paired-plan/plan.json`, `runs/mock-logs/`, and `runs/silicon-final/`.
