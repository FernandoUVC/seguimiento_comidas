"""
subir.py - Fase 5 real del pipeline: sube pendientes a revisión

Reemplaza a sembrar.py (que era solo para sembrar datos de prueba en la room
Pendientes). Este es el paso real: toma lo que Claude Code generó a partir
de las fotos y lo deja en pipeline/pendientes para que se revise dentro de
NutriLog (room Pendientes: Aprobar / Corregir / Quitar). No escribe nunca en
registros/ directamente — esa escritura solo ocurre cuando un humano aprueba
en la app.

Seguridad:
  - Modo prueba por defecto: sin --subir solo muestra qué haría, no escribe
    nada (ni pipeline/*, ni subidos.json).
  - Idempotencia: C:\\dev\\nutrilog-proceso\\subidos.json lleva registro de
    los ids ya subidos alguna vez. Si un id ya está ahí, se salta.
  - Anti-duplicado: antes de subir, revisa si ya existe un registro real en
    registros/{anio}/{mes}/{diaId}/comidas a esa misma hora. Si lo hay, se
    salta y avisa (probablemente ya se registró esa comida por otro medio).

{id} sale del nombre de la primera foto de cada comida, sin extensión
(ej: "20260904_131826.jpg" -> "20260904_131826").

Uso:
    python subir.py                        (modo prueba, usa borrador2.json)
    python subir.py --subir                (sube de verdad)
    python subir.py --subir --borrador borrador.json
    python subir.py --limpiar              (borra pipeline/* y termina,
                                              no sube en la misma corrida)
"""

import base64
import json
import re
import sys
from datetime import datetime
from pathlib import Path
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from revisar import validar          # misma validación que revisar.py
from contexto import get, partes     # mismo GET y mismo cálculo de dia_id que contexto.py

BASE_URL = "https://nutrilog-fernando-default-rtdb.firebaseio.com"
PROCESO = Path(r"C:\dev\nutrilog-proceso")
MANIFIESTO = PROCESO / "manifiesto.json"
SUBIDOS = PROCESO / "subidos.json"

TAGS_CAMPOS = ["cubierto", "atencion", "contexto", "suplementos"]


