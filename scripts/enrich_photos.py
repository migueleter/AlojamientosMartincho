"""Enrich the local accommodation catalog with public photos and websites.

The only search input is the accommodation name plus locality/country. The
script never reads OAuth files or sends reservation identifiers to the search
engine. Photos are copied into assets/photos so the local HTML also works
without a network connection after enrichment.
"""

from __future__ import annotations

import glob
import hashlib
import html
import json
import mimetypes
import os
import re
import shutil
import time
import unicodedata
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "alojamientos-martincho.json"
PHOTO_DIR = ROOT / "assets" / "photos"
REPORT_PATH = ROOT / "photo-enrichment-report.json"
TAKEOUT_PATTERN = str(ROOT / "takeout-*" / "Takeout" / "Conservar")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "Chrome/131.0.0.0 Safari/537.36"
)
MAX_IMAGE_BYTES = 8 * 1024 * 1024
EXTRA_QUERIES = {
    "downtown apartment with private garden": [
        "Rua Eça de Queirós 19 Aveiro Portugal",
    ],
    "casa das musas": [
        "Rua das Musas 318 Porto Portugal",
    ],
    "hermoso apartamento cerca de foodhallen y vondelpark": [
        "Airbnb 5088242 Foodhallen Amsterdam",
    ],
}


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def safe_stem(value: str) -> str:
    stem = normalize(value).replace(" ", "-")
    return stem[:100] or "accommodation"


def request_bytes(url: str, referer: str = "https://www.google.com/") -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": referer,
        },
    )
    with urlopen(request, timeout=35) as response:
        return response.read(MAX_IMAGE_BYTES + 1)


def request_text(url: str) -> str:
    return request_bytes(url).decode("utf-8", "ignore")


def image_extension(data: bytes, content_type: str = "") -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    extension = mimetypes.guess_extension(content_type.split(";", 1)[0])
    return extension if extension in {".jpg", ".jpeg", ".png", ".gif", ".webp"} else ""


