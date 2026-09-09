"""
sembrar.py - Utilidad de siembra para probar la room Pendientes

No es parte del pipeline real: el pipeline externo (fuera de este repo) es
quien va a escribir en pipeline/pendientes de verdad. Esto es para poder
probar la room dentro de la app sin depender de que ese pipeline ya exista.

Toma un borrador (el JSON que produce tools/prompt-extraccion.md, por
defecto borrador2.json) y manifiesto.json, y escribe en Firebase:

    pipeline/pendientes/{id}   con el formato exacto que espera la room
    pipeline/imagenes/{id}     con las fotos en base64

{id} sale del nombre de la primera foto de cada comida, sin extensión
(ej: "20260904_131826.jpg" -> "20260904_131826").

Los "problemas" de validación se calculan reutilizando validar() de
revisar.py (mismo criterio, sin duplicar la lógica).

Uso:
    python sembrar.py                        (usa borrador2.json)
    python sembrar.py --borrador borrador.json
    python sembrar.py --limpiar               (borra pipeline/* y termina,
                                                 no siembra en la misma corrida)
"""

import base64
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from revisar import validar  # reutiliza la misma validación que revisar.py

BASE_URL = "https://nutrilog-fernando-default-rtdb.firebaseio.com"
PROCESO = Path(r"C:\dev\nutrilog-proceso")
MANIFIESTO = PROCESO / "manifiesto.json"

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


def main():
    if "--limpiar" in sys.argv:
        limpiar()
        return

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

    print(f"Sembrando {len(comidas)} comidas de {nombre} en pipeline/pendientes...\n")
    sembrados = 0
    for i, c in enumerate(comidas):
        fotos = c.get("fotos") or []
        if not fotos:
            print(f"  [saltada] comida {i + 1}: sin fotos")
            continue
        meta = por_archivo.get(fotos[0])
        if not meta:
            print(f"  [saltada] comida {i + 1}: {fotos[0]} no está en el manifiesto")
            continue

        id_ = Path(fotos[0]).stem

        pendiente = {
            "fecha": meta.get("fecha", ""),
            "hora": meta.get("hora", ""),
            "titulo": c.get("titulo", ""),
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
        print(f"  sembrado: {id_}  ({len(imagenes)} foto(s)) — {c.get('titulo', '')}")
        sembrados += 1

    print(f"\n{sembrados} pendientes sembrados en pipeline/pendientes.")


if __name__ == "__main__":
    main()
