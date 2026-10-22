import json
import numpy as np
import pytest
from pydantic import ValidationError

from alloy_discovery.schema import Candidate, AgingStep, SimulationSettings, example_candidate, schedule
from alloy_discovery.grading import numerical_checks, discovery_status
from alloy_discovery.search import pareto_indices
from alloy_discovery.runner import run_id


def test_composition_units_and_balance_rejected():
    with pytest.raises(ValidationError):
        Candidate(name="percent accidentally supplied", composition_at_fraction={"AL":99.8,"SC":0.2}, steps=[AgingStep(temperature_c=350,duration_h=1)])
    with pytest.raises(ValidationError):
        Candidate(name="unbalanced", composition_at_fraction={"AL":0.99,"SC":0.002}, steps=[AgingStep(temperature_c=350,duration_h=1)])


def test_unknown_elements_and_nonfinite_inputs_rejected():
    for composition in [{"AL":0.998,"SC":0.001,"CU":0.001}, {"AL":float("nan"),"SC":0.001}]:
        with pytest.raises(ValidationError):
            Candidate(name="invalid", composition_at_fraction=composition, steps=[AgingStep(temperature_c=350,duration_h=1)])


def test_temperature_jump_requires_ramp():
    c = example_candidate().model_dump()
    c["steps"].append({"temperature_c":350,"duration_h":1})
    with pytest.raises(ValidationError):
        Candidate.model_validate(c)
    c["steps"][-1]["ramp_h"] = 0.1
    t,T,ends = schedule(Candidate.model_validate(c))
    assert t == [0,4,4.1,5.1]
    assert T == [673.15,673.15,623.15,623.15]
    assert ends == [4,5.1]


def test_cache_ignores_label_but_tracks_physical_changes():
    c = example_candidate()
    changed = c.model_copy(update={"name":"different label"})
    assert run_id(c,SimulationSettings()) == run_id(changed,SimulationSettings())
    assert run_id(c,SimulationSettings()) != run_id(c,SimulationSettings(gamma_j_m2=0.12))
    changed = Candidate.model_validate({**c.model_dump(),"composition_at_fraction":{"AL":0.999,"SC":0.001}})
    assert run_id(c,SimulationSettings()) != run_id(changed,SimulationSettings())


def numerical_fixture():
    return dict(time_s=np.array([0.,1.]), temperature_k=np.array([600.,600.]),
                composition=np.array([[0.002],[0.002]]), volume_fraction=np.zeros((2,1)),
                radius_m=np.zeros((2,1)), density_m3=np.zeros((2,1)),
                solute_in_precipitates=np.zeros((2,1,1)), initial_composition=[0.002],
                expected_end_s=1, psd=np.zeros(3))


@pytest.mark.parametrize("fault",["mass", "negative_population", "incomplete", "nan"])
def test_numerical_faults_cannot_pass(fault):
    args=numerical_fixture()
    assert numerical_checks(**args)["status"] == "pass"
    if fault == "mass": args["composition"][-1,0] = 0.001
    if fault == "negative_population": args["psd"][0] = -1
    if fault == "incomplete": args["expected_end_s"] = 2
    if fault == "nan": args["radius_m"][-1,0] = np.nan
    assert numerical_checks(**args)["status"] == "fail"


def test_numerical_pass_does_not_imply_material_discovery():
    r={"status":"completed", "numerical":{"status":"pass"}, "evidence":{}}
    assert discovery_status(r) == "screening_candidate_only"
    r["status"]="partial"
    assert discovery_status(r) == "not_eligible"


def test_pareto_excludes_failed_simulations():
    def row(strength,sc,h,status="completed"):
        return {"status":status,"numerical":{"status":"pass"},"metrics":{"final_strength_increment_mpa":strength,"sc_at_percent":sc,"processing_hours":h}}
    assert pareto_indices([row(100,.1,1),row(90,.2,2),row(120,.2,2),row(999,.01,.1,"failed")]) == [0,2]


def test_weight_atomic_conversion_and_precedent_bounds():
    from alloy_discovery.benchmark import weight_to_atomic_sc, atomic_to_weight_percent, synthesis_dossier
    x = weight_to_atomic_sc(.2)
    assert x == pytest.approx(.001201, rel=.001)
    c = {"AL":1-x,"SC":x}
    assert atomic_to_weight_percent(c)["SC"] == pytest.approx(.2)
    proposal = Candidate(name="in range",composition_at_fraction=c,steps=[AgingStep(temperature_c=350,duration_h=1)])
    assert synthesis_dossier(proposal)["status"] == "analogue_route_requires_validation"
    assert synthesis_dossier(example_candidate())["status"] == "outside_precedent_composition_range"


@pytest.mark.simulation
def test_actual_kawin_state_continuation():
    from alloy_discovery.simulator import evaluate
    split = Candidate(name="continuation test",composition_at_fraction={"AL":.998,"SC":.002},
                      steps=[AgingStep(name="first",temperature_c=400,duration_h=.25),AgingStep(name="second",temperature_c=400,duration_h=.25)])
    checkpoints = []
    result = evaluate(split, on_step=checkpoints.append)
    assert result["status"] == "completed"
    assert result["steps"][1]["start_density_m3"] > 0
    assert result["steps"][1]["start_radius_nm"] == pytest.approx(result["steps"][0]["end_radius_nm"])
    assert result["steps"][1]["start_h"] == pytest.approx(.25)
    assert result["steps"][1]["end_h"] == pytest.approx(.5)
    assert result["numerical"]["checks"]["internal_solute_balance"]
    assert result["discovery_status"] == "screening_candidate_only"
    assert len(checkpoints) == 2
    assert len(checkpoints[0]["completed_steps"]) == 1
    assert len(checkpoints[1]["completed_steps"]) == 2
    json.dumps(result,allow_nan=False)


@pytest.mark.simulation
def test_ternary_cannot_inherit_binary_strength():
    from alloy_discovery.simulator import evaluate
    c = Candidate(name="ternary",composition_at_fraction={"AL":.9985,"SC":.0005,"ZR":.001},
                  steps=[AgingStep(temperature_c=350,duration_h=4)])
    result = evaluate(c)
    assert result["status"] == "partial"
    assert result["metrics"] is None and result["trace"] is None
    assert result["numerical"]["status"] == "indeterminate"
    assert sum(result["equilibrium"]["points"][0]["phase_mole_fractions"].values()) == pytest.approx(1)