def put(ruta, valor):
    url = f"{BASE_URL}/{ruta}.json"
    data = json.dumps(valor, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="PUT", headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def delete(ruta):
    url = f"{BASE_URL}/{ruta}.json"
    req = urllib.request.Request(url, method="DELETE")
    urllib.request.urlopen(req, timeout=30)


def limpiar():
    for ruta in ("pipeline/pendientes", "pipeline/imagenes", "pipeline/revisados", "pipeline/descartados"):
        print(f"Borrando {ruta}...")
        delete(ruta)
    print("Listo.")


def tags_sin_vacios(comida):
    # Mismo criterio que pendAprobar en index.html: no escribir claves de
    # tags vacías (los registros reales tampoco las tienen).
    tags = {}
    for campo in TAGS_CAMPOS:
        valores = comida.get(f"tags_{campo}") or []
        if valores:
            tags[campo] = valores
    return tags


def img_b64(ruta):
    return base64.b64encode(Path(ruta).read_bytes()).decode("ascii")


def cargar_subidos():
    if SUBIDOS.exists():
        return json.loads(SUBIDOS.read_text(encoding="utf-8"))
    return {}


def guardar_subidos(subidos):
    SUBIDOS.write_text(json.dumps(subidos, indent=2, ensure_ascii=False), encoding="utf-8")


def hhmm(h):
    """Reduce cualquier hora tipo 'HH:MM', 'H:MM am' etc. a (hora, minuto) para comparar."""
    if not h:
        return None
    m = re.match(r'^\s*(\d{1,2}):(\d{2})', str(h).strip().lower())
    if not m:
        return None
    return int(m.group(1)) % 24, int(m.group(2))


def buscar_duplicado(fecha, hora):
    """Si ya existe una comida real a esa fecha/hora, devuelve (comidaId, titulo). Si no, None."""
    objetivo = hhmm(hora)
    if not fecha or objetivo is None:
        return None
    anio, mes, dia_id = partes(fecha)
    comidas = get(f"registros/{anio}/{mes}/{dia_id}/comidas") or {}
    for cid, c in comidas.items():
        if hhmm(c.get("hora")) == objetivo:
            return cid, c.get("titulo", "")
    return None


def main():
    if "--limpiar" in sys.argv:
        limpiar()
        return

    modo_subir = "--subir" in sys.argv

    nombre = "borrador2.json"
    if "--borrador" in sys.argv:
        nombre = sys.argv[sys.argv.index("--borrador") + 1]

    borrador = PROCESO / nombre
    for f in (borrador, MANIFIESTO):
        if not f.exists():
            print(f"Falta {f}")
            return

    comidas = json.loads(borrador.read_text(encoding="utf-8"))
    manifiesto = json.loads(MANIFIESTO.read_text(encoding="utf-8"))
    por_archivo = {f["archivo"]: f for f in manifiesto}

    problemas, _ = validar(comidas, manifiesto)
    subidos = cargar_subidos()

    if modo_subir:
        print(f"Subiendo {len(comidas)} comidas de {nombre}...\n")
    else:
        print("MODO PRUEBA — no se escribe nada (ni pipeline/*, ni subidos.json).")
        print("Usa --subir para subir de verdad.\n")

    n_subidos = n_duplicados = n_ya_subidos = 0

    for i, c in enumerate(comidas):
        fotos = c.get("fotos") or []
        titulo = c.get("titulo", "")

        if not fotos:
            print(f"  [saltada] comida {i + 1}: sin fotos")
            continue
        meta = por_archivo.get(fotos[0])
        if not meta:
            print(f"  [saltada] comida {i + 1}: {fotos[0]} no está en el manifiesto")
            continue

        id_ = Path(fotos[0]).stem

        if id_ in subidos:
            print(f"  [ya subido] {id_} — {titulo}")
            n_ya_subidos += 1
            continue

        dup = buscar_duplicado(meta.get("fecha", ""), meta.get("hora", ""))
        if dup:
            cid, titulo_existente = dup
            print(f"  [posible duplicado] {id_} — ya existe '{cid}' (\"{titulo_existente}\") a esa hora, se salta")
            n_duplicados += 1
            continue

        if not modo_subir:
            print(f"  [subiría] {id_} — {titulo}")
            n_subidos += 1
            continue

        pendiente = {
            "fecha": meta.get("fecha", ""),
            "hora": meta.get("hora", ""),
            "titulo": titulo,
            "icono": c.get("icono", ""),
            "nota": c.get("nota", ""),
            "alimentos": c.get("alimentos") or [],
            "tags": tags_sin_vacios(c),
            "confianza": c.get("confianza", "media"),
            "dudas": c.get("dudas") or [],
            "problemas": problemas.get(i, []),
            "fotos": fotos,
        }

        imagenes = []
        for f in fotos:
            fm = por_archivo.get(f)
            if not fm:
                print(f"    [aviso] {f} no está en el manifiesto, se omite esa foto")
                continue
            imagenes.append(img_b64(fm["reducida"]))

        put(f"pipeline/pendientes/{id_}", pendiente)
        put(f"pipeline/imagenes/{id_}", {"imagenes": imagenes})

        subidos[id_] = {
            "fecha": meta.get("fecha", ""),
            "hora": meta.get("hora", ""),
            "titulo": titulo,
            "subido_en": datetime.now().isoformat(timespec="seconds"),
        }
        guardar_subidos(subidos)  # se guarda tras cada subida, no solo al final

        print(f"  [subido] {id_}  ({len(imagenes)} foto(s)) — {titulo}")
        n_subidos += 1

    verbo = "Subirían" if not modo_subir else "Subidos"
    print(f"\n{verbo}: {n_subidos}   Duplicados: {n_duplicados}   Ya subidos: {n_ya_subidos}")


if __name__ == "__main__":
    main()