def attachment_index() -> list[dict]:
    """Index exact accommodation-name matches from local Google Keep notes."""

    notes: list[dict] = []
    for directory in glob.glob(TAKEOUT_PATTERN):
        directory_path = Path(directory)
        for note_path in directory_path.glob("*.json"):
            try:
                note = json.loads(note_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            labels = {label.get("name", "") for label in note.get("labels", [])}
            if "Viajes" not in labels:
                continue
            attachments = []
            for attachment in note.get("attachments", []) or []:
                path = directory_path / attachment.get("filePath", "")
                if path.is_file():
                    attachments.append(path)
            if not attachments:
                continue
            annotation_text = " ".join(
                " ".join(
                    [
                        annotation.get("title", ""),
                        annotation.get("description", ""),
                        annotation.get("url", ""),
                    ]
                )
                for annotation in note.get("annotations", []) or []
            )
            search_text = normalize(
                " ".join([note.get("title", ""), note.get("textContent", ""), annotation_text])
            )
            notes.append({"search": search_text, "attachments": attachments})
    return notes


def local_photo_for(record: dict, notes: list[dict]) -> Path | None:
    name = normalize(record.get("name", ""))
    if len(name) < 5:
        return None
    name_variants = [name, re.sub(r"\s+\d+$", "", name).strip()]
    for note in notes:
        if any(variant and variant in note["search"] for variant in name_variants):
            return note["attachments"][0]
    return None


def public_url(value: str) -> str:
    """Keep a public URL but remove tracking and reservation credentials."""

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
    if "airbnb." in host and "/rooms/" in parts.path:
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def google_travel_query(record: dict) -> str:
    parts = [record.get("name", ""), record.get("locality", ""), record.get("country", "")]
    return " ".join(part.strip() for part in parts if part and part.strip())


def google_travel_queries(record: dict) -> list[str]:
    name = record.get("name", "").strip()
    locality = record.get("locality", "").strip()
    province = record.get("province", "").strip()
    country = record.get("country", "").strip()
    simplified = re.sub(
        r"\s+(?:-\s*)?(?:all inclusive hotel|hotel|by marriott|anfitri[oó]n:.*)$",
        "",
        name,
        flags=re.IGNORECASE,
    ).strip(" ,-")
    candidates = [
        f"{name} {locality} {province} {country}",
        f"{simplified} {locality} {province} {country}",
        f"{simplified} {province} {country}",
        f"{simplified} {locality} {province} hotel",
        f"{simplified} {locality} {province} Airbnb",
    ]
    result = []
    for candidate in candidates:
        candidate = " ".join(candidate.split())
        if candidate and candidate not in result:
            result.append(candidate)
    for candidate in EXTRA_QUERIES.get(normalize(name), []):
        if candidate not in result:
            result.append(candidate)
    return result


def extract_google_result(page: str) -> tuple[str, str]:
    """Return the first public website and first main photo from Google Travel."""

    website = ""
    website_match = re.search(
        r'href="(https?://[^"<>]+)"[^>]{0,300}aria-label="Visit site for',
        page,
        re.IGNORECASE,
    )
    if website_match:
        website = public_url(html.unescape(website_match.group(1)))
        if website.startswith("https://www.google."):
            website = ""

    photo = ""
    photo_match = re.search(r'<img\b[^>]*alt="Photo 1"[^>]*>', page, re.IGNORECASE)
    if photo_match:
        tag = photo_match.group(0)
        candidates = []
        for attribute in ("srcset", "data-srcset", "src", "data-src"):
            match = re.search(rf'{attribute}="([^"]+)"', tag, re.IGNORECASE)
            if not match:
                continue
            candidates.extend(re.findall(r"https://lh[3456]\.googleusercontent\.com/[^\s,]+", match.group(1)))
        if candidates:
            photo = candidates[-1].replace("\\u003d", "=").replace("\\u0026", "&")
    return website, photo


def download_photo(url: str, stem: str) -> tuple[str, str]:
    if not url:
        return "", ""
    try:
        data = request_bytes(url)
    except (HTTPError, URLError, TimeoutError, OSError):
        return "", ""
    if not data or len(data) > MAX_IMAGE_BYTES:
        return "", ""
    extension = image_extension(data)
    if not extension:
        return "", ""
    target = PHOTO_DIR / f"{stem}{extension}"
    target.write_bytes(data)
    return f"assets/photos/{target.name}", hashlib.sha256(data).hexdigest()


def copy_local_photo(source: Path, stem: str) -> tuple[str, str]:
    try:
        data = source.read_bytes()
    except OSError:
        return "", ""
    extension = image_extension(data) or source.suffix.lower()
    if extension not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return "", ""
    target = PHOTO_DIR / f"{stem}{extension}"
    shutil.copy2(source, target)
    return f"assets/photos/{target.name}", hashlib.sha256(data).hexdigest()


def enrich() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    records = catalog.get("accommodations", [])
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    notes = attachment_index()
    report = []
    for index, record in enumerate(records, start=1):
        stem = safe_stem(record.get("id") or f"accommodation-{index}")
        result = {
            "id": record.get("id", ""),
            "name": record.get("name", ""),
            "source": "none",
            "query": "",
            "website": "",
            "photo": "",
            "sha256": "",
            "error": "",
        }

        record["url"] = public_url(record.get("url", ""))
        record["fallbackUrl"] = public_url(record.get("fallbackUrl", ""))
        if record.get("photo") and (ROOT / record["photo"]).is_file():
            result.update({"source": "existing", "photo": record["photo"]})
        local_source = local_photo_for(record, notes)
        if local_source and not record.get("photo"):
            photo, digest = copy_local_photo(local_source, stem)
            if photo:
                record["photo"] = photo
                result.update({"source": "google-keep", "photo": photo, "sha256": digest})

        if not record.get("photo"):
            queries = google_travel_queries(record)
            result["query"] = queries[0] if queries else ""
            for query in queries:
                try:
                    page_url = "https://www.google.com/travel/search?" + urlencode(
                        {"q": query, "hl": "en", "gl": "ES", "ucbcb": "1"}
                    )
                    page = request_text(page_url)
                    website, photo_url = extract_google_result(page)
                    if website and not record.get("url"):
                        record["url"] = website
                    if website:
                        result["website"] = website
                    photo, digest = download_photo(photo_url, stem)
                    if photo:
                        record["photo"] = photo
                        result.update({"source": "google-travel", "photo": photo, "sha256": digest, "query": query})
                        break
                except (HTTPError, URLError, TimeoutError, OSError) as error:
                    result["error"] = type(error).__name__
                time.sleep(0.35)
            if not record.get("photo") and not result["error"]:
                result["error"] = "No se encontró Photo 1"
        report.append(result)
        print(f"[{index}/{len(records)}] {record.get('name', '')}: {result['source']}")

    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = {}
    for item in report:
        counts[item["source"]] = counts.get(item["source"], 0) + 1
    print(json.dumps({"records": len(records), "sources": counts, "report": str(REPORT_PATH)}, ensure_ascii=False))


if __name__ == "__main__":
    enrich()
