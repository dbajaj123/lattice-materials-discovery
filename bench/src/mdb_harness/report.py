import html
import json
from pathlib import Path

import plotly.graph_objects as go

from .release import load_release


def create_report(snapshot: Path, audit: dict, output: Path):
    release = load_release(snapshot)
    fig = go.Figure()
    for model in release['models']:
        rows = [r for r in release['candidates'] if r['model'] == model['id']]
        fig.add_trace(go.Scatter(x=[r['epsInf'] for r in rows], y=[r['kappa'] for r in rows],
            mode='markers', name=model['name'], marker={'size': 8, 'opacity': 0.7, 'color': model['light']},
            text=[f"{html.escape(r['formula'])} · {r['id']}<br>Recipe: {release['grades']['byCandidate'].get(r['id'], 'missing')}<br>{r['provenance']}" for r in rows],
            hovertemplate='%{text}<br>Exported epsilon field: %{x}<br>κ: %{y} W/(m K)<extra></extra>'))
    fig.update_layout(template='plotly_white', height=510, xaxis_title='Exported epsInf field (meaning unresolved)',
                      yaxis_title='Reported κ, W/(m K)', yaxis_type='log', margin=dict(l=65,r=20,t=20,b=50))
    chart = fig.to_html(full_html=False, include_plotlyjs=True)
    table = ''.join('<tr>' + ''.join(f'<td>{html.escape(str(value))}</td>' for value in [
        m['model'], m['released_rows'], m['represented_runs'], m['verdict_counts'].get('attempt',0),
        m['verdict_counts'].get('unlikely',0), m['verdict_counts'].get('refuse',0)]) + '</tr>' for m in audit['models'])
    limitations = ''.join(f'<li>{html.escape(x)}</li>' for x in audit['limitations'])
    choices = ''.join(f'<option value="{r["id"]}">{html.escape(r["formula"])} · {r["id"]}</option>' for r in release['candidates'])
    payload = json.dumps({r['id']: {'formula':r['formula'], 'detail': release['details'].get(r['id']),
                                  'verdict': release['grades']['byCandidate'].get(r['id']),
                                  'duplicate_of': audit['duplicate_of'].get(r['id'])} for r in release['candidates']}).replace('</', '<\\/')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Material Discovery Bench · Local harness</title><style>
body{margin:0;background:#f4f6fa;color:#14233b;font:16px/1.6 system-ui}main{max-width:1180px;margin:auto;padding:32px}h1{font-size:34px;margin:8px 0}
.tag{color:#5a4a11;background:#fff1c2;border-radius:8px;padding:12px}.cards{display:flex;gap:16px;flex-wrap:wrap;margin:24px 0}.card{background:white;padding:20px 26px;border-radius:12px;flex:1;min-width:130px}.big{font-size:30px;font-weight:700}section{background:white;padding:24px;border-radius:12px;margin:20px 0}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}.scroll{overflow:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.7 system-ui}select{max-width:100%;padding:10px}a{color:#1754a8}.muted{color:#5d6b80}
</style><main><div class="muted">RELEASE AUDIT · INDEPENDENT HARNESS</div><h1>Material Discovery Bench</h1>
<div class="tag">Development data from the public release. No new discoveries or SOTA claim. Exact official evaluator unavailable.</div>'''
        + f'''<div class="cards"><div class="card"><div class="big">{audit['rows']}</div>released rows</div><div class="card"><div class="big">{audit['structural_groups'] if audit['structural_groups'] is not None else '—'}</div>structure groups at local tolerance</div><div class="card"><div class="big">{audit['verdict_counts'].get('attempt',0)}</div>published “would attempt” recipe</div><div class="card"><div class="big">0</div>new verified candidates here</div></div>
<section><h2>Released property predictions</h2><p class="muted">Click a model legend to filter; hover to inspect. These are published MLIP results, not calculations made by this harness.</p>{chart}</section>
<section><h2>Published synthesis outcomes</h2><div class="scroll"><table><thead><tr><th>Model</th><th>Rows</th><th>Represented runs</th><th>Attempt</th><th>Unlikely</th><th>Refuse</th></tr></thead><tbody>{table}</tbody></table></div></section>
<section><h2>Candidate and proposed route</h2><p class="muted">Historical agent-generated recipes are unvalidated research artifacts, not laboratory instructions.</p><select id="candidate">{choices}</select><p id="verdict"></p><div id="crystal" style="height:390px"></div><details><summary>Inspect historical recipe text</summary><pre id="recipe"></pre></details></section>
<section><h2>Comparison limits</h2><ul>{limitations}</ul><p>Source: <a href="https://discoveredmaterials.com/research/">current research page</a> · <a href="https://petmad.matforge.ai/bench/about.html">legacy methods</a></p></section>
<script>const rows={payload};
function update(){{const id=document.getElementById('candidate').value;const r=rows[id];document.getElementById('verdict').textContent='Published verdict: '+r.verdict+(r.duplicate_of?' · Local equivalent: '+r.duplicate_of:'');document.getElementById('recipe').textContent=r.detail?.recipe||'No recipe';const s=r.detail?.structure;if(!s){{Plotly.purge('crystal');return;}} const species=[...new Set(s.sites.map(x=>x.el))];const traces=species.map(el=>{{const atoms=s.sites.filter(x=>x.el===el).map(x=>[0,1,2].map(j=>x.f.reduce((v,f,i)=>v+f*s.lattice[i][j],0)));return {{type:'scatter3d',mode:'markers',name:el,x:atoms.map(a=>a[0]),y:atoms.map(a=>a[1]),z:atoms.map(a=>a[2]),marker:{{size:7}},hovertemplate:el+'<extra></extra>'}};}});Plotly.newPlot('crystal',traces,{{margin:{{l:0,r:0,b:0,t:0}},scene:{{aspectmode:'data',xaxis:{{title:'Å'}},yaxis:{{title:'Å'}},zaxis:{{title:'Å'}}}}}},{{responsive:true}});}} document.getElementById('candidate').addEventListener('change',update);update();</script></main></html>''')
