"""
aplicar.py - Aplica las correcciones de pipeline/revisados a registros/

pipeline/revisados/{id} es lo que deja el botón "Corregir" de la room
Pendientes: el registro completo tal como estaba, más un campo `instruccion`
con lo que el usuario escribió a las carreras en el panel flotante. Aplicar
esa corrección con criterio requiere mirar la foto — no es un paso mecánico,
por eso este script se corre en tres tiempos:

    python aplicar.py --bajar
        Trae pipeline/revisados + sus fotos a disco. Solo lectura, no borra
        nada en Firebase todavía. Escribe:
          C:\\dev\\nutrilog-proceso\\revisados.json   (un objeto por pendiente)
          C:\\dev\\nutrilog-proceso\\revisados\\       (las fotos)

    (acá Claude Code lee revisados.json + las fotos, sigue las reglas de
     tools/prompt-aplicar.md, y escribe a mano:
       C:\\dev\\nutrilog-proceso\\corregidos.json)

    python aplicar.py --escribir
        Lee revisados.json + corregidos.json. Por cada id: baja un respaldo
        de registros/ antes de la PRIMERA escritura (si el respaldo falla,
        cancela todo); si el id ya no está en pipeline/revisados lo salta
        (ya se aplicó antes — idempotencia); si no, arma la comida igual que
        pendAprobar en index.html (sin confianza/dudas/problemas/fotos, tags
        sin claves vacías), la escribe en registros/{anio}/{mes}/{diaId}/
        comidas/{comidaId}, escribe meta si falta, y borra
        pipeline/revisados/{id} + pipeline/imagenes/{id}.

Aparte, sin relación con lo anterior:

    python aplicar.py --purgar-descartados [--forzar]
        pipeline/descartados es lo que deja "Quitar". No necesita que nadie
        mire fotos -esa decisión ya la tomó un humano- pero la imagen se
        conservó por si ese toque fue un error y hacía falta rescatarlo a
        mano, así que solo se purga lo que lleve 30 días o más (usa el campo
        quitado_en si existe; si no, aproxima con la fecha de la comida).
        --forzar ignora el umbral y purga todo.

Solo librería estándar. Reutiliza get/partes/siguiente_id/respaldo de
contexto.py y put/delete/tags_sin_vacios de subir.py.
"""

import base64
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contexto import get, partes, siguiente_id, respaldo
from subir import put, delete, tags_sin_vacios

PROCESO = Path(r"C:\dev\nutrilog-proceso")
REVISADOS_JSON = PROCESO / "revisados.json"
REVISADOS_DIR = PROCESO / "revisados"
CORREGIDOS_JSON = PROCESO / "corregidos.json"

DIAS_NOMBRE = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
MESES_NOMBRE = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

UMBRAL_DIAS_DESCARTE = 30


def normalizar_hora(h):
    """Puerto de normalizarHora() en index.html — mismo criterio exacto."""
    if not h:
        return ""
    h = h.strip().lower()
    if re.fullmatch(r"\d{1,2}:\d{2}", h):
        return h
    m = re.fullmatch(r"(\d{1,2}):(\d{2}):\d{2}", h)
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?\s*(a\.?m\.?|p\.?m\.?)", h)
    if m:
        hr, mn = int(m.group(1)), m.group(2)
        espm = m.group(3).replace(".", "") == "pm"
        if espm and hr != 12:
            hr += 12
        if not espm and hr == 12:
            hr = 0
        return f"{hr}:{mn}"
    return h


def escribir_meta_si_falta(anio, mes, dia_id, fecha):
    """Puerto del bloque de meta de guardarComidaEnFirebase() en index.html."""
    if get(f"registros/{anio}/{mes}/{dia_id}/meta"):
        return
    d = datetime.strptime(fecha, "%Y-%m-%d")
    etiqueta = f"{DIAS_NOMBRE[(d.weekday() + 1) % 7]} {d.day} de {MESES_NOMBRE[d.month - 1]}"
    put(f"registros/{anio}/{mes}/{dia_id}/meta", {
        "fecha": fecha, "dia_id": dia_id, "etiqueta": etiqueta, "resumen_dia": ""
    })


# --- --bajar -----------------------------------------------------------------


