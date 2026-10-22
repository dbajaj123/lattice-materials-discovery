# Studio fixes and evaluator checks — 2026-10-23

The local studio supports persistent proposer and critic model selection, with explicit dashboard settings taking precedence over environment defaults. Runs retain frozen model choices. Saving settings does not make a model request or verify model access. Synthesis remains paused.

The validation suite passed 66 tests. Browser checks passed for persisted model choices after refresh, invalid-setting errors, all five credential-provider entries, capability descriptions, historical property statuses, synthesis pause and desktop/mobile layouts. Browser tests restored the original settings and made no model calls.

Real known-silicon controls exercised the current PET-MAD / Phonopy / phono3py path:

| Quantity | Model output |
|---|---:|
| Relaxation | Converged |
| Minimum sampled phonon frequency | approximately −2.25 × 10⁻⁷ THz |
| Young's modulus | 176.89 GPa |
| Shear modulus | 70.85 GPa |
| Minimum thermal-conductivity tensor eigenvalue at 300 K | 61.91 W/(m·K) |
| Anharmonic displacements | 194 |

A separate one-displacement-budget control correctly withheld conductivity and reported the required 194 displacements. The final transport-progress check recorded `computed_preliminary` after all 194 displacements, rather than leaving the progress record marked running.

These checks establish execution and reporting, not predictive accuracy. Silicon is known. Transport used a 2×2×2 supercell, 9×9×9 q mesh, third-order finite-displacement force constants and the relaxation-time approximation. Supercell, mesh and force/displacement convergence are not established. The tiny signed acoustic minimum is not by itself evidence of instability. The outputs are neither DFT results nor measurements.

The latest saved discovery candidates required 18,480 (AlB2N3O2) and 4,632 (BC2N) anharmonic displacements under the current settings. This exceeds the default 300-displacement budget. Those workload inspections did not calculate candidate conductivity. Raising the budget is an explicit run setting, not a convergence guarantee.

Other corrections separate input and final densities, block inconsistent proposal labels and unexplained nominal-charge claims before physics, preserve raw historical dossiers while displaying a current deterministic audit, distinguish missing/disabled/failed/timed-out properties, reject invalid citation support, retry transient provider failures, expire failed provider caches and synchronize stopped-run status. Bulk modulus and Poisson ratio are derived isotropic elastic properties and carry that provenance.

Dielectric response, band gaps, electronic transport, a complete same-model competing-phase hull and a second-potential cross-check remain unconnected. Route synthesis remains paused. No new material discovery, globally exhaustive novelty check, calibrated certainty or benchmark SOTA result is claimed.

Local raw artifacts are intentionally ignored by Git:

- `runs/live/20261022-211911-3eae5d`: one-displacement-budget silicon control.
- `runs/live/20261022-212006-237161`: silicon transport result.
- `runs/live/20261022-212211-d9fef6`: terminal transport-progress verification.
- `runs/report-fixes-20261023/audit.json`: derived audit of the historical discovery run.
- `runs/model-settings-desktop.png` and `runs/model-settings-mobile.png`: browser captures.

Run `python -m pytest -q` in the installed bench environment for the automated suite. `scripts/check_model_settings.py` additionally needs the local server, the saved discovery run it references, Playwright and Chrome; it is a local regression script, not a portable standalone unit test.
