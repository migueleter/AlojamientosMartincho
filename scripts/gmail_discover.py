"""Busca emails de confirmacion de Booking.com en Gmail y vuelca su texto a scripts/raw_emails/.

No interpreta ni extrae ningun dato de reserva todavia - solo sirve para confirmar que
la busqueda encuentra los correos correctos antes de escribir el parser.
"""

import base64
import glob
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from bs4 import BeautifulSoup
from googleapiclient.errors import HttpError

from gmail_auth import get_gmail_service

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "raw_emails")
QUERY = "from:(booking.com)"
MAX_RETRIES = 6


def call_with_retry(request):
    delay = 5
    for attempt in range(MAX_RETRIES):
        try:
            return request.execute()
        except HttpError as error:
            is_rate_limit = error.resp.status in (403, 429) and "rateLimitExceeded" in str(error)
            if not is_rate_limit or attempt == MAX_RETRIES - 1:
                raise
            print(f"  Limite de peticiones alcanzado, esperando {delay}s...")
            time.sleep(delay)
            delay = min(delay * 2, 60)


def extract_body(payload):
    """Devuelve el mejor texto disponible del mensaje (prefiere text/plain)."""
    plain = _find_part(payload, "text/plain")
    if plain:
        return plain
    html = _find_part(payload, "text/html")
    if html:
        return BeautifulSoup(html, "html.parser").get_text("\n")
    return ""


def _find_part(payload, mime_type):
    if payload.get("mimeType") == mime_type and payload.get("body", {}).get("data"):
        return _decode(payload["body"]["data"])
    for part in payload.get("parts", []) or []:
        found = _find_part(part, mime_type)
        if found:
            return found
    return None


def _decode(data):
    return base64.urlsafe_b64decode(data.encode("utf-8") + b"==").decode("utf-8", errors="replace")


def header(headers, name):
    for entry in headers:
        if entry.get("name", "").lower() == name.lower():
            return entry.get("value", "")
    return ""


def safe_filename(text):
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-")[:60]


def already_downloaded_ids():
    ids = set()
    for path in glob.glob(os.path.join(OUTPUT_DIR, "*.txt")):
        with open(path, "r", encoding="utf-8") as file:
            match = re.search(r"^ID: (\S+)$", file.read(), re.MULTILINE)
            if match:
                ids.add(match.group(1))
    return ids


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    service = get_gmail_service()

    message_ids = []
    request = service.users().messages().list(userId="me", q=QUERY, maxResults=500)
    while request is not None:
        response = call_with_retry(request)
        message_ids.extend(message["id"] for message in response.get("messages", []))
        request = service.users().messages().list_next(request, response)

    print(f"Encontrados {len(message_ids)} correos que coinciden con: {QUERY}")

    done = already_downloaded_ids()
    if done:
        print(f"Ya descargados previamente: {len(done)} (se omiten)")

    pending = [message_id for message_id in message_ids if message_id not in done]
    for index, message_id in enumerate(pending, start=1):
        get_request = service.users().messages().get(userId="me", id=message_id, format="full")
        full_message = call_with_retry(get_request)
        headers = full_message.get("payload", {}).get("headers", [])
        subject = header(headers, "Subject")
        date = header(headers, "Date")
        sender = header(headers, "From")
        body = extract_body(full_message.get("payload", {}))

        filename = f"{message_id}_{safe_filename(subject) or 'sin-asunto'}.txt"
        path = os.path.join(OUTPUT_DIR, filename)
        with open(path, "w", encoding="utf-8") as file:
            file.write(f"De: {sender}\nFecha: {date}\nAsunto: {subject}\nID: {message_id}\n\n{body}")

        print(f"[{index}/{len(pending)}] {subject!r} -> {filename}")
        time.sleep(0.3)

    print(f"\nListo. Revisa los .txt en {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
