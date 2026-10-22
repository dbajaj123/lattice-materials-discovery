"""Evidence-grounded route critique. No calibrated synthesis probabilities."""
from .discovery_schema import RouteAssessment


def assess_route(route,review:RouteAssessment,store,max_wafer_c=400):
    criteria=[]; hard_failures=[]; steps=[]
    for i,step in enumerate(route.steps):
        citations=[store.validate_citation(c) for c in step.citations]
        judgment=next((s for s in review.step_assessments if s.step==i+1),None)
        review_checks=[store.validate_citation(c) for c in judgment.citations] if judgment else []
        step_status=judgment.status if judgment else 'unknown'
        if step_status=='supported' and (not review_checks or not all(c['valid'] for c in review_checks) or not any(c['full_text'] for c in review_checks)):
            step_status='unknown'
        conflicts=[]
        if step.on_device_wafer and step.temperature_c is not None and step.temperature_c>max_wafer_c:
            conflicts.append('On-wafer temperature exceeds configured thermal budget')
        missing=[name for name in ['phase_formation_mechanism','temperature_c','duration_minutes','equipment',
                                   'precursors','atmosphere','characterization','stop_or_failure_condition']
                 if getattr(step,name) in [None,'',[]]]
        if missing and step_status=='supported': step_status='unknown'
        steps.append({'step':i+1,'operation':step.operation,'status':'contradicted' if conflicts else step_status,
                      'review':judgment.model_dump() if judgment else None,'review_citation_checks':review_checks,
                      'missing_fields':missing,'conflicts':conflicts,'citation_checks':citations,
                      'evidence_level':'cited_full_text' if any(c['valid'] and c['full_text'] for c in citations) else 'unsupported_or_metadata_only'})
        hard_failures.extend(conflicts)
    for item in review.criteria:
        checks=[store.validate_citation(c) for c in item.citations]
        status=item.status
        if status=='supported' and (not checks or not all(c['valid'] for c in checks) or not any(c['full_text'] for c in checks)):
            status='unknown'
        if item.criterion=='thermal_budget' and hard_failures:
            status='contradicted'
        criteria.append({**item.model_dump(),'status':status,'citation_checks':checks})
    contradictions=sum(c['status']=='contradicted' for c in criteria)+sum(s['status']=='contradicted' for s in steps)+len(review.critical_issues)
    supported=sum(c['status']=='supported' for c in criteria)
    completeness_gaps=sum(len(s['missing_fields']) for s in steps)
    status='reject_or_revise' if contradictions else 'expert_review_candidate' if supported==len(criteria) and not completeness_gaps and all(s['status']=='supported' for s in steps) else 'insufficient_evidence'
    return {'route_name':route.name,'method':route.method,'status':status,'criteria':criteria,'steps':steps,
            'critical_issues':review.critical_issues+hard_failures,'next_experiment':review.next_experiment,
            'ranking_components':{'contradictions':contradictions,'supported_criteria':supported,'missing_step_fields':completeness_gaps},
            'certainty':'uncalibrated_model_review','human_review_required':True,
            'synthesis_success_probability':None,'experimentally_validated':False}
