"""Optional real anharmonic transport; deliberately labelled preliminary."""
import importlib.metadata
import numpy as np
from .live_events import atomic_json,emit


def calculate_thermal(atoms,workdir,*,max_displacements=300,mesh=(9,9,9),temperature=300):
    from ase import Atoms
    from phono3py import Phono3py
    from phonopy.structure.atoms import PhonopyAtoms
    if len(atoms)*8>128:
        return {'status':'budget_exceeded','reason':'Supercell exceeds 128 atoms'}
    unit=PhonopyAtoms(symbols=atoms.get_chemical_symbols(),cell=atoms.cell.array,
                     scaled_positions=atoms.get_scaled_positions())
    ph3=Phono3py(unit,supercell_matrix=[2,2,2],primitive_matrix='auto',symprec=1e-3)
    ph3.generate_displacements(distance=0.03,is_plusminus=True)
    supercells=ph3.supercells_with_displacements
    progress={'status':'planned','required_displacements':len(supercells),'budget':max_displacements,
              'completed_displacements':0,'temperature_k':temperature,'mesh':list(mesh)}
    atomic_json(workdir/'thermal-progress.json',progress)
    emit(workdir,'thermal',f'Transport requires {len(supercells)} displacements; budget {max_displacements}')
    if len(supercells)>max_displacements:
        progress.update(status='budget_exceeded',reason='Required displacements exceed configured budget')
        atomic_json(workdir/'thermal-progress.json',progress)
        return progress
    forces=[]
    for cell in supercells:
        displaced=Atoms(cell.symbols,cell=cell.cell,scaled_positions=cell.scaled_positions,pbc=True)
        displaced.calc=atoms.calc
        f=displaced.get_forces()
        if not np.isfinite(f).all(): raise ValueError('Nonfinite anharmonic forces')
        forces.append(f-f.mean(axis=0))
        if len(forces)==1 or len(forces)%25==0 or len(forces)==len(supercells):
            progress.update(status='running',completed_displacements=len(forces))
            atomic_json(workdir/'thermal-progress.json',progress)
            emit(workdir,'thermal',f'Anharmonic forces: {len(forces)} / {len(supercells)} displacements')
    ph3.forces=forces
    ph3.produce_fc3(symmetrize_fc3r=True)
    ph3.produce_fc2(symmetrize_fc2=True)
    ph3.mesh_numbers=list(mesh)
    ph3.init_phph_interaction()
    ph3.run_thermal_conductivity(temperatures=[temperature],is_isotope=True,is_LBTE=False)
    values=np.asarray(ph3.thermal_conductivity.kappa)[0,0]
    tensor=np.array([[values[0],values[5],values[4]],
                     [values[5],values[1],values[3]],
                     [values[4],values[3],values[2]]])
    if not np.isfinite(tensor).all() or np.linalg.eigvalsh(tensor).min()<=0:
        raise ValueError('Thermal tensor is nonfinite or nonpositive')
    np.savez_compressed(workdir/'thermal-force-constants.npz',fc2=ph3.fc2,fc3=ph3.fc3)
    result={'status':'computed_preliminary','tensor_w_mk':tensor.tolist(),
            'minimum_eigenvalue_w_mk':float(np.linalg.eigvalsh(tensor).min()),
            'temperature_k':temperature,'mesh':list(mesh),'supercell':[2,2,2],
            'displacement_angstrom':0.03,'displacements':len(forces),
            'method':'PET-MAD forces + phono3py 3-phonon RTA with isotopes',
            'phono3py_version':importlib.metadata.version('phono3py'),
            'convergence_established':False,'thin_film_effects_included':False}
    atomic_json(workdir/'thermal-progress.json',{**progress,**result,'completed_displacements':len(forces)})
    return result
