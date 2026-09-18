# Archivo de Estancias

Aplicación local para consultar el historial personal de alojamientos. La fuente de verdad es
`alojamientos-martincho.json`; `index.html` contiene una copia depurada dentro del bloque
`seed-data` para poder abrirlo directamente sin servidor.

## Estado actual

- 119 alojamientos en el catálogo maestro.
- 119 fotos verificadas descargadas a `assets/photos/`.
- Las tres búsquedas que inicialmente no tenían ficha directa se resolvieron por dirección pública
  o identificador de anuncio, sin reutilizar imágenes de otra propiedad.
- Los enlaces con `bn`, `pincode` y URLs de gestión de Booking han sido retirados del catálogo que
  consume el HTML.
- Cuando no existe una web oficial, Booking se enlaza mediante una búsqueda pública sin datos de
  reserva.
- El frontend usa la clave de almacenamiento `alojamientos-martincho-v2`, por lo que no reutiliza
  registros antiguos guardados bajo la versión anterior.

## Flujo de actualización

El catálogo se puede volver a enriquecer con:

```bash
python scripts/enrich_photos.py
python scripts/sync_catalog_to_html.py
```

`enrich_photos.py` usa únicamente nombre, localidad, provincia y país para buscar en Google Travel.
También reutiliza coincidencias exactas de fotos presentes en notas locales de Google Keep. Las
imágenes se guardan localmente, y el informe de fuentes se escribe en
`photo-enrichment-report.json`.

`sync_catalog_to_html.py` inserta en `index.html` solo los campos necesarios para la vista. No
embebe notas privadas, números de reserva, PINs, emails ni datos de pago.

## OAuth de Gmail

El pipeline opcional de Gmail usa exclusivamente el scope `gmail.readonly`. No se deben compartir
contraseñas, cookies ni códigos de acceso.

Las credenciales y el token se buscan fuera de la carpeta del proyecto, en:

```text
%LOCALAPPDATA%\AlojamientosMartincho\credentials.json
%LOCALAPPDATA%\AlojamientosMartincho\token.json
```

También se pueden indicar las rutas mediante `ALOJAMIENTOS_GMAIL_CREDENTIALS` y
`ALOJAMIENTOS_GMAIL_TOKEN`. El token anterior del proyecto fue revocado y retirado de la carpeta
sincronizada.

## Archivos relevantes

- `index.html`: aplicación autónoma con tabla, tarjetas, filtros, edición e importación/exportación.
- `alojamientos-martincho.json`: catálogo maestro de 119 registros.
- `assets/photos/`: fotos locales verificadas.
- `photo-enrichment-report.json`: fuente y resultado de cada intento de enriquecimiento.
- `scripts/enrich_photos.py`: descarga fotos públicas y sanea enlaces.
- `scripts/sync_catalog_to_html.py`: actualiza el seed del HTML.
- `scripts/gmail_auth.py`: autenticación OAuth de solo lectura con rutas privadas.
- `scripts/gmail_discover.py`: descarga local de correos de Booking cuando se autoriza Gmail.
- `scripts/gmail_to_json.py`: parser histórico de correos de Booking.
- `.gitignore`: excluye credenciales, correos crudos, Takeout y artefactos locales.

Los correos crudos y cualquier exportación de Gmail deben permanecer fuera de la aplicación web.
