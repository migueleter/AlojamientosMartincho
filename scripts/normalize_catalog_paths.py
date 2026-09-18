"""Convert local photo URLs back to portable assets/photos paths."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "alojamientos-martincho.json"


def normalize_photo(value: str) -> str:
    text = str(value or "").replace("\\", "/")
    if text.startswith("assets/photos/"):
        return text
    parts = urlsplit(text)
    path = unquote(parts.path or text)
    marker = "/assets/photos/"
    if marker in path:
        return "assets/photos/" + path.split(marker, 1)[1]
    return text


def normalize_catalog() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    for record in catalog.get("accommodations", []):
        record["photo"] = normalize_photo(record.get("photo", ""))
    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"records": len(catalog.get("accommodations", [])), "catalog": str(CATALOG_PATH)})


if __name__ == "__main__":
    normalize_catalog()
