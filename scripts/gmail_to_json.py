"""Convierte los .txt de scripts/raw_emails/ (volcados por gmail_discover.py) en
alojamientos-booking.json, con el formato que index.html espera en "Importar reservas".

No usa la API de Gmail directamente - reutiliza los correos ya descargados en disco.
Los campos que no se puedan extraer con confianza se dejan vacios en vez de adivinar.
"""

import glob
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(SCRIPT_DIR, "raw_emails")
OUTPUT_PATH = os.path.join(os.path.dirname(SCRIPT_DIR), "alojamientos-booking.json")

MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

MODERN_SUBJECT_RE = re.compile(r"reserva en el (.+?) est[aá] confirmad", re.IGNORECASE)
MODERN_SUBJECT_ALT_RE = re.compile(r"casa en (.+?) est[aá] confirmad", re.IGNORECASE)
OLD_SUBJECT_RE = re.compile(r"^Tu reserva en el (.+)$")
CANCELLATION_SUBJECT_RE = re.compile(
    r"se ha cancelado la reserva|se cancel[oó] la reserva|confirmaci[oó]n de cancelaci[oó]n|"
    r"cancelaci[oó]n de su reserva",
    re.IGNORECASE,
)

ENTRADA_RE = re.compile(r"Entrada\D*?(\d{1,2} de \w+ de \d{4})")
SALIDA_RE = re.compile(r"Salida\D*?(\d{1,2} de \w+ de \d{4})")
PRECIO_TOTAL_RE = re.compile(r"Precio total\D*?€\s*([\d.,]+)")
CONFIRMACION_RE = re.compile(r"confirmaci[oó]n:?\s*(\d+)", re.IGNORECASE)
NUMERO_RESERVA_RE = re.compile(r"n[uú]mero de reserva:?\s*(\d+)", re.IGNORECASE)
UBICACION_RE = re.compile(r"Ubicaci[oó]n\s*\n+\s*(.+)")
DIRECCION_RE = re.compile(r"Direcci[oó]n:?\s*(.+)\n\s*(.+?),\s*(\S+)\s*\n\s*(.+)")

EXCLUSION_PHRASES = [
    "no te presentaste",
    "nos ha informado de que no",
    "ha cancelado",
    "se cancel",
]


def parse_email_date(text):
    match = re.search(r"(\d{1,2}) de (\w+) de (\d{4})", text)
    if not match:
        return None
    day, month_name, year = match.groups()
    month = MONTHS.get(month_name.lower())
    if not month:
        return None
    return f"{int(year):04d}-{month:02d}-{int(day):02d}"


def parse_amount(raw):
    raw = raw.strip()
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_modern_location(body):
    match = UBICACION_RE.search(body)
    if not match:
        return {"locality": "", "province": "", "country": ""}
    segments = [s.strip() for s in match.group(1).split(",") if s.strip()]
    if not segments:
        return {"locality": "", "province": "", "country": ""}
    country = segments[-1]
    locality = ""
    if len(segments) >= 2:
        candidate = segments[-2]
        combined = re.match(r"^[\d\-]+\s+(.+)$", candidate)
        if combined:
            locality = combined.group(1).strip()
        elif re.match(r"^[\d\-]+$", candidate):
            locality = segments[-3].strip() if len(segments) >= 3 else ""
        else:
            locality = candidate
    return {"locality": locality, "province": "", "country": country}


def parse_old_location(body):
    match = DIRECCION_RE.search(body)
    if not match:
        return {"locality": "", "province": "", "country": ""}
    _street, city, _postal, country = match.groups()
    return {"locality": city.strip(), "province": "", "country": country.strip()}


def read_email(path):
    with open(path, "r", encoding="utf-8") as file:
        content = file.read()
    header, _, body = content.partition("\n\n")
    subject_match = re.search(r"^Asunto: (.*)$", header, re.MULTILINE)
    subject = subject_match.group(1).strip() if subject_match else ""
    return subject, body


def build_record(name, body, location_fn):
    entrada = ENTRADA_RE.search(body)
    salida = SALIDA_RE.search(body)
    precio = PRECIO_TOTAL_RE.search(body)
    confirmacion = CONFIRMACION_RE.search(body) or NUMERO_RESERVA_RE.search(body)

    date = parse_email_date(entrada.group(1)) if entrada else None
    end_date = parse_email_date(salida.group(1)) if salida else None
    if not date or not end_date:
        return None

    record = {
        "date": date,
        "endDate": end_date,
        "name": name.strip(),
        "location": location_fn(body),
        "price": {},
        # Nunca se exportan números de reserva ni PINs. La conciliación usa
        # confirmation_number solo en memoria durante esta ejecución.
        "fallbackUrl": "",
        "platform": "Booking",
    }

    if precio:
        amount = parse_amount(precio.group(1))
        if amount is not None:
            record["price"] = {"amount": amount, "currency": "EUR", "period": "total"}

    confirmation_number = confirmacion.group(1) if confirmacion else None
    return record, confirmation_number


def classify_and_parse(subject, body):
    modern_match = MODERN_SUBJECT_RE.search(subject) or MODERN_SUBJECT_ALT_RE.search(subject)
    if modern_match:
        return build_record(modern_match.group(1), body, parse_modern_location)

    old_match = OLD_SUBJECT_RE.match(subject)
    if old_match:
        lowered = body.lower()
        if any(phrase in lowered for phrase in EXCLUSION_PHRASES):
            return None
        if "Número de reserva" not in body and "Numero de reserva" not in body:
            return None
        return build_record(old_match.group(1), body, parse_old_location)

    return None


def find_cancelled_confirmations(paths):
    cancelled = set()
    for path in paths:
        subject, body = read_email(path)
        if not CANCELLATION_SUBJECT_RE.search(subject):
            continue
        match = CONFIRMACION_RE.search(body) or NUMERO_RESERVA_RE.search(body)
        if match:
            cancelled.add(match.group(1))
    return cancelled


def main():
    paths = sorted(glob.glob(os.path.join(RAW_DIR, "*.txt")))
    print(f"Analizando {len(paths)} correos en {RAW_DIR}")

    cancelled_confirmations = find_cancelled_confirmations(paths)
    print(f"Reservas con aviso de cancelación detectado: {len(cancelled_confirmations)}")

    by_confirmation = {}
    unkeyed = []
    skipped_no_dates = 0
    skipped_cancelled = 0

    for path in paths:
        subject, body = read_email(path)
        result = classify_and_parse(subject, body)
        if result is None:
            continue
        record, confirmation_number = result
        if record is None:
            skipped_no_dates += 1
            continue
        if confirmation_number and confirmation_number in cancelled_confirmations:
            skipped_cancelled += 1
            continue
        if confirmation_number:
            by_confirmation[confirmation_number] = record
        else:
            unkeyed.append(record)

    accommodations = list(by_confirmation.values()) + unkeyed
    accommodations.sort(key=lambda item: item["date"])

    output = {"version": 1, "accommodations": accommodations}
    with open(OUTPUT_PATH, "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    print(f"Reservas confirmadas y vigentes: {len(accommodations)}")
    print(f"Descartadas por estar canceladas: {skipped_cancelled}")
    print(f"Descartadas por falta de fechas reconocibles: {skipped_no_dates}")
    print(f"Escrito: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
