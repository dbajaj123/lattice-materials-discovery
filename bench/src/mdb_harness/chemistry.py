"""Composition checks with explicit limits for covalent and metallic bonding."""
from collections import Counter
import re

from pymatgen.core import Composition


def composition_audit(hypothesis):
    composition=hypothesis.crystal.structure().composition
    counts=Counter(hypothesis.crystal.species)
    # Restricted nominal model, not a universal oxidation-state assignment.
    charges={'B':3,'Al':3,'Si':4,'N':-3,'O':-2}
    applicable=bool(set(counts)&{'N','O'}) and set(counts)<=set(charges)
    residual=sum(charges[e]*n for e,n in counts.items()) if applicable else None
    discrepancies=[]
    labels=list(re.finditer(r'(?<![A-Za-z])(?:[A-Z][a-z]?\d*){2,}(?![A-Za-z])',hypothesis.name))
    parsed=[]
    for match in labels:
        try:
            parsed.append((match,Composition(match.group()).reduced_composition))
        except ValueError:pass
    has_actual=any(claimed==composition.reduced_composition for _,claimed in parsed)
    for match,claimed in parsed:
        if claimed==composition.reduced_composition:continue
        # A correctly named candidate may explicitly describe a different parent prototype.
        # Without a correct formula elsewhere, a mismatched "X-derived" label is still flagged.
        prototype=re.match(r'(?:[-–—]|\s)+(?:derived|based|type)\b',hypothesis.name[match.end():],re.I)
        if has_actual and prototype:continue
        discrepancies.append({'label_formula':match.group(),'actual_formula':composition.reduced_formula})
    return {'formula':composition.reduced_formula,'cell_composition':dict(counts),'label_discrepancies':discrepancies,
            'nominal_oxidation_states':{e:charges[e] for e in counts} if applicable else None,
            'nominal_charge_per_cell':residual,
            'charge_status':'not_applicable' if not applicable else 'nominally_balanced' if residual==0 else 'requires_bonding_justification',
            'interpretation':'Formal charge counting tests the proposed ionic/closed-shell rationale, not the existence of covalent, mixed-valent or metallic phases. Nonzero residual requires a justified bonding/electronic-structure calculation.',
            'electronic_validation':'not_computed'}


def hypothesis_preflight(hypothesis):
    audit=composition_audit(hypothesis)
    issues=[]
    if audit['label_discrepancies']:
        issues.append('Correct the formula in the name to match the submitted cell.')
    if audit['charge_status']=='requires_bonding_justification' and not getattr(hypothesis,'bonding_justification','').strip():
        issues.append('Nonzero nominal charge requires an explicit bonding_justification and electronic-structure test; a claim of charge balance alone is insufficient.')
    return {'status':'requires_revision' if issues else 'ready_for_screening','issues':issues,
            'scope':'Proposal consistency only; this does not prove phase stability or validate alternative bonding.'}


def property_status(physics,config=None):
    statuses={}
    artifacts=physics.get('artifacts',{})
    thermal=artifacts.get('thermal',{})
    requested=artifacts.get('requested_calculations',config or {})
    for key in ['youngs_gpa','shear_gpa','kappa_w_mk','epsilon_static','minimum_phonon_thz']:
        if physics.get(key) is not None:status='predicted'
        elif key=='epsilon_static':status='backend_not_configured'
        elif key=='kappa_w_mk' and requested.get('thermal') is False:status='disabled_by_configuration'
        elif key in ['youngs_gpa','shear_gpa'] and 'elastic_tensor_gpa' in artifacts:status='withheld_invalid_or_unconverged'
        elif key=='kappa_w_mk' and (physics.get('minimum_phonon_thz') or 0)<-1:status='withheld_dynamic_instability'
        elif key=='kappa_w_mk' and thermal.get('status'):status=thermal['status']
        elif physics.get('relaxed') and not physics.get('converged'):status='withheld_relaxation_unconverged'
        elif artifacts.get('worker_status') in ['timeout','failed']:status='worker_'+artifacts['worker_status']
        else:status='not_calculated_or_incomplete'
        statuses[key]=status
    return statuses