def bajar():
    REVISADOS_DIR.mkdir(parents=True, exist_ok=True)
    print("Bajando pipeline/revisados...")
    revisados = get("pipeline/revisados") or {}
    if not revisados:
        print("  no hay nada en pipeline/revisados.")
        return

    manifiesto = []
    for id_, r in revisados.items():
        entrada = dict(r)
        entrada["id"] = id_
        manifiesto.append(entrada)

        datos_img = get(f"pipeline/imagenes/{id_}") or {}
        imagenes = datos_img.get("imagenes") or []
        fotos = r.get("fotos") or []
        for i, b64 in enumerate(imagenes):
            nombre = fotos[i] if i < len(fotos) else f"{id_}_{i}.jpg"
            (REVISADOS_DIR / nombre).write_bytes(base64.b64decode(b64))

        print(f"  bajado: {id_}  ({len(imagenes)} foto(s)) - {r.get('titulo', '')}")

    manifiesto.sort(key=lambda e: (e.get("fecha", ""), e.get("hora", "")))
    REVISADOS_JSON.write_text(
        json.dumps(manifiesto, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n{len(manifiesto)} revisados bajados.")
    print(f"Manifiesto: {REVISADOS_JSON}")
    print(f"Fotos en:   {REVISADOS_DIR}")
    print("\nSiguiente paso: seguir tools/prompt-aplicar.md y escribir corregidos.json")


# --- --escribir ----------------------------------------------------------------


def escribir():
    if not REVISADOS_JSON.exists():
        print(f"Falta {REVISADOS_JSON}. Corre --bajar primero.")
        sys.exit(1)
    if not CORREGIDOS_JSON.exists():
        print(f"Falta {CORREGIDOS_JSON}. Hace falta revisar las fotos y escribirlo "
              f"primero (ver tools/prompt-aplicar.md).")
        sys.exit(1)

    manifiesto = json.loads(REVISADOS_JSON.read_text(encoding="utf-8"))
    correcciones = {c["id"]: c for c in json.loads(CORREGIDOS_JSON.read_text(encoding="utf-8"))}
    por_id = {e["id"]: e for e in manifiesto}

    faltantes = [id_ for id_ in correcciones if id_ not in por_id]
    if faltantes:
        print(f"Aviso: corregidos.json tiene ids que no están en revisados.json: {faltantes}")

    print("Bajando respaldo de registros/ antes de escribir...")
    if not respaldo():
        print("Respaldo fallido — cancelo. No se escribió nada.")
        sys.exit(1)
    print()

    n_escritos = n_saltados = 0

    for id_, entrada in por_id.items():
        corregido = correcciones.get(id_)
        if not corregido:
            print(f"  [sin corrección] {id_}: no está en corregidos.json, se salta")
            continue

        # Idempotencia: si ya no está en pipeline/revisados, una corrida
        # anterior de --escribir ya lo aplicó y borró.
        if get(f"pipeline/revisados/{id_}") is None:
            print(f"  [ya aplicado] {id_}")
            n_saltados += 1
            continue

        fecha = entrada.get("fecha", "")
        anio, mes, dia_id = partes(fecha)

        comidas = get(f"registros/{anio}/{mes}/{dia_id}/comidas") or {}
        comida_id = siguiente_id(anio, mes, dia_id, comidas)

        comida = {
            "titulo": corregido.get("titulo", ""),
            "hora": normalizar_hora(entrada.get("hora", "")),
            "icono": corregido.get("icono") or "🍽️",
            "alimentos": corregido.get("alimentos") or [],
            "tags": tags_sin_vacios(corregido),
            "nota": corregido.get("nota", ""),
        }

        put(f"registros/{anio}/{mes}/{dia_id}/comidas/{comida_id}", comida)
        escribir_meta_si_falta(anio, mes, dia_id, fecha)

        delete(f"pipeline/revisados/{id_}")
        delete(f"pipeline/imagenes/{id_}")

        print(f"  [escrito] {id_} -> registros/{anio}/{mes}/{dia_id}/comidas/{comida_id}"
              f"  ({corregido.get('titulo', '')})")
        n_escritos += 1

    print(f"\nEscritos: {n_escritos}   Ya aplicados: {n_saltados}")


# --- --purgar-descartados -------------------------------------------------------


def _antiguedad_dias(entrada):
    marca = entrada.get("quitado_en")
    ref = None
    if marca:
        try:
            ref = datetime.fromisoformat(marca.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            ref = None
    if ref is None:
        fecha = entrada.get("fecha")
        if not fecha:
            return 0  # sin ninguna referencia: se trata como "de hoy", no se purga por accidente
        ref = datetime.strptime(fecha, "%Y-%m-%d")
    return (datetime.now() - ref).days


def purgar_descartados(forzar=False):
    descartados = get("pipeline/descartados") or {}
    if not descartados:
        print("pipeline/descartados está vacío.")
        return

    print(f"{len(descartados)} en pipeline/descartados:\n")
    n_purgados = n_conservados = 0
    for id_, d in descartados.items():
        edad = _antiguedad_dias(d)
        titulo = d.get("titulo", "")
        cuando = f"{d.get('fecha', '')} {d.get('hora', '')}".strip()
        if forzar or edad >= UMBRAL_DIAS_DESCARTE:
            delete(f"pipeline/descartados/{id_}")
            delete(f"pipeline/imagenes/{id_}")
            print(f"  [purgado] {id_} ({edad} días) - {cuando} - {titulo}")
            n_purgados += 1
        else:
            faltan = UMBRAL_DIAS_DESCARTE - edad
            print(f"  [conservado] {id_} ({edad} días, faltan {faltan} para purgar) - {cuando} - {titulo}")
            n_conservados += 1

    print(f"\nPurgados: {n_purgados}   Conservados: {n_conservados}")


def main():
    if "--bajar" in sys.argv:
        bajar()
    elif "--escribir" in sys.argv:
        escribir()
    elif "--purgar-descartados" in sys.argv:
        purgar_descartados(forzar="--forzar" in sys.argv)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
