"""Servidor HTTP local para Archivo de Estancias.

Sirve los archivos estaticos del proyecto (index.html, JSON, etc.) igual que
`python -m http.server`, y ademas acepta POST a /alojamientos-martincho.json
para que la propia app pueda guardar en disco los cambios hechos desde la UI
(altas, ediciones, borrados, importaciones).
"""

import http.server
import json
import os
import socketserver

PORT = 8000
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(ROOT, "alojamientos-martincho.json")
MAX_RECORDS_DROP = 3  # protección: no permitir que un POST borre de golpe mas estancias que esto


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
