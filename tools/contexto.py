"""
contexto.py - Fase 2 del pipeline NutriLog

Consulta Firebase para armar el contexto que necesita la extraccion:
  - Siguiente comida_id disponible para cada fecha del lote
  - Historial de los ultimos 14 dias (suplementos, rachas)
  - Deteccion de posibles duplicados

Uso:
    python contexto.py
    python contexto.py --respaldo    (ademas baja una copia completa de la base)
"""

import json
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# --- Configuracion -----------------------------------------------------------

BASE_URL = "https://nutrilog-fernando-default-rtdb.firebaseio.com"
PROCESO = Path(r"C:\dev\nutrilog-proceso")
MANIFIESTO = PROCESO / "manifiesto.json"
CONTEXTO = PROCESO / "contexto.json"
RESPALDOS = PROCESO / "respaldos"

DIAS = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]

# --- Utilidades --------------------------------------------------------------


def get(ruta):
    """GET a Firebase. Devuelve el objeto decodificado o None si no existe."""
    url = f"{BASE_URL}/{ruta}.json"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"  [error] no se pudo leer {ruta}: {e}")
        return None


def dia_id(fecha):
    """'2026-09-04' -> 'vie04'"""
    d = datetime.strptime(fecha, "%Y-%m-%d")
    return f"{DIAS[d.weekday()]}{d.day:02d}"


def partes(fecha):
    """'2026-09-04' -> ('2026', '09', 'vie04')"""
    d = datetime.strptime(fecha, "%Y-%m-%d")
    return f"{d.year}", f"{d.month:02d}", dia_id(fecha)


def siguiente_id(anio, mes, did, comidas):
    """Devuelve el proximo comida_id libre siguiendo el patron {did}_c{n}."""
    n = 1
    existentes = set(comidas or {})
    while f"{did}_c{n}" in existentes:
        n += 1
    return f"{did}_c{n}"


# --- Proceso principal -------------------------------------------------------


def respaldo():
    RESPALDOS.mkdir(parents=True, exist_ok=True)
    print("Bajando respaldo completo...")
    datos = get("registros")
    if datos is None:
        print("  respaldo fallido")
        return
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = RESPALDOS / f"registros_{marca}.json"
    destino.write_text(
        json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  guardado en {destino}")


def main():
    if not MANIFIESTO.exists():
        print(f"No existe {MANIFIESTO}. Corre preparar.py primero.")
        return

    if "--respaldo" in sys.argv:
        respaldo()

    manifiesto = json.loads(MANIFIESTO.read_text(encoding="utf-8"))
    if not manifiesto:
        print("El manifiesto esta vacio.")
        return

    fechas = sorted({f["fecha"] for f in manifiesto})
    print(f"Fechas en el lote: {', '.join(fechas)}\n")

    # --- Estado de cada fecha del lote ---
    dias = {}
    for fecha in fechas:
        anio, mes, did = partes(fecha)
        comidas = get(f"registros/{anio}/{mes}/{did}/comidas") or {}

        horas = sorted(
            (cid, c.get("hora", "?"), c.get("titulo", ""))
            for cid, c in comidas.items()
        )
        dias[fecha] = {
            "dia_id": did,
            "path": f"registros/{anio}/{mes}/{did}/comidas",
            "comidas_existentes": len(comidas),
            "siguiente_comida_id": siguiente_id(anio, mes, did, comidas),
            "ya_registradas": [
                {"comida_id": cid, "hora": h, "titulo": t} for cid, h, t in horas
            ],
        }
        print(f"  {fecha} ({did}): {len(comidas)} comidas ya registradas"
              f"  ->  siguiente: {dias[fecha]['siguiente_comida_id']}")

    # --- Historial de 14 dias hacia atras desde la fecha mas antigua ---
    inicio = datetime.strptime(fechas[0], "%Y-%m-%d") - timedelta(days=14)
    meses = set()
    cursor = inicio
    fin = datetime.strptime(fechas[-1], "%Y-%m-%d")
    while cursor <= fin:
        meses.add((f"{cursor.year}", f"{cursor.month:02d}"))
        cursor += timedelta(days=1)

    print("\nLeyendo historial de 14 dias...")
    historial = []
    for anio, mes in sorted(meses):
        datos = get(f"registros/{anio}/{mes}") or {}
        for did, dia in datos.items():
            for cid, c in (dia.get("comidas") or {}).items():
                tags = c.get("tags") or {}
                historial.append({
                    "dia_id": did,
                    "comida_id": cid,
                    "hora": c.get("hora"),
                    "titulo": c.get("titulo"),
                    "suplementos": tags.get("suplementos") or [],
                })

    # --- Resumen de suplementos ---
    suplementos = {}
    for h in historial:
        for s in h["suplementos"]:
            suplementos.setdefault(s, []).append(h["dia_id"])

    resumen = {
        s: {"veces": len(d), "dias": sorted(set(d))[-5:]}
        for s, d in sorted(suplementos.items())
    }

    contexto = {
        "generado": datetime.now().isoformat(timespec="seconds"),
        "dias_del_lote": dias,
        "suplementos_recientes": resumen,
        "total_comidas_periodo": len(historial),
    }

    CONTEXTO.write_text(
        json.dumps(contexto, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\nComidas en el periodo: {len(historial)}")
    if resumen:
        print("Suplementos registrados:")
        for s, d in resumen.items():
            print(f"  {s}: {d['veces']} veces")
    else:
        print("Sin suplementos en el periodo.")
    print(f"\nContexto: {CONTEXTO}")


if __name__ == "__main__":
    main()
