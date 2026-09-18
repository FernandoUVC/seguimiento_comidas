"""
auditar_tags.py - Fase 2 del pipeline NutriLog (auditoria de posibles omisiones)

Compara los tags_cubierto de cada comida contra tools/tabla_nutrientes.json y
avisa cuando un alimento reconocido en la tabla no tiene su tag "auditar"
correspondiente en esa comida. Nunca agrega tags: solo avisa. Fernando decide
en la revision (room Pendientes o a mano).

Entrada, dos modos:
  - Por defecto: C:\\dev\\nutrilog-proceso\\borrador2.json (o --borrador <archivo>).
  - --respaldo <archivo>: un respaldo completo de registros/ (el que baja
    contexto.py --respaldo o aplicar.py antes de escribir), recorriendo
    {anio}/{mes}/{dia}/comidas. Admite --desde y --hasta (YYYY-MM-DD) sobre
    meta.fecha.

Uso:
    python auditar_tags.py
    python auditar_tags.py --borrador otro.json
    python auditar_tags.py --respaldo C:\\dev\\nutrilog-proceso\\respaldos\\registros_X.json
    python auditar_tags.py --respaldo <archivo> --desde 2026-08-23 --hasta 2026-09-10
    python auditar_tags.py --escribir-avisos      (solo con borrador2.json / --borrador, nunca con --respaldo)

Con --escribir-avisos agrega a cada comida del borrador el campo
posibles_omisiones: [{grupo, tags, palabra}, ...] (uno por cada palabra de la
tabla que matcheo en esa comida y dejo tags de "auditar" sin cubrir). Si la
comida queda sin avisos, el campo se omite. Nunca toca "tags"/tags_cubierto.
Antes de escribir guarda una copia <borrador>.bak.

Solo libreria estandar. Sin dependencias externas.
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from revisar import CATALOGO  # mismo catalogo de tags que usa la revision

HERRAMIENTAS = Path(__file__).resolve().parent
PROCESO = Path(r"C:\dev\nutrilog-proceso")
TABLA = HERRAMIENTAS / "tabla_nutrientes.json"


# --- Tabla de nutrientes ------------------------------------------------------


def cargar_tabla():
    datos = json.loads(TABLA.read_text(encoding="utf-8"))
    grupos = datos.get("grupos", {})
    grupos = {nombre: g for nombre, g in grupos.items() if not nombre.startswith("_")}

    validos = CATALOGO["cubierto"]
    for nombre, g in grupos.items():
        tags = set(g.get("cubierto") or []) | set(g.get("auditar") or [])
        faltan = tags - validos
        if faltan:
            print(f"  [aviso] grupo '{nombre}' tiene tags fuera del catalogo: {sorted(faltan)}")

    return grupos


_PATRONES = {}


def _patron(frase):
    p = _PATRONES.get(frase)
    if p is None:
        p = re.compile(r"\b" + re.escape(frase) + r"\b", re.IGNORECASE)
        _PATRONES[frase] = p
    return p


def contiene(texto, frase):
    """Coincidencia de 'frase' como palabra/frase completa dentro de 'texto'."""
    return _patron(frase).search(texto) is not None


# --- Normalizacion de alimentos ------------------------------------------------


def alimentos_planos(titulo, alimentos):
    """Devuelve una lista de alimentos individuales en minusculas.

    Soporta el formato actual (arreglo, un alimento por elemento) y el viejo
    (un solo string, o un arreglo con un unico elemento largo, con varios
    alimentos unidos por " + "). Si no hay alimentos, usa el titulo (que
    tambien puede traer " + ")."""
    al = alimentos
    if not al:
        al = [titulo or ""]
    if isinstance(al, str):
        al = [al]
    piezas = []
    for item in al:
        piezas.extend(p.strip() for p in str(item).split(" + ") if p.strip())
    return [p.lower() for p in piezas if p]


# --- Auditoria de una comida ---------------------------------------------------


def auditar_comida(titulo, alimentos, cubierto, grupos):
    """Devuelve (entradas, tags_unicos):
    - entradas: [{grupo, tags, palabra}] una por cada (grupo, palabra) que
      matcheo en la comida y dejo tags de 'auditar' sin cubrir.
    - tags_unicos: set de tags faltantes en la comida (un tag cuenta una vez
      aunque varias palabras/grupos lo disparen)."""
    piezas = alimentos_planos(titulo, alimentos)
    cubierto = set(cubierto or [])
    entradas = []

    for nombre_grupo, g in grupos.items():
        auditar = g.get("auditar") or []
        if not auditar:
            continue
        faltan = [t for t in auditar if t not in cubierto]
        if not faltan:
            continue

        palabras = g.get("palabras") or []
        excluir = g.get("excluir") or []
        encontradas = set()
        for pieza in piezas:
            if any(contiene(pieza, ex) for ex in excluir):
                continue
            for pal in palabras:
                if contiene(pieza, pal):
                    encontradas.add(pal)

        for pal in sorted(encontradas):
            entradas.append({"grupo": nombre_grupo, "tags": faltan, "palabra": pal})

    tags_unicos = sorted({t for e in entradas for t in e["tags"]})
    return entradas, tags_unicos


# --- Carga de comidas: borrador y respaldo -------------------------------------


def comidas_de_borrador(ruta):
    comidas = json.loads(ruta.read_text(encoding="utf-8"))
    filas = []
    for i, c in enumerate(comidas):
        etiqueta = f"{i + 1}. {c.get('titulo', '')}"
        filas.append((etiqueta, c.get("titulo", ""), c.get("alimentos"),
                      c.get("tags_cubierto") or []))
    return comidas, filas


def comidas_de_respaldo(ruta, desde, hasta):
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    filas = []
    for anio, meses in sorted((datos or {}).items()):
        for mes, dias in sorted((meses or {}).items()):
            for did, dia in sorted((dias or {}).items()):
                meta = dia.get("meta") or {}
                fecha = meta.get("fecha", "")
                if desde and fecha < desde:
                    continue
                if hasta and fecha > hasta:
                    continue
                comidas = dia.get("comidas") or {}
                for cid, c in sorted(comidas.items()):
                    tags = c.get("tags") or {}
                    etiqueta = f"{fecha} {did}/{cid}. {c.get('titulo', '')}"
                    filas.append((etiqueta, c.get("titulo", ""), c.get("alimentos"),
                                  tags.get("cubierto") or []))
    return filas


# --- Reporte --------------------------------------------------------------------


def procesar(filas, grupos):
    """filas: [(etiqueta, titulo, alimentos, cubierto)]. Devuelve lista paralela
    de (entradas, tags_unicos) e imprime el reporte."""
    resultados = []
    con_aviso = 0
    total_avisos = 0
    conteo_por_tag = {}

    for etiqueta, titulo, alimentos, cubierto in filas:
        entradas, tags_unicos = auditar_comida(titulo, alimentos, cubierto, grupos)
        resultados.append((entradas, tags_unicos))
        if tags_unicos:
            con_aviso += 1
            total_avisos += len(tags_unicos)
            for t in tags_unicos:
                conteo_por_tag[t] = conteo_por_tag.get(t, 0) + 1

            print(f"\n{etiqueta}")
            por_tag = {}
            for e in entradas:
                for t in e["tags"]:
                    por_tag.setdefault(t, set()).add(f"{e['grupo']}:{e['palabra']}")
            for t in tags_unicos:
                origenes = ", ".join(sorted(por_tag.get(t, [])))
                print(f"    - {t}  (por: {origenes})")

    print(f"\nComidas: {len(filas)}")
    print(f"Con aviso: {con_aviso}")
    print(f"Total de avisos: {total_avisos}")
    if conteo_por_tag:
        print("\nMas frecuentes:")
        for t, n in sorted(conteo_por_tag.items(), key=lambda x: (-x[1], x[0])):
            print(f"    {t}: {n}")

    return resultados


# --- Escritura de avisos (solo borrador) ----------------------------------------


def escribir_avisos(ruta, comidas, resultados):
    respaldo = ruta.with_suffix(ruta.suffix + ".bak")
    shutil.copy2(ruta, respaldo)
    print(f"\nRespaldo: {respaldo}")

    for c, (entradas, tags_unicos) in zip(comidas, resultados):
        if tags_unicos:
            c["posibles_omisiones"] = entradas
        else:
            c.pop("posibles_omisiones", None)

    # Escritura atomica: si el proceso muere a medio escribir, el .tmp queda
    # incompleto pero ruta nunca se toca hasta el os.replace() final.
    temporal = ruta.with_suffix(ruta.suffix + ".tmp")
    temporal.write_text(json.dumps(comidas, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporal, ruta)
    print(f"Avisos escritos en {ruta}")


# --- main -------------------------------------------------------------------------


def _valor(args, nombre):
    return args[args.index(nombre) + 1] if nombre in args else None


def main():
    args = sys.argv[1:]
    ruta_respaldo = _valor(args, "--respaldo")
    desde = _valor(args, "--desde")
    hasta = _valor(args, "--hasta")
    escribir = "--escribir-avisos" in args
    nombre_borrador = _valor(args, "--borrador") or "borrador2.json"

    grupos = cargar_tabla()
    print(f"Grupos en la tabla: {len(grupos)}")

    if ruta_respaldo:
        if escribir:
            print("--escribir-avisos no aplica con --respaldo (solo con borrador2.json).")
            sys.exit(1)
        ruta = Path(ruta_respaldo)
        if not ruta.exists():
            print(f"Falta {ruta}")
            sys.exit(1)
        filas = comidas_de_respaldo(ruta, desde, hasta)
        procesar(filas, grupos)
        return

    ruta = PROCESO / nombre_borrador
    if not ruta.exists():
        print(f"Falta {ruta}")
        sys.exit(1)

    comidas, filas = comidas_de_borrador(ruta)
    resultados = procesar(filas, grupos)

    if escribir:
        escribir_avisos(ruta, comidas, resultados)


if __name__ == "__main__":
    main()
