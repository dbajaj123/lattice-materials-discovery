"""Schemas for our own discovery campaign, independent of the upstream grader."""
from typing import Literal

from pydantic import Field, model_validator

from .schema import Crystal, StrictModel, SynthesisStep


class CampaignConfig(StrictModel):
    name: str = 'chip-dielectrics'
    objective: str = 'Find new crystalline chip dielectrics with useful heat transport and plausible fabrication routes.'
    model: str = 'openai/gpt-5.4'
    review_model: str | None = None
    critic_enabled: bool = True
    synthesis_enabled: bool = False
    search_strategy: Literal['evolution','sequential'] = 'evolution'
    population_size: int = Field(default=12,ge=2,le=50)
    reference_library: str | None = None
    literature_memory: str | None = None
    reference_seed_limit: int = Field(default=12,ge=0,le=30)
    allowed_elements: list[str] = Field(default_factory=lambda: ['B','C','N','Si','Al','O'])
    rounds: int = Field(default=2, ge=1, le=20)
    candidates_per_round: int = Field(default=2, ge=1, le=8)
    routes_per_candidate: int = Field(default=3, ge=2, le=5)
    max_model_calls: int = Field(default=24, ge=1, le=500)
    max_total_tokens: int = Field(default=120000, ge=1000)
    max_output_tokens: int = Field(default=6000, ge=500, le=32000)
    backend: Literal['none','petmad'] = 'petmad'
    simulation_timeout_seconds: int = Field(default=300, ge=5, le=7200)
    elastic: bool = True
    thermal: bool = False
    max_wafer_temperature_c: float = Field(default=400, ge=20, le=2000)
    kappa_min_w_mk: float = Field(default=20, gt=0)
    epsilon_static_max: float = Field(default=10, gt=1)
    network_enabled: bool = True
    papers_per_query: int = Field(default=5, ge=1, le=20)
    max_open_papers: int = Field(default=4, ge=0, le=20)
    database_page_limit: int = Field(default=25, ge=1, le=100)
    database_max_pages: int = Field(default=2, ge=1, le=20)
    literature_queries: list[str] = Field(default_factory=lambda: [
        'boron carbon nitride crystalline thin film deposition phase selection',
        'aluminum nitride low temperature deposition thermal conductivity dielectric',
        'silicon carbide thin film deposition dielectric thermal conductivity',
    ])
    literature_files: list[str] = Field(default_factory=list)
    seed_cif_files: list[str] = Field(default_factory=list)
    optimade_endpoints: dict[str,str] = Field(default_factory=lambda: {
        'oqmd':'https://www.oqmd.org/optimade/structures',
        'jarvis':'https://jarvis.nist.gov/optimade/jarvisdft/v1/structures/',
    })


class Citation(StrictModel):
    source_id: str
    chunk_id: str
    quote: str = Field(min_length=8, max_length=600)


class CandidateHypothesis(StrictModel):
    name: str
    hypothesis: str = Field(min_length=10)
    crystal: Crystal
    expected_advantage: str
    closest_known_material: str
    falsification_test: str
    citations: list[Citation] = Field(default_factory=list)
    parent_ids: list[str] = Field(default_factory=list,max_length=2)
    mutation_operator: Literal['explore','substitute','recombine','distort','change_prototype','repair'] = 'explore'
    parent_issues_addressed: list[str] = Field(default_factory=list)
    change_rationale: str = ''
    expected_tradeoffs: list[str] = Field(default_factory=list)
    predicted_mechanism: str = ''


class HypothesisBatch(StrictModel):
    candidates: list[CandidateHypothesis] = Field(min_length=1, max_length=8)
    reasoning_summary: str


class RouteStep(SynthesisStep):
    anticipated_competing_phases: list[str] = Field(default_factory=list)
    stop_or_failure_condition: str = ''
    citations: list[Citation] = Field(default_factory=list)


class SynthesisRoute(StrictModel):
    name: str
    method: str
    phase_selection_hypothesis: str
    steps: list[RouteStep] = Field(min_length=1, max_length=15)
    expected_failure_modes: list[str]
    required_equipment: list[str]
    unresolved_assumptions: list[str]


class RoutePortfolio(StrictModel):
    routes: list[SynthesisRoute] = Field(min_length=1, max_length=5)
    alternatives_not_supported: list[str] = Field(default_factory=list)


CRITERIA = ('phase_selection','precursor_chemistry','thermal_budget','equipment_compatibility',
            'kinetic_pathway','characterization')


class CriterionAssessment(StrictModel):
    criterion: Literal['phase_selection','precursor_chemistry','thermal_budget',
                       'equipment_compatibility','kinetic_pathway','characterization']
    status: Literal['supported','contradicted','unknown']
    explanation: str
    citations: list[Citation] = Field(default_factory=list)


class StepAssessment(StrictModel):
    step: int = Field(ge=1, le=15)
    status: Literal['supported','contradicted','unknown']
    explanation: str
    citations: list[Citation] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


class RouteAssessment(StrictModel):
    criteria: list[CriterionAssessment]
    step_assessments: list[StepAssessment] = Field(default_factory=list)
    critical_issues: list[str]
    next_experiment: str

    @model_validator(mode='after')
    def complete_criteria(self):
        names=[x.criterion for x in self.criteria]
        if sorted(names)!=sorted(CRITERIA):
            raise ValueError('Review must assess every criterion exactly once')
        indices=[s.step for s in self.step_assessments]
        if len(indices)!=len(set(indices)):
            raise ValueError('Each synthesis step may be assessed only once')
        return self


class CriticFinding(StrictModel):
    domain: Literal['physics','novelty','synthesis','evidence']
    severity: Literal['blocking','uncertain','informational']
    issue: str
    evidence_fields: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    recommended_test: str


class HypothesisCritique(StrictModel):
    recommendation: Literal['reject','repair','test_further']
    findings: list[CriticFinding]
    why_try_a_different_material: str
    suggested_changes: list[str]
    tradeoffs: list[str]
    next_discriminating_test: str
