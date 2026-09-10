"""
preparar.py - Fase 1 del pipeline NutriLog

Detecta fotos nuevas en la carpeta de Drive, extrae fecha y hora del EXIF,
genera copias reducidas y produce un manifiesto para la fase de lectura.

Uso:
    python preparar.py
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

# --- Configuracion -----------------------------------------------------------

ENTRADA = Path(r"C:\GoogleDrive\NutriLog-Fotos")
PROCESO = Path(r"C:\dev\nutrilog-proceso")
REDUCIDAS = PROCESO / "reducidas"
MANIFIESTO = PROCESO / "manifiesto.json"
REGISTRO = PROCESO / "procesadas.json"

ANCHO_MAX = 1000
EXTENSIONES = {".jpg", ".jpeg", ".png"}

# --- Utilidades --------------------------------------------------------------


def cargar_registro():
    """Devuelve el conjunto de archivos ya procesados en corridas anteriores."""
    if REGISTRO.exists():
        return set(json.loads(REGISTRO.read_text(encoding="utf-8")))
    return set()


def guardar_registro(procesadas):
    REGISTRO.write_text(
        json.dumps(sorted(procesadas), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def leer_fecha_exif(ruta):
    """
    Extrae la fecha y hora de captura del EXIF.
    Devuelve (fecha, hora, fuente) donde fuente indica de donde salio el dato.
    """
    try:
        with Image.open(ruta) as im:
            exif = im.getexif()
            # 36867 = DateTimeOriginal, 306 = DateTime
            crudo = exif.get(36867) or exif.get(306)
            if crudo:
                dt = datetime.strptime(crudo, "%Y:%m:%d %H:%M:%S")
                return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M"), "exif"
    except Exception:
        pass

    # Sin EXIF: usamos la fecha de modificacion del archivo y lo marcamos
    dt = datetime.fromtimestamp(ruta.stat().st_mtime)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M"), "archivo"


def reducir(origen, destino):
    """Genera una copia con ANCHO_MAX de ancho, conservando proporcion."""
    with Image.open(origen) as im:
        im = im.convert("RGB")
        if im.width > ANCHO_MAX:
            alto = int(im.height * ANCHO_MAX / im.width)
            im = im.resize((ANCHO_MAX, alto), Image.LANCZOS)
        im.save(destino, "JPEG", quality=85)


# --- Proceso principal -------------------------------------------------------


def main():
    if not ENTRADA.exists():
        print(f"No existe la carpeta de entrada: {ENTRADA}")
        sys.exit(1)

    REDUCIDAS.mkdir(parents=True, exist_ok=True)

    procesadas = cargar_registro()
    fotos = sorted(
        p for p in ENTRADA.iterdir()
        if p.is_file() and p.suffix.lower() in EXTENSIONES
    )

    nuevas = [p for p in fotos if p.name not in procesadas]

    if not nuevas:
        print(f"Sin fotos nuevas. Ya procesadas: {len(procesadas)}")
        return

    print(f"Fotos nuevas detectadas: {len(nuevas)}\n")

    manifiesto = []
    sin_exif = 0

    for foto in nuevas:
        if foto.stat().st_size == 0:
            print(f"  [omitida] {foto.name} pesa 0 bytes (revisa Drive)")
            continue

        fecha, hora, fuente = leer_fecha_exif(foto)
        if fuente == "archivo":
            sin_exif += 1

        destino = REDUCIDAS / f"{foto.stem}.jpg"
        try:
            reducir(foto, destino)
        except Exception as e:
            print(f"  [error] {foto.name}: {e}")
            continue

        manifiesto.append({
            "archivo": foto.name,
            "reducida": str(destino),
            "fecha": fecha,
            "hora": hora,
            "fuente_fecha": fuente,
        })

        marca = "" if fuente == "exif" else "  <- sin EXIF"
        print(f"  {foto.name}  ->  {fecha} {hora}{marca}")
        procesadas.add(foto.name)

    manifiesto.sort(key=lambda x: (x["fecha"], x["hora"]))
    MANIFIESTO.write_text(
        json.dumps(manifiesto, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    guardar_registro(procesadas)

    print(f"\nListas: {len(manifiesto)}")
    if sin_exif:
        print(f"Sin EXIF (fecha aproximada): {sin_exif}")
    print(f"Manifiesto: {MANIFIESTO}")


if __name__ == "__main__":
    main()
