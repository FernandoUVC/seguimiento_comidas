"""
orquestar.py - Orquestador del pipeline NutriLog

Cada corrida evalua dos ramas independientes y actua segun corresponda.
Ambas pueden ejecutarse en la misma corrida.

Rama 1 (fotos nuevas): si hay fotos sin procesar en la carpeta de Drive y la
mas reciente lleva 45+ min sin cambios (lote estable):
    preparar.py -> contexto.py -> claude -p (prompt-extraccion.md) -> subir.py --subir

Rama 2 (correcciones pendientes): si pipeline/revisados tiene algo:
    aplicar.py --bajar -> claude -p (prompt-aplicar.md) -> aplicar.py --escribir

Si un paso de una rama falla, esa rama se detiene ahi (queda registrado) y la
otra rama se evalua igual - una no bloquea a la otra.

Uso:
    python orquestar.py                      (modo prueba: dice que haria, no hace nada)
    python orquestar.py --ejecutar            (corre de verdad)
    python orquestar.py --solo-fotos          (fuerza solo la rama de fotos)
    python orquestar.py --solo-correcciones   (fuerza solo la rama de correcciones)

Bitacora con rotacion: C:\\dev\\nutrilog-proceso\\orquestador.log
Candado de una sola corrida a la vez: C:\\dev\\nutrilog-proceso\\orquestador.lock

Solo libreria estandar.
"""

import contextlib
import ctypes
import json
import logging
import logging.handlers
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contexto import get
from revisar import validar  # misma cobertura foto->comida que ya usa revisar.py
import preparar  # ENTRADA, EXTENSIONES, cargar_registro

HERRAMIENTAS = Path(__file__).resolve().parent
RAIZ_REPO = HERRAMIENTAS.parent
PROCESO = Path(r"C:\dev\nutrilog-proceso")
MANIFIESTO = PROCESO / "manifiesto.json"
BORRADOR = PROCESO / "borrador2.json"  # mismo default que subir.py
CORREGIDOS_JSON = PROCESO / "corregidos.json"
LOG_PATH = PROCESO / "orquestador.log"
LOCK_PATH = PROCESO / "orquestador.lock"

VENTANA_ESTABLE_MIN = 45
TIMEOUT_PASO = 5 * 60        # preparar/contexto/subir/aplicar como subprocess
TIMEOUT_CLAUDE = 15 * 60     # claude -p, lee fotos, puede tardar mas

DIR_ADD = str(PROCESO)


# --- Bitacora ----------------------------------------------------------------


def _logger():
    log = logging.getLogger("orquestador")
    log.setLevel(logging.INFO)
    if log.handlers:
        return log
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=512 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    log.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    log.addHandler(sh)
    return log


log = _logger()


# --- Candado de una sola corrida a la vez -------------------------------------

STILL_ACTIVE = 259
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _pid_vivo(pid):
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return False
    salida = ctypes.c_ulong()
    ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(salida))
    ctypes.windll.kernel32.CloseHandle(h)
    return bool(ok) and salida.value == STILL_ACTIVE


class CorridaEnCursoError(Exception):
    def __init__(self, pid):
        super().__init__(f"ya hay una corrida en curso (pid {pid})")
        self.pid = pid


@contextlib.contextmanager
def candado():
    if LOCK_PATH.exists():
        pid_previo = None
        try:
            pid_previo = int(LOCK_PATH.read_text().strip())
        except ValueError:
            pass
        if pid_previo and _pid_vivo(pid_previo):
            raise CorridaEnCursoError(pid_previo)
        log.warning(f"Candado huérfano encontrado (pid {pid_previo}), lo limpio y sigo")
    LOCK_PATH.write_text(str(os.getpid()))
    try:
        yield
    finally:
        try:
            LOCK_PATH.unlink()
        except FileNotFoundError:
            pass


# --- Pasos ---------------------------------------------------------------------


