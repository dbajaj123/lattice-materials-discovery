import json
import math
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError
from pymatgen.core import Lattice, Structure

from mdb_harness.engine import Engine
from mdb_harness.novelty import StructureRegistry
from mdb_harness.release import assignment, hypervolume
from mdb_harness.schema import Crystal, PhysicsResult, Proposal, SynthesisStep, physics_gates, synthesis_checks


def diamond():
    return Structure.from_spacegroup('Fd-3m', Lattice.cubic(3.57), ['C'], [[0, 0, 0]])


def proposal():
    return Proposal(name='Known diamond control', hypothesis='Known diamond is a simulator control, not a discovery.',
                    crystal=Crystal.from_structure(diamond()))


def test_supercell_and_permutation_do_not_earn_credit():
    registry = StructureRegistry()
    s = diamond()
    assert registry.register('first', s) is None
    supercell = s * [2, 1, 1]
    supercell.translate_sites(range(len(supercell)), [0.17, 0.23, 0.31])
    assert registry.register('bigger', Structure.from_sites(list(reversed(supercell)))) == 'first'


def test_distinct_phases_not_collapsed_by_formula():
    registry = StructureRegistry()
    assert registry.register('diamond', diamond()) is None
    graphite = Structure(Lattice.hexagonal(2.46, 6.7), ['C'] * 4,
                         [[0,0,0], [1/3,2/3,0], [0,0,.5], [2/3,1/3,.5]])
    assert registry.register('graphite', graphite) is None


@pytest.mark.parametrize('field,value', [('kappa_w_mk',500), ('novel',True), ('eligible',True)])
def test_agent_cannot_submit_scores(field,value):
    p = proposal().model_dump(); p[field]=value
    with pytest.raises(ValidationError):
        Proposal.model_validate(p)


def test_nonfinite_and_overlap_rejected():
    p = proposal().crystal.model_dump(); p['lattice'][0][0] = math.nan
    with pytest.raises(ValidationError):
        Crystal.model_validate(p)
    with pytest.raises(ValidationError):
        Crystal(lattice=np.eye(3).tolist(), species=['C','C'], frac_coords=[[0,0,0],[0,0,0]])


def test_infinity_epsilon_never_fills_static():
    result = PhysicsResult(status='partial', backend='test', input_digest='x', converged=True,
                           minimum_phonon_thz=0, youngs_gpa=100, shear_gpa=50, kappa_w_mk=100, epsilon_infinity=4)
    gates = {g.name:g.status for g in physics_gates(result)}
    assert gates['static_dielectric']=='unknown'


def test_property_boundaries_are_explicit():
    r = PhysicsResult(status='complete', backend='test', input_digest='x', converged=True,
                      minimum_phonon_thz=-1, youngs_gpa=20, shear_gpa=6, kappa_w_mk=20, epsilon_static=10)
    g={x.name:x.status for x in physics_gates(r)}
    assert g['thermal_conductivity']=='fail' and g['static_dielectric']=='fail'
    assert g['youngs_modulus']=='pass' and g['dynamic_stability']=='unknown'


def test_recipe_completeness_never_means_plausible():
    p = proposal()
    p.synthesis = [SynthesisStep(operation='deposit',target_phase_or_state='diamond',temperature_c=401)]
    assert synthesis_checks(p)[0]['status']=='fail'
    p.synthesis[0].on_device_wafer=False
    assert synthesis_checks(p)[0]['status']=='unknown'


def test_hypervolume_ignores_dominated_and_duplicate_points():
    assert hypervolume([(1, .2), (.5, .6)]) == pytest.approx(.4)
    assert hypervolume([(1, .2), (.5, .6), (.1,.1), (.5,.6)]) == pytest.approx(.4)
    with pytest.raises(ValueError):
        hypervolume([(math.inf,1)])


def test_js_import_does_not_execute_expressions():
    assert assignment('window.X = [{"value": 1}];', 'X') == [{'value':1}]
    with pytest.raises(ValueError):
        assignment('window.X = dangerous();','X')
    with pytest.raises(ValueError):
        assignment('window.X = {} + dangerous();','X')


def test_unknowns_and_duplicates_cannot_pass(tmp_path):
    engine=Engine(tmp_path/'run',backend='none',max_screen_calls=3)
    first=engine.screen(proposal().model_dump())
    assert not first['eligible']
    assert all(x['status']=='unknown' for x in first['gates'])
    second=engine.screen(proposal().model_dump())
    assert second['duplicate_of']==first['candidate_id']
    engine.screen({'bad':'proposal'})
    assert 'budget' in engine.screen(proposal().model_dump())['error'].lower()
    assert engine.submit(first['candidate_id'])['eligible'] is False
    assert engine.submit(first['candidate_id'])['recorded'] is False
    assert engine.state()['eligible_count']==0


def test_existing_run_not_overwritten(tmp_path):
    Engine(tmp_path/'run')
    with pytest.raises(ValueError):
        Engine(tmp_path/'run')


def test_route_revision_reuses_physics_without_extra_credit(tmp_path):
    engine=Engine(tmp_path/'run',backend='none')
    result=engine.screen(proposal().model_dump())
    cid=result['candidate_id']
    step=SynthesisStep(operation='deposit',target_phase_or_state='diamond',temperature_c=350)
    for revision in range(1,4):
        response=engine.revise_synthesis(cid,[step.model_dump()],[])
        assert response['revision']==revision and not response['eligible']
    assert 'error' in engine.revise_synthesis(cid,[step.model_dump()],[])
    assert engine.screen_calls==1
    assert len(engine.results)==1


def test_snapshot_tampering_is_detected(tmp_path):
    import hashlib
    from mdb_harness.release import verify_snapshot
    data=b'original'
    (tmp_path/'x').write_bytes(data)
    (tmp_path/'manifest.json').write_text(json.dumps({'files':{'x':{'sha256':hashlib.sha256(data).hexdigest()}}}))
    verify_snapshot(tmp_path)
    (tmp_path/'x').write_bytes(b'changed')
    with pytest.raises(ValueError,match='checksum'):
        verify_snapshot(tmp_path)
