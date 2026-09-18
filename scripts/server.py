"""Servidor HTTP local para Archivo de Estancias.

Sirve los archivos estaticos del proyecto (index.html, JSON, etc.) igual que
`python -m http.server`, y ademas acepta POST a /alojamientos-martincho.json
para que la propia app pueda guardar en disco los cambios hechos desde la UI
(altas, ediciones, borrados, importaciones), y POST a /api/upload-photo para
guardar como archivo las fotos subidas desde el formulario en vez de
incrustarlas en base64 dentro del JSON.
"""

import base64
import http.server
import json
import os
import re
import socketserver

PORT = 8000
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(ROOT, "alojamientos-martincho.json")
PHOTOS_DIR = os.path.join(ROOT, "assets", "photos")
MAX_RECORDS_DROP = 3  # protección: no permitir que un POST borre de golpe mas estancias que esto
MAX_PHOTO_BYTES = 4 * 1024 * 1024
DATA_URL_RE = re.compile(r"^data:image/(png|jpeg|jpg|gif|webp);base64,(.+)$", re.DOTALL | re.IGNORECASE)


def _record_count(path):
    try:
        with open(path, encoding="utf-8") as file:
            return len(json.load(file).get("accommodations", []))
    except (OSError, ValueError):
        return None


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_POST(self):
        if self.path == "/api/upload-photo":
            self._handle_upload_photo()
            return
        if self.path != "/alojamientos-martincho.json":
            self.send_error(404, "Solo se puede escribir alojamientos-martincho.json")
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except ValueError as error:
            self.send_error(400, f"JSON invalido: {error}")
            return

        new_count = len(data.get("accommodations", []))
        current_count = _record_count(DATA_FILE)
        if current_count is not None and new_count < current_count - MAX_RECORDS_DROP:
            print(
                f"RECHAZADO: intento de guardar {new_count} estancias cuando el archivo tiene "
                f"{current_count} (diferencia > {MAX_RECORDS_DROP}). Posible pestaña con datos "
                "desactualizados. No se ha escrito nada."
            )
            self.send_error(
                409,
                f"El archivo tiene {current_count} estancias y se intentaba guardar solo {new_count}. "
                "Recarga la pagina (F5) antes de seguir editando para evitar perder datos.",
            )
            return

        with open(DATA_FILE, "w", encoding="utf-8", newline="\n") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        print(f"Guardado: {new_count} estancias (antes: {current_count}).")
        payload = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_upload_photo(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except ValueError as error:
            self.send_error(400, f"JSON invalido: {error}")
            return

        raw_filename = str(payload.get("filename") or "estancia")
        data_url = str(payload.get("dataUrl") or "")

        match = DATA_URL_RE.match(data_url)
        if not match:
            self.send_error(400, "dataUrl debe ser una imagen en base64 (png/jpeg/gif/webp)")
            return

        ext = match.group(1).lower()
        ext = "jpg" if ext == "jpeg" else ext
        try:
            raw = base64.b64decode(match.group(2))
        except ValueError as error:
            self.send_error(400, f"base64 invalido: {error}")
            return

        if len(raw) > MAX_PHOTO_BYTES:
            self.send_error(413, f"La foto supera {MAX_PHOTO_BYTES // (1024 * 1024)} MB")
            return

        safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw_filename).strip("-") or "estancia"
        filename = f"{safe_name}.{ext}"
        os.makedirs(PHOTOS_DIR, exist_ok=True)
        with open(os.path.join(PHOTOS_DIR, filename), "wb") as file:
            file.write(raw)

        relative_path = f"assets/photos/{filename}"
        print(f"Foto guardada: {relative_path} ({len(raw)} bytes).")
        response = json.dumps({"ok": True, "path": relative_path}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format_str, *args):
        if "GET" not in format_str % args:
            print(format_str % args)


if __name__ == "__main__":
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"Sirviendo {ROOT} en http://localhost:{PORT} (Ctrl+C para detener)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
