"""Restricted reference-set hull calculation, with strict energy provenance."""
from pymatgen.analysis.phase_diagram import PDEntry,PhaseDiagram
from pymatgen.core import Composition
import math


def reference_hull(candidate:dict,references:list[dict]):
    """Entries have formula, total_energy_ev, energy_model_sha256 and settings_sha256.

    The caller supplies evaluator-owned results, never LLM-estimated energies.
    Formula stoichiometry must correspond to the total-energy cell.
    """
    all_entries=[candidate]+references
    if any(not math.isfinite(x['total_energy_ev']) for x in all_entries):
        raise ValueError('Hull energies must be finite evaluator results')
    identities={(x['energy_model_sha256'],x['settings_sha256']) for x in all_entries}
    if len(identities)!=1 or not all(next(iter(identities))):
        raise ValueError('Candidate and references require identical energy model and settings; never mix ML and DFT energies')
    entries=[PDEntry(Composition(x['formula']),x['total_energy_ev']) for x in all_entries]
    system={e for e in entries[0].composition.elements}
    if any(not set(entry.composition.elements)<=system for entry in entries):
        raise ValueError('Reference contains elements outside candidate chemical system')
    phases=PhaseDiagram(entries)
    decomposition,above=phases.get_decomp_and_e_above_hull(entries[0])
    return {'energy_above_supplied_hull_ev_atom':float(above),
            'decomposition':{x.composition.reduced_formula:float(v) for x,v in decomposition.items()},
            'reference_phases':len(references),'reference_completeness':'not_established',
            'global_thermodynamic_stability_established':False,
            'energy_model_sha256':candidate['energy_model_sha256']}
