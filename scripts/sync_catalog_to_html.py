"""Embed the sanitized master catalog into the standalone HTML application."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote_plus, parse_qsl, unquote, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "alojamientos-martincho.json"
HTML_PATH = ROOT / "index.html"


def public_url(value: str) -> str:
    if not value:
        return ""
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return ""
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    host = parts.netloc.lower().split(":", 1)[0]
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if host == "secure.booking.com" or "pincode" in query or "bn" in query:
        return ""
    if host in {"google.com", "www.google.com", "deals.vio.com", "www.vio.com"}:
        return ""
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def local_photo_path(value: str) -> str:
    text = str(value or "").replace("\\", "/")
    if text.startswith("assets/photos/"):
        return text
    parts = urlsplit(text)
    path = unquote(parts.path or text)
    marker = "/assets/photos/"
    return "assets/photos/" + path.split(marker, 1)[1] if marker in path else text


def booking_search_url(record: dict) -> str:
    parts = [record.get("name", ""), record.get("locality", ""), record.get("province", ""), record.get("country", "")]
    query = ", ".join(part.strip() for part in parts if part and part.strip())
    return "https://www.booking.com/searchresults.html?ss=" + quote_plus(query)


def visible_record(record: dict) -> dict:
    url = public_url(record.get("url", ""))
    fallback = public_url(record.get("fallbackUrl", ""))
    platform = str(record.get("platform", "")).strip()
    if not url and not fallback and platform.lower() == "booking":
        fallback = booking_search_url(record)
    return {
        "id": record.get("id", ""),
        "date": record.get("date", ""),
        "endDate": record.get("endDate", ""),
        "name": record.get("name", ""),
        "locality": record.get("locality", ""),
        "province": record.get("province", ""),
        "country": record.get("country", ""),
        "amount": record.get("amount"),
        "currency": record.get("currency", "EUR"),
        "period": record.get("period", "total"),
        "photo": local_photo_path(record.get("photo", "")),
        "url": url,
        "fallbackUrl": fallback,
        "platform": platform,
    }


def sync() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    payload = {
        "version": catalog.get("version", 1),
        "accommodations": [visible_record(record) for record in catalog.get("accommodations", [])],
    }
    html = HTML_PATH.read_text(encoding="utf-8")
    pattern = re.compile(
        r'(<script\s+type="application/json"\s+id="seed-data">).*?(</script>)',
        re.IGNORECASE | re.DOTALL,
    )
    replacement = r'\1\n' + json.dumps(payload, ensure_ascii=False, indent=2) + r'\n  \2'
    updated, count = pattern.subn(replacement, html, count=1)
    if count != 1:
        raise SystemExit("No se encontró exactamente un bloque seed-data en index.html")
    HTML_PATH.write_text(updated, encoding="utf-8")
    print(json.dumps({"records": len(payload["accommodations"]), "html": str(HTML_PATH)}, ensure_ascii=False))


if __name__ == "__main__":
    sync()
