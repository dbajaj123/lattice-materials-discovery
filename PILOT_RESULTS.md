# Initial commissioning results

The objective remains a useful new alloy composition with a plausible synthesis route. No novel material is established by this campaign.

## Completed

- Eight budgeted binary proposals: four random and four feedback-heuristic proposals, including the shared reference.
- Three restricted ternary equilibrium screens; kinetics deliberately unassessed.
- One two-stage temperature-ramp route completed on the longer 600-second wall budget.
- Six designed parameter/resolution scenarios; no calibrated probability interval.
- Three literature endpoint comparisons and 36 cached bibliographic records.
- Source-linked preparation analogue attached for the strongest initial screen.
- Interactive offline dashboard and marimo viewer; software tests and browser checks passed.

## Scientific finding

All three predicted mean radii fall outside the reported ranges. Number densities are substantially underpredicted. This requires calibration and/or model changes before using the rankings to claim improved material performance.

| Sc (wt.%) | Measured radius (nm) | Predicted radius (nm) | Predicted/measured number density |
|---|---|---|---|
| 0.1 | 8.8 ± 0.5 | 10.45 | 0.0086 |
| 0.2 | 3.0 ± 0.4 | 9.92 | 0.1318 |
| 0.3 | 2.0 ± 0.4 | 6.04 | 0.1945 |

Source: [Marquis and Seidman, Table 1](https://www.dunand.northwestern.edu/refs/files/Marquis-Nanoscale.pdf), printed page 1915. Reported errors are not interpreted as a specific confidence level. The source is related to upstream parameter literature, so this is not a blind independent holdout.

The reference's final strengthening contribution changes by 0.160% with finer resolution, but the parameter sensitivity range is 5.08–192.39 MPa. Numerical convergence does not remove parameter or model uncertainty.

The small random baseline narrowly exceeds the feedback heuristic in best final modeled strengthening. Four proposals and one seed are insufficient to claim a method advantage. The heuristic is not a live LLM.

## Immediate next work

1. Diagnose the radius and nucleation-density discrepancies against independently sourced experiments; represent heterogeneous nucleation and preparation history where needed.
2. Validate thermodynamic and mobility inputs before enabling multicomponent kinetic rankings.
3. Connect a reasoning model to the existing proposal/evaluation contract and compare against Bayesian optimization under matched budgets.
4. Audit substantive composition/process novelty and complete the preparation/characterization plan for any robustly promising candidate.

Artifact entry point: `runs/initial/report.html`. The local server serves it at `http://127.0.0.1:8765/report.html`.
