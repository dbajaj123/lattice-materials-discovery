# Connecting dielectric calculations

The studio currently has no DFT/DFPT runner. A Materials Project key provides database access; it does not run Quantum ESPRESSO. The existing PET-MAD potential supplies energies, forces and stresses, not electronic dielectric response. This document specifies the connection to implement once a compute machine is selected; it is not an executable integration or a completed calculation.

Use Quantum ESPRESSO (`pw.x`, `ph.x`, `dynmat.x`) behind the operator-owned evaluator. ASE can write plane-wave inputs and pymatgen can handle structures. A local subprocess runner or an explicitly configured scheduler should execute jobs; the proposing model must never supply accepted property numbers.

1. Export the exact candidate structure and record its digest. Select a consistent exchange-correlation functional and compatible, versioned pseudopotentials for every species; retain their hashes. Converge plane-wave/density cutoffs and electronic k-point sampling against the quantities of interest.
2. Relax atomic positions and cell with `pw.x` (`vc-relax`), then run a converged SCF calculation on that final geometry. Retain energies, forces, stress, electronic occupations and all input/output files. Reassess stability on the DFT structure. ML-screened stability does not establish DFT stability.
3. Establish that the candidate is insulating using appropriate electronic sampling. The insulating electric-field response is not valid for a metal; a small semilocal DFT gap also requires careful interpretation. Run `ph.x` at Gamma with `epsil=.true.` and `trans=.true.` to obtain the electronic dielectric tensor, Born effective charges and the Gamma dynamical matrix.
4. Run `dynmat.x` with `lperm=.true.` to obtain mode contributions to the ionic dielectric tensor. Inspect unstable optical modes and acoustic sum-rule corrections, rather than hiding a structural instability by applying a correction. For a stable insulating crystal, the fixed-strain static response is the electronic tensor plus the ionic contribution. This is distinct from a free-stress response in a piezoelectric crystal.
5. Parse only completed, converged outputs, bound to the input structure and job ID. Save the full electronic, ionic and total 3×3 tensors, principal values, DFT geometry, solver version, pseudopotential hashes and convergence studies. Use a declared reduction for the dashboard gate (for example the largest principal value for a low-permittivity objective). Withhold the scalar when the calculation fails or its physical assumptions do not apply.

Illustrative downstream inputs, valid only after the preceding SCF calculation has completed using the same `prefix` and `outdir`:

```text
Candidate Gamma dielectric response
&INPUTPH
  prefix='candidate', outdir='./scratch',
  fildyn='candidate.gamma.dyn',
  epsil=.true., trans=.true., tr2_ph=1.0d-14
/
0.0 0.0 0.0
```

```text
&INPUT
  fildyn='candidate.gamma.dyn',
  asr='crystal', lperm=.true.,
  filout='candidate.gamma.modes'
/
```

The tolerance shown is illustrative, not a demonstrated convergence setting. Full Brillouin-zone phonons require additional q points. A Gamma dielectric calculation alone does not verify dynamic stability throughout the zone or thermodynamic stability against competing phases.

Thermal conductivity uses a separate path: harmonic and third-order force constants, phonon scattering and a Boltzmann transport calculation (the current implementation uses phono3py RTA with PET-MAD forces). It needs displacement, supercell and q-mesh convergence checks. Neither the thermal conductivity nor the dielectric tensor is determined by elastic stiffness alone. Electrical conductivity is a third observable and is not presently evaluated by this studio.

Before accepting results, run known insulating controls (for example silicon and a polar insulator), compare against reproducible references using matching conventions, test numerical convergence, and verify failure handling with metallic, unstable and unconverged cases. These controls validate an implementation within their scope; they do not establish a universal error bar for new materials.

Primary documentation: [Quantum ESPRESSO pw.x](https://www.quantum-espresso.org/Doc/INPUT_PW.html), [ph.x](https://www.quantum-espresso.org/Doc/INPUT_PH.html), [dynmat.x](https://www.quantum-espresso.org/Doc/INPUT_DYNMAT.html), [phono3py transport workflow](https://phonopy.github.io/phono3py/).
