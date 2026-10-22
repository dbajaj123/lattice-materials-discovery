"""Explicit evaluator capabilities, not claims about candidate performance."""
from importlib.util import find_spec


def evaluator_capabilities():
    atomistic=all(find_spec(name) is not None for name in ['ase','pet_mad','phonopy'])
    thermal=atomistic and find_spec('phono3py') is not None
    return [
        {'property':'Structure, density and volume','status':'available','method':'pymatgen; PET-MAD / ASE relaxation',
         'limit':'Final geometry is only relaxed when the optimizer converges.'},
        {'property':'Energy, forces and residual stress','status':'available' if atomistic else 'dependencies_missing',
         'method':'PET-MAD','limit':'Model predictions; energy per atom is not formation energy or energy above hull.'},
        {'property':'Sampled phonons and dynamic stability','status':'available' if atomistic else 'dependencies_missing',
         'method':'PET-MAD forces + Phonopy','limit':'Finite mesh and supercell; no polar corrections or demonstrated convergence.'},
        {'property':'Elastic tensor, Young, shear and bulk moduli; Poisson ratio','status':'available' if atomistic else 'dependencies_missing',
         'method':'Finite strain with internal relaxation; Voigt–Reuss–Hill reduction',
         'limit':'Withheld for invalid stiffness or unconverged internal relaxation. Aggregate moduli are not film-direction properties.'},
        {'property':'Lattice thermal conductivity tensor at 300 K','status':'budget_limited' if thermal else 'dependencies_missing',
         'method':'PET-MAD forces + phono3py RTA','limit':'Must pass phonon screening and fit the displacement/time budget. Bulk preliminary estimate, not electrical conductivity.'},
        {'property':'Static and electronic dielectric tensors','status':'not_connected','method':'Requires an electronic-response evaluator such as DFT/DFPT',
         'limit':'Cannot be inferred from stiffness.'},
        {'property':'Band gap, electrical conductivity and carrier mobility','status':'not_connected','method':'Requires electronic-structure and appropriate transport calculations',
         'limit':'No candidate values are calculated by the present potential.'},
        {'property':'Thermodynamic stability against competing phases','status':'not_connected','method':'Requires reference-phase calculations using consistent energy settings',
         'limit':'A supplied-reference hull utility exists, but a complete reference-phase workflow is not connected.'},
    ]
