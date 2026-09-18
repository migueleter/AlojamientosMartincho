"""Fill missing public websites for records whose platform is Web."""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlencode

from enrich_photos import extract_google_result, google_travel_queries, public_url, request_text


ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "alojamientos-martincho.json"
REPORT_PATH = ROOT / "web-link-enrichment-report.json"


def enrich() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    report = []
    for record in catalog.get("accommodations", []):
        platform = str(record.get("platform", ""))
        result = {
            "id": record.get("id", ""),
            "name": record.get("name", ""),
            "source": "existing" if record.get("url") else "none",
            "query": "",
            "url": public_url(record.get("url", "")),
            "error": "",
        }
        record["url"] = result["url"]
        if "web" not in platform.lower() or record["url"]:
            report.append(result)
            continue

        for query in google_travel_queries(record):
            result["query"] = query
            try:
                page_url = "https://www.google.com/travel/search?" + urlencode(
                    {"q": query, "hl": "en", "gl": "ES", "ucbcb": "1"}
                )
                website, _ = extract_google_result(request_text(page_url))
            except Exception as error:  # Network responses vary by public provider.
                result["error"] = type(error).__name__
                time.sleep(0.35)
                continue
            if website:
                record["url"] = public_url(website)
                result.update({"source": "google-travel", "url": record["url"]})
                break
            time.sleep(0.35)
        report.append(result)
        print(f"{record.get('name', '')}: {result['source']}")

    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "webRecords": sum("web" in str(r.get("platform", "")).lower() for r in catalog["accommodations"]),
        "webWithUrl": sum("web" in str(r.get("platform", "")).lower() and bool(r.get("url")) for r in catalog["accommodations"]),
        "report": str(REPORT_PATH),
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    enrich()