def paso(nombre, cmd):
    log.info(f"  > {nombre}")
    try:
        r = subprocess.run(cmd, cwd=RAIZ_REPO, capture_output=True, text=True, timeout=TIMEOUT_PASO)
    except subprocess.TimeoutExpired:
        log.error(f"{nombre}: superó el tiempo límite ({TIMEOUT_PASO}s)")
        return False

    for linea in r.stdout.splitlines():
        log.info(f"    {linea}")
    if r.stderr.strip():
        for linea in r.stderr.splitlines():
            log.warning(f"    [stderr] {linea}")

    if r.returncode != 0:
        log.error(f"{nombre}: terminó con código {r.returncode}")
        return False
    return True


def paso_claude(nombre, instruccion, archivo_esperado):
    if shutil.which("claude") is None:
        log.error(f"{nombre}: 'claude' no está en el PATH")
        return False

    antes = archivo_esperado.stat().st_mtime if archivo_esperado.exists() else 0
    cmd = [
        "claude", "-p", instruccion,
        "--output-format", "json",
        "--permission-mode", "dontAsk",
        "--restricted",
        "--tools", "Read,Write",          # que ni existan otras herramientas
        "--allowedTools", "Read,Write",   # y que estas dos no requieran aprobación
        "--add-dir", DIR_ADD,
    ]
    log.info(f"  > {nombre}: claude -p...")
    try:
        r = subprocess.run(cmd, cwd=RAIZ_REPO, capture_output=True, text=True, timeout=TIMEOUT_CLAUDE)
    except subprocess.TimeoutExpired:
        log.error(f"{nombre}: claude -p superó el tiempo límite ({TIMEOUT_CLAUDE}s)")
        return False
    except Exception as e:
        log.error(f"{nombre}: error al invocar claude: {e}")
        return False

    resultado = None
    try:
        resultado = json.loads(r.stdout)
    except (json.JSONDecodeError, TypeError):
        pass

    es_error = bool(resultado.get("is_error")) if resultado else False
    denegados = resultado.get("permission_denials") if resultado else None

    if r.returncode != 0 or es_error:
        log.error(f"{nombre}: claude -p reportó falla (exit={r.returncode}, is_error={es_error})")
        if resultado:
            log.error(f"    resultado: {str(resultado.get('result', ''))[:300]}")
        return False
    if denegados:
        log.error(f"{nombre}: claude -p tuvo permisos denegados: {denegados}")
        return False

    # El CLI puede "salir bien" sin haber logrado la tarea real (ver plan) -
    # se verifica el efecto de verdad, no lo que el CLI dice de si mismo.
    if not archivo_esperado.exists() or archivo_esperado.stat().st_mtime <= antes:
        log.error(f"{nombre}: claude -p terminó pero {archivo_esperado.name} no se actualizó")
        return False
    try:
        datos = json.loads(archivo_esperado.read_text(encoding="utf-8"))
        if not isinstance(datos, list) or not datos:
            raise ValueError("vacío o no es una lista")
    except Exception as e:
        log.error(f"{nombre}: {archivo_esperado.name} no es JSON válido: {e}")
        return False

    log.info(f"{nombre}: OK, {archivo_esperado.name} con {len(datos)} elemento(s)")
    return True


# --- Rama 1: fotos nuevas --------------------------------------------------------


def _fotos_nuevas():
    if not preparar.ENTRADA.exists():
        return []
    procesadas = preparar.cargar_registro()
    fotos = [
        p for p in preparar.ENTRADA.iterdir()
        if p.is_file() and p.suffix.lower() in preparar.EXTENSIONES
    ]
    return [p for p in fotos if p.name not in procesadas]


