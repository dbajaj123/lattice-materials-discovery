"""Offline interactive views of actual cached simulator outputs."""
import json
from pathlib import Path


def flatten_results(campaign):
    rows = []
    for method, results in campaign.get("methods", {}).items():
        rows.extend(dict(r, method=method) for r in results)
    rows.extend(dict(r, method="route_case_study") for r in campaign.get("route_examples", []))
    rows.extend(dict(r, method="ternary_screen") for r in campaign.get("ternary_screens", []))
    return rows


def export_report(campaign_path, output):
    from plotly.offline import get_plotlyjs
    campaign_path, output = Path(campaign_path), Path(output)
    data = json.loads(campaign_path.read_text())
    sensitivity_path = campaign_path.parent / "sensitivity.json"
    if sensitivity_path.exists():
        data["sensitivity"] = json.loads(sensitivity_path.read_text())
    experimental_path = campaign_path.parent / "experimental-comparison.json"
    if experimental_path.exists():
        data["experimental_comparison"] = json.loads(experimental_path.read_text())
    route_path = campaign_path.parent / "synthesis-route.json"
    if route_path.exists():
        data["synthesis_route"] = json.loads(route_path.read_text())
    cases_path = campaign_path.parent / "route-examples.json"
    if cases_path.exists():
        data["route_examples"] = json.loads(cases_path.read_text())
    payload = json.dumps(data, allow_nan=False).replace("<", "\\u003c")
    template = Path(__file__).with_name("data")/"dashboard.html"
    html = template.read_text().replace("__PLOTLY_JS__", get_plotlyjs()).replace("__CAMPAIGN_JSON__", payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html)
