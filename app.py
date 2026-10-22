import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full")


@app.cell
def _():
    import json
    from pathlib import Path
    import marimo as mo
    import plotly.graph_objects as go
    from alloy_discovery.report import flatten_results
    return Path, flatten_results, go, json, mo


@app.cell
def _(Path, mo):
    _campaigns = sorted(Path("runs").glob("*/campaign.json"))
    campaign_picker = mo.ui.dropdown({str(p): str(p) for p in _campaigns}, value=str(_campaigns[0]) if _campaigns else None, label="Campaign")
    mo.vstack([mo.md("# Alloy discovery\nReal simulation results, processing steps and unresolved evidence."), campaign_picker])
    return (campaign_picker,)


@app.cell
def _(Path, campaign_picker, flatten_results, json, mo):
    mo.stop(campaign_picker.value is None, mo.md("Run `alloy-discovery campaign` to create results."))
    campaign_data = json.loads(Path(campaign_picker.value).read_text())
    _cases = Path(campaign_picker.value).with_name("route-examples.json")
    if _cases.exists():
        campaign_data["route_examples"] = json.loads(_cases.read_text())
    results = flatten_results(campaign_data)
    options = {f"{i+1}. {r['candidate']['name']} · {r['method']}": i for i,r in enumerate(results)}
    candidate_picker = mo.ui.dropdown(options, value=next(iter(options)), label="Candidate")
    candidate_picker
    return candidate_picker, results


@app.cell
def _(candidate_picker, mo, results):
    result = results[candidate_picker.value]
    mo.vstack([mo.md(f"**Status:** {result['status']} · **Discovery:** {result['discovery_status']}"),
               mo.callout("Predicted precipitation strengthening is not total measured strength. Novelty, experimental calibration and the preparation of the initial state remain unresolved.", kind="warn"),
               mo.ui.table([{"element": e, "atomic_percent": 100*x} for e,x in result["candidate"]["composition_at_fraction"].items()])])
    return (result,)


@app.cell
def _(mo, result):
    trace = result.get("trace")
    mo.stop(trace is None, mo.md(result.get("next_action", result.get("error", "Kinetics unavailable"))))
    time_slider = mo.ui.slider(0, len(trace["time_h"])-1, value=len(trace["time_h"])-1, label="Simulation time index")
    time_slider
    return time_slider, trace


@app.cell
def _(go, mo, time_slider, trace):
    _idx = time_slider.value
    _figure = go.Figure()
    _figure.add_trace(go.Scatter(x=trace["time_h"], y=trace["strength_increment_mpa"], name="Precipitation contribution"))
    _figure.add_vline(x=trace["time_h"][_idx], line_dash="dot")
    _figure.update_layout(xaxis_title="Time (h)", yaxis_title="Modeled contribution (MPa)", template="plotly_dark")
    mo.vstack([mo.md(f"At **{trace['time_h'][_idx]:.3f} h**: mean radius **{trace['radius_nm'][_idx]:.2f} nm**, volume fraction **{100*trace['volume_fraction'][_idx]:.3f}%**."), mo.ui.plotly(_figure)])
    return


@app.cell
def _(mo, result):
    mo.vstack([mo.md("## Processing steps"), mo.ui.table(result.get("steps", [])),
               mo.md("## Evidence"), mo.ui.table([{"gate": k, **v} for k,v in result.get("evidence", {}).items()]),
               mo.md("## Restricted equilibrium assessment"), mo.json(result.get("equilibrium", {})),
               mo.accordion({"Provenance and warnings": mo.json({"provenance": result.get("provenance"), "warnings": result.get("warnings")})})])
    return


if __name__ == "__main__":
    app.run()