def _verificar_agrupacion():
    """Cobertura foto->comida: si alguna foto del manifiesto no quedó en ninguna
    comida del borrador, es un fallo silencioso real (a diferencia de agrupar
    varias fotos en una sola comida, que puede ser perfectamente correcto).
    Reutiliza validar() de revisar.py — mismo cálculo de 'sueltas' que ya usa
    la validación normal. Solo avisa, no falla la rama."""
    try:
        manifiesto = json.loads(MANIFIESTO.read_text(encoding="utf-8"))
        borrador = json.loads(BORRADOR.read_text(encoding="utf-8"))
        _, sueltas = validar(borrador, manifiesto)
    except Exception:
        return

    if sueltas:
        log.warning(
            f"Agrupación: {len(sueltas)} foto(s) del manifiesto no quedaron en "
            f"ninguna comida del borrador: {', '.join(sueltas)} — revisar antes "
            f"de aprobar en la room Pendientes"
        )


def rama_fotos(ejecutar):
    nuevas = _fotos_nuevas()
    if not nuevas:
        log.info("Rama fotos: sin fotos nuevas")
        return

    mas_reciente = max(p.stat().st_mtime for p in nuevas)
    antiguedad_min = (time.time() - mas_reciente) / 60
    if antiguedad_min < VENTANA_ESTABLE_MIN:
        faltan = VENTANA_ESTABLE_MIN - antiguedad_min
        log.info(
            f"Rama fotos: lote inestable ({len(nuevas)} fotos), "
            f"faltan {faltan:.0f} min para considerarlo estable"
        )
        return

    log.info(
        f"Rama fotos: lote estable ({len(nuevas)} fotos) -> "
        f"{'ejecutando' if ejecutar else 'correría'} preparar -> contexto -> claude -> subir --subir"
    )
    if not ejecutar:
        return

    if not paso("preparar.py", [sys.executable, str(HERRAMIENTAS / "preparar.py")]):
        return
    if not paso("contexto.py", [sys.executable, str(HERRAMIENTAS / "contexto.py")]):
        return

    instruccion = (
        "Lee tools/prompt-extraccion.md y sigue esas instrucciones. El manifiesto y "
        "las fotos reducidas están en C:\\dev\\nutrilog-proceso. Escribe el resultado "
        "en C:\\dev\\nutrilog-proceso\\borrador2.json"
    )
    if not paso_claude("extraccion", instruccion, BORRADOR):
        return
    _verificar_agrupacion()

    if not paso("subir.py --subir", [sys.executable, str(HERRAMIENTAS / "subir.py"), "--subir"]):
        return

    log.info("Rama fotos: completada")


# --- Rama 2: correcciones pendientes ---------------------------------------------


def rama_correcciones(ejecutar):
    revisados = get("pipeline/revisados") or {}
    if not revisados:
        log.info("Rama correcciones: pipeline/revisados vacío")
        return

    log.info(
        f"Rama correcciones: {len(revisados)} revisado(s) -> "
        f"{'ejecutando' if ejecutar else 'correría'} aplicar --bajar -> claude -> aplicar --escribir"
    )
    if not ejecutar:
        return

    if not paso("aplicar.py --bajar", [sys.executable, str(HERRAMIENTAS / "aplicar.py"), "--bajar"]):
        return

    instruccion = "Lee tools/prompt-aplicar.md y sigue esas instrucciones."
    if not paso_claude("aplicar", instruccion, CORREGIDOS_JSON):
        return

    if not paso("aplicar.py --escribir", [sys.executable, str(HERRAMIENTAS / "aplicar.py"), "--escribir"]):
        return

    log.info("Rama correcciones: completada")


# --- main ----------------------------------------------------------------------


def main():
    ejecutar = "--ejecutar" in sys.argv
    solo_fotos = "--solo-fotos" in sys.argv
    solo_correcciones = "--solo-correcciones" in sys.argv
    correr_fotos = not (solo_correcciones and not solo_fotos)
    correr_correcciones = not (solo_fotos and not solo_correcciones)

    try:
        with candado():
            log.info(f"--- inicio (modo={'ejecutar' if ejecutar else 'prueba'}) ---")
            if correr_fotos:
                rama_fotos(ejecutar)
            if correr_correcciones:
                rama_correcciones(ejecutar)
            log.info("--- fin ---")
    except CorridaEnCursoError as e:
        log.warning(f"{e} — salgo sin hacer nada")


if __name__ == "__main__":
    main()
