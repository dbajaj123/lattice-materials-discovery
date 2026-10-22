"""Cached bibliographic discovery; absence of results never implies novelty."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import requests

QUERIES = [
    'Al Sc Zr alloy precipitation synthesis aging',
    'aluminum scandium zirconium two stage aging precipitation strengthening',
    'Al Sc precipitation Bayesian optimization KWN',
]


def retrieve(root: Path, queries=None, rows=12):
    cache = Path(root)/"literature"
    cache.mkdir(parents=True, exist_ok=True)
    records = []
    for query in queries or QUERIES:
        path = cache/(hashlib.sha256(f"{query}:{rows}".encode()).hexdigest()[:20]+".json")
        record = json.loads(path.read_text()) if path.exists() else None
        if record is None or record.get("status") != "retrieved":
            record = {"provider": "Crossref", "query": query, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                      "coverage": "metadata search only; full text, patents and supplementary files not reviewed"}
            try:
                response = requests.get("https://api.crossref.org/works", params={"query.bibliographic": query, "rows": rows},
                                        headers={"User-Agent": "alloy-discovery/0.1 (research prototype)"}, timeout=30)
                response.raise_for_status()
                records_raw = response.json()["message"]["items"]
                record.update(status="retrieved", works=[{"doi": r.get("DOI"), "title": r.get("title", [""])[0],
                    "url": r.get("URL"), "published": r.get("published",{}).get("date-parts"),
                    "source_score": r.get("score"), "relevance_review": "pending"} for r in records_raw])
            except (requests.RequestException, ValueError, KeyError) as error:
                record.update(status="error", error=str(error), works=[])
            path.write_text(json.dumps(record, indent=2))
        records.append(record)
    return {"searches": records, "novelty_status": "unresolved",
            "next_action": "Review relevance, read methods and supplements, extract composition ranges with units, expand citations, and inspect patents. Metadata hits are not verified matches."}
