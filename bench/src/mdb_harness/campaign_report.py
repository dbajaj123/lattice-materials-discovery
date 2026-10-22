"""Offline visual dossier for our campaign, separate from the benchmark release."""
import html
import json
from pathlib import Path

from plotly.offline import get_plotlyjs


def write_campaign_report(root:Path):
    root=Path(root)
    state=json.loads((root/'state.json').read_text())
    config=json.loads((root/'config.json').read_text())
    sources=json.loads((root/'sources.json').read_text()) if (root/'sources.json').exists() else []
    candidates=[json.loads(p.read_text()) for p in sorted((root/'candidates').glob('*/dossier.json'))]
    payload=json.dumps(candidates,allow_nan=False).replace('</','<\\/')
    source_rows=''.join(f'<li>{html.escape(s["title"])} <span class="muted">({html.escape(s["kind"])})</span> · {html.escape(s["url"])}</li>' for s in sources)
    report='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Discovery campaign</title><style>body{font:16px/1.6 system-ui;background:#f4f6fa;color:#13243c;margin:0}main{max-width:1180px;margin:auto;padding:32px}h1{font-size:36px;margin:8px 0}h2{margin-top:0}.muted{color:#5c6a7f}.panel,.card{background:white;border-radius:12px;padding:22px;margin:18px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px}.card{margin:0}.big{font-size:30px;font-weight:700}.notice{background:#fff0c7;padding:15px;border-radius:9px}.step{border-left:3px solid #85a5d4;padding:8px 16px;margin:12px 0}select{padding:12px;max-width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 system-ui}details{margin:12px 0}code{overflow-wrap:anywhere}</style><main>
<div class="muted">INDEPENDENT MATERIALS RESEARCH</div>'''
    report+=f'<h1>{html.escape(config["name"])}</h1><p>{html.escape(config["objective"])}</p>'
    report+=f'<div class="notice">Status: {html.escape(state["status"])}. Synthesis: {"enabled" if config.get("synthesis_enabled",True) else "paused"}. Outputs are computational hypotheses; no experimentally validated discovery is claimed.</div>'
    report+=f'<div class="grid" style="margin-top:20px"><div class="card"><div class="big">{len(sources)}</div>retrieved sources</div><div class="card"><div class="big">{len(candidates)}</div>candidate dossiers</div><div class="card"><div class="big">{sum(len(c["routes"]["routes"]) for c in candidates)}</div>proposed synthesis routes</div><div class="card"><div class="big">0</div>experimentally validated discoveries</div></div>'
    report+='''<section class="panel"><h2>Candidate explorer</h2><select id="candidate"></select><p id="empty"></p><p id="hypothesis"></p><div id="crystal" style="height:400px"></div><div id="properties" class="grid"></div><h3>Physics assessment and critic</h3><pre id="assessment"></pre><pre id="critic"></pre><h3>Unresolved evidence</h3><ul id="uncertainties"></ul><details><summary>Database novelty checks</summary><pre id="novelty"></pre></details></section>
<section class="panel"><h2>Alternative synthesis routes</h2><p class="muted">Assessments distinguish cited evidence, contradictions and unknowns. Model review is uncalibrated; route cards are proposals for expert review.</p><div id="routes"></div></section>'''
    report+='<section class="panel"><h2>Literature ledger</h2><ul>'+source_rows+'</ul></section>'
    report+='<script>'+get_plotlyjs()+'</script><script>const candidates='+payload+''';
const el=id=>document.getElementById(id);const text=(tag,value)=>{let x=document.createElement(tag);x.textContent=value;return x;};
for(const c of candidates){let o=document.createElement('option');o.value=c.id;o.textContent=c.id+' · '+c.hypothesis.name;el('candidate').append(o);}
function update(){if(!candidates.length){el('empty').textContent='Evidence preparation is available now. Candidate generation starts after the model key is configured and the campaign is run.';el('crystal').style.display='none';return;}
const c=candidates.find(x=>x.id===el('candidate').value);el('hypothesis').textContent=c.hypothesis.hypothesis;el('novelty').textContent=JSON.stringify(c.novelty,null,2);el('uncertainties').replaceChildren(...c.uncertainties.map(x=>text('li',x)));el('assessment').textContent=JSON.stringify(c.assessment||{status:'Legacy run; assessment unavailable'},null,2);el('critic').textContent=JSON.stringify(c.critic||{status:'Not available'},null,2);
const s=c.evaluated_crystal;const elements=[...new Set(s.species)];const traces=elements.map(symbol=>{const positions=s.species.flatMap((e,i)=>e===symbol?[[0,1,2].map(j=>s.frac_coords[i].reduce((v,f,k)=>v+(((f%1)+1)%1)*s.lattice[k][j],0))]:[]);return {type:'scatter3d',mode:'markers',name:symbol,x:positions.map(x=>x[0]),y:positions.map(x=>x[1]),z:positions.map(x=>x[2]),marker:{size:8}};});Plotly.newPlot('crystal',traces,{margin:{l:0,r:0,t:0,b:0},scene:{aspectmode:'data'}},{responsive:true});
el('properties').replaceChildren();for(const [key,label] of [['youngs_gpa','Young’s modulus (GPa)'],['shear_gpa','Shear modulus (GPa)'],['kappa_w_mk','Thermal conductivity (W/m K)'],['epsilon_static','Static dielectric constant']]){const card=text('div','');card.className='card';card.append(text('strong',label),text('p',c.physics[key]==null?'Not calculated':Number(c.physics[key]).toPrecision(4)));el('properties').append(card);}
el('routes').replaceChildren();for(const route of c.routes.routes){const assessment=c.route_assessments.find(x=>x.route_name===route.name);let card=text('div','');card.className='panel';card.append(text('h3',route.name+' · '+route.method),text('p','Assessment: '+(assessment?.status||'not reviewed')),text('p',route.phase_selection_hypothesis));for(const [i,step] of route.steps.entries()){let box=text('div','');box.className='step';box.append(text('strong',(i+1)+'. '+step.operation),text('p','Target: '+step.target_phase_or_state),text('p','Mechanism: '+(step.phase_formation_mechanism||'Unresolved')),text('p','Temperature: '+(step.temperature_c??'unspecified')+' °C · Duration: '+(step.duration_minutes??'unspecified')+' min'),text('p','Failure criterion: '+(step.stop_or_failure_condition||'Missing')));card.append(box);}let details=text('details','');details.append(text('summary','Evidence and review details'),text('pre',JSON.stringify(assessment,null,2)));card.append(details);el('routes').append(card);}}
el('candidate').addEventListener('change',update);update();</script></main></html>'''
    report=report.replace('</style>','li{overflow-wrap:anywhere}</style>')
    (root/'report.html').write_text(report)
