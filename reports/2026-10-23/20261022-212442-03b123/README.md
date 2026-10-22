# Discovery run 20261022-212442-03b123

Model: `openai/gpt-6-astra`. Status: **complete**. 6 model requests; 14,472 charged/reserved tokens.

These are saved model predictions and original screening decisions, not verified discoveries. Missing properties are unassessed.

| Candidate | Formula | Relaxation | Young (GPa) | Shear (GPa) | Thermal result |
|---|---|---|---:|---:|---|
| r00-c00 | AlSi3C3N | converged | 378.99 | 154.29 | budget_exceeded (18,480 displacements required) |
| r00-c01 | BC6N | converged | 881.78 | 402.88 | budget_exceeded (9,372 displacements required) |
| r01-c00 | AlSi7C7N | not evaluated | — | — | not calculated |
| r01-c01 | BC14N | converged | 956.38 | 432.05 | budget_exceeded (73,824 displacements required) |

## Limits and corrections

Dielectric response, complete competing-phase hull and independent potential/DFT cross-checks were not calculated. Finite-mesh phonons and elastic predictions do not establish synthesis feasibility or global novelty.

Source coverage: {'abstract_archive': 22, 'abstract_preprint': 33, 'metadata': 56, 'full_text_open_access': 3, 'full_text_preprint': 5, 'abstract': 6}. Source metadata is included; abstracts, full papers and model request prompts are not redistributed.

- r01-c00: the original formula checker incorrectly treated an explicitly named parent prototype as the candidate formula. The checker is fixed in current code. This run's original preflight rejection is retained; physics was not rerun and no stability conclusion follows from that rejection.

[Interactive report](report.html) · [Source metadata](sources.json) · [Usage ledger](usage.json)
