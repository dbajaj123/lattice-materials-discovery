"""Real atomistic prescreen. Not the unavailable official property evaluator."""
from __future__ import annotations

import importlib.metadata
import hashlib
from pathlib import Path

import numpy as np

from .schema import Crystal, PhysicsResult
from .live_events import atomic_json, emit


def petmad_screen(crystal: Crystal, workdir: Path, *, version="1.0.2", elastic=False, thermal=False,thermal_max_displacements=300) -> PhysicsResult:
    import torch
    from ase import Atoms
    from ase.filters import FrechetCellFilter
    from ase.optimize import BFGS
    from pet_mad.calculator import PETMADCalculator
    from phonopy import Phonopy
    from phonopy.structure.atoms import PhonopyAtoms

    workdir.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(2)
    emit(workdir,'relaxation','Loading PET-MAD and relaxing the crystal')
    atoms = Atoms(crystal.species, scaled_positions=crystal.frac_coords, cell=crystal.lattice, pbc=True)
    atoms.calc = PETMADCalculator(version=version, device="cpu")
    from platformdirs import user_cache_dir
    model_path = Path(user_cache_dir('pet-mad', 'metatensor')) / f'pet-mad-{version}.pt'
    with model_path.open('rb') as model_file:
        model_sha = hashlib.file_digest(model_file, 'sha256').hexdigest()
    optimizer = BFGS(FrechetCellFilter(atoms), logfile=str(workdir / "relax.log"))
    def trajectory_frame():
        atomic_json(workdir/'live-structure.json',{
            'crystal':{'lattice':atoms.cell.array.tolist(),'species':atoms.get_chemical_symbols(),
                       'frac_coords':atoms.get_scaled_positions().tolist()},
            'step':optimizer.nsteps,'energy_ev':float(atoms.get_potential_energy()),
            'max_force_ev_a':float(np.linalg.norm(atoms.get_forces(),axis=1).max())})
    optimizer.attach(trajectory_frame,interval=1)
    converged = bool(optimizer.run(fmax=0.03, steps=80))
    relaxed = Crystal(lattice=atoms.cell.array.tolist(), species=atoms.get_chemical_symbols(),
                      frac_coords=atoms.get_scaled_positions().tolist())
    result = PhysicsResult(
        status="partial", backend=f"PET-MAD/{version}", input_digest=crystal.digest(),
        relaxed=relaxed, converged=converged,
        warnings=["Independent local prescreen; official model revision/settings unavailable.",
                  "Static dielectric evaluator is not configured; thermal transport runs only when explicitly enabled.",
                  "Phonons use finite displacements and a finite q mesh, without polar nonanalytic corrections; not a full convergence study."],
        artifacts={"packages": {x: importlib.metadata.version(x) for x in ['pet-mad', 'ase', 'phonopy', 'torch']},
                   "requested_calculations": {"elastic":elastic,"thermal":thermal},
                   "exported_model_sha256": model_sha,
                   "energy_ev_per_atom": float(atoms.get_potential_energy() / len(atoms)),
                   "max_force_ev_a": float(np.linalg.norm(atoms.get_forces(), axis=1).max()),
                   "stress_gpa":(atoms.get_stress(voigt=False)*160.21766208).tolist(),
                   "pressure_gpa":float(-np.trace(atoms.get_stress(voigt=False))*160.21766208/3),
                   "relaxation_steps": optimizer.nsteps,
                   "phonon_supercell": [2, 2, 2], "phonon_mesh": [6, 6, 6]},
    )
    if not converged:
        result.warnings.append("Relaxation did not converge; remaining calculations skipped")
        return result
    if len(atoms) * 8 > 128:
        result.warnings.append("Phonon supercell exceeds local 128-atom budget")
        return result
    atomic_json(workdir/'physics-partial.json',result.model_dump())
    emit(workdir,'phonons','Computing finite-displacement phonons')
    cell = PhonopyAtoms(symbols=atoms.get_chemical_symbols(), cell=atoms.cell.array,
                        scaled_positions=atoms.get_scaled_positions())
    phonon = Phonopy(cell, np.diag([2, 2, 2]), primitive_matrix="auto")
    phonon.generate_displacements(distance=0.01, is_plusminus=True)
    forces = []
    for sc in phonon.supercells_with_displacements:
        displaced = Atoms(symbols=sc.symbols, scaled_positions=sc.scaled_positions, cell=sc.cell, pbc=True)
        displaced.calc = atoms.calc
        f = displaced.get_forces()
        if not np.isfinite(f).all():
            raise ValueError("Nonfinite displacement forces")
        forces.append(f - f.mean(axis=0))
    phonon.forces = forces
    phonon.produce_force_constants()
    phonon.symmetrize_force_constants()
    phonon.run_mesh([6, 6, 6], is_gamma_center=True)
    frequencies = np.asarray(phonon.get_mesh_dict()["frequencies"])
    if not np.isfinite(frequencies).all():
        raise ValueError("Nonfinite phonon frequencies")
    result.minimum_phonon_thz = float(frequencies.min())
    result.artifacts["phonon_displacements"] = len(forces)
    qpoints=np.asarray(phonon.get_mesh_dict()['qpoints'])
    result.artifacts['phonon_diagnostics']={
        'modes_below_minus_0_1_thz':int((frequencies<-.1).sum()),
        'gamma_frequencies_thz':frequencies[np.linalg.norm(qpoints-np.rint(qpoints),axis=1)<1e-8].tolist(),
        'interpretation':'Three Gamma acoustic translations approach zero. Near-zero numerical signs alone are not evidence of marginal stability; convergence and mode inspection are still required.'}
    np.savez_compressed(workdir / "phonons.npz", frequencies_thz=frequencies,
                        qpoints=qpoints, force_constants=phonon.force_constants)
    result.artifacts["phonon_data"] = "phonons.npz"
    atomic_json(workdir/'physics-partial.json',result.model_dump())
    if result.minimum_phonon_thz < -1:
        result.warnings.append('Large imaginary phonon frequency: elastic and transport calculations skipped. Repair the structure and verify stability before further property screening.')
        emit(workdir,'physics_rejected','Dynamic instability found; downstream properties skipped')
        return result
    if elastic:
        emit(workdir,'elasticity','Computing the elastic response under strain')
        stiffness = np.zeros((6, 6))
        internal_converged = True
        strain_size = 0.005
        for j in range(6):
            stresses = []
            for sign in (-1, 1):
                strain = np.zeros((3, 3))
                if j < 3:
                    strain[j, j] = sign * strain_size
                else:
                    a, b = [(1, 2), (0, 2), (0, 1)][j - 3]
                    strain[a, b] = strain[b, a] = sign * strain_size / 2
                deformed = atoms.copy()
                deformed.set_cell(atoms.cell.array @ (np.eye(3) + strain), scale_atoms=True)
                deformed.calc = atoms.calc
                opt = BFGS(deformed, logfile=None)
                internal_converged &= bool(opt.run(fmax=0.02, steps=40))
                stresses.append(deformed.get_stress() * 160.21766208)
            stiffness[:, j] = (stresses[1] - stresses[0]) / (2 * strain_size)
        c = (stiffness + stiffness.T) / 2
        result.artifacts["elastic_tensor_gpa"] = c.tolist()
        result.artifacts["elastic_internal_relaxation_converged"] = internal_converged
        result.artifacts["elastic_strain"] = strain_size
        if internal_converged and np.isfinite(c).all() and np.linalg.eigvalsh(c).min() > 0:
            s = np.linalg.inv(c)
            kv = c[:3, :3].sum() / 9
            gv = (np.trace(c[:3, :3]) - (c[0, 1] + c[0, 2] + c[1, 2]) + 3 * np.trace(c[3:, 3:])) / 15
            kr = 1 / s[:3, :3].sum()
            gr = 15 / (4 * np.trace(s[:3, :3]) - 4 * (s[0, 1] + s[0, 2] + s[1, 2]) + 3 * np.trace(s[3:, 3:]))
            bulk, shear = (kv + kr) / 2, (gv + gr) / 2
            result.shear_gpa = float(shear)
            result.youngs_gpa = float(9 * bulk * shear / (3 * bulk + shear))
            result.artifacts["elastic_reduction"] = "Voigt-Reuss-Hill isotropic aggregate; not a specified film orientation"
        else:
            result.warnings.append("Elasticity invalid or internally unconverged; moduli withheld")
        atomic_json(workdir/'physics-partial.json',result.model_dump())
    if thermal and result.minimum_phonon_thz is not None and result.minimum_phonon_thz<-.1:
        result.artifacts['thermal']={'status':'withheld_unresolved_phonons','reason':'Resolve imaginary modes before transport calculations'}
    elif thermal and result.minimum_phonon_thz is not None:
        result.artifacts['thermal']={'status':'running'}
        atomic_json(workdir/'physics-partial.json',result.model_dump())
        emit(workdir,'thermal','Computing anharmonic forces and thermal transport')
        from .thermal import calculate_thermal
        try:
            transport=calculate_thermal(atoms,workdir,max_displacements=thermal_max_displacements)
            result.artifacts['thermal']=transport
            if transport['status']=='computed_preliminary':
                result.kappa_w_mk=transport['minimum_eigenvalue_w_mk']
                result.warnings.append('Thermal conductivity is a preliminary bulk RTA estimate; supercell and q-mesh convergence are not established.')
            else:
                result.warnings.append('Thermal conductivity withheld: '+str(transport))
        except Exception as exc:
            result.artifacts['thermal']={'status':'failed','error_type':type(exc).__name__}
            atomic_json(workdir/'thermal-progress.json',result.artifacts['thermal'])
            result.warnings.append(f'Thermal calculation unavailable/failed ({type(exc).__name__}); conductivity withheld')
        atomic_json(workdir/'physics-partial.json',result.model_dump())
    emit(workdir,'physics_complete','Physics screening finished')
    return result
