# PLAN — Pipeline automatizado de fotos a Firebase (NutriLog)

## Objetivo

Reducir el registro de comidas de ~2 horas cada dos semanas a ~15 minutos de revisión.

**Flujo actual:** foto → (2 semanas después) describir cada foto a mano → CSV → pegar en el formulario → parsear → verificar → enviar.

**Flujo objetivo:** foto → carpeta sincronizada → un comando → revisar y corregir en pantalla → aprobar.

## Principio de diseño

Este pipeline **no toca `index.html`**. Es un sistema paralelo que escribe a la misma base de datos. Si algo falla, NutriLog sigue funcionando exactamente igual. Esto elimina la mayor parte del riesgo.

Un solo agente ejecutando pasos en orden, no una cadena de agentes revisándose entre sí. La verificación viene de scripts deterministas y de la revisión humana, no de una segunda IA.

## Estructura de carpetas

```
Mi unidad\NutriLog-Fotos\          ← entrada, sincroniza desde el S24
C:\dev\seguimiento_comidas\tools\  ← scripts, viven en el repo
C:\dev\nutrilog-proceso\           ← trabajo temporal, fuera del repo
```

Las fotos de comida nunca entran a GitHub. El repo es público y no le sirven a nadie.

---

## Fase 0 — Prerequisitos

**Qué hay que resolver:**

1. Google Drive para escritorio en **modo espejo**, no streaming. En streaming los archivos son fantasmas de 0 bytes y ningún script puede leerlos.
2. Python en el PATH. Verificar con `python --version`.
3. Conocer las reglas actuales de la Realtime Database. Definen si el script puede escribir con una llamada REST simple o si hay que resolver autenticación.
4. Definir la ruta de escritura en RTDB para verificar que coincide con la que usa la app.

**Listo cuando:** un script de Python puede listar los archivos de la carpeta de Drive y leer su tamaño real.

---

## Fase 1 — Preparación (`preparar.py`)

**Qué hace:**

- Recorre `NutriLog-Fotos\` y detecta las fotos que no se han procesado
- Lee el EXIF de cada una para extraer fecha y hora exactas
- Redimensiona a ~1000px de ancho en una carpeta de trabajo
- Genera `manifiesto.json` con: nombre de archivo, ruta de la copia reducida, fecha, hora

**Por qué el redimensionado:** las fotos del S24 son de 12 MP. Mandarlas en tamaño original quema contexto sin agregar precisión sobre qué hay en el plato.

**Por qué el EXIF:** hoy reconstruyes fechas de memoria dos semanas después. El archivo ya trae el dato exacto.

**Cuidado con:** la zona horaria. Verificar que la hora del EXIF coincida con la hora local de Quintana Roo y no con UTC.

**Listo cuando:** con 5 fotos de prueba, el manifiesto tiene las 5 con fecha y hora correctas.

---

## Fase 2 — Lectura de imágenes (Claude Code)

**Qué hace:**

Claude Code lee el manifiesto, ve cada foto reducida, y genera `borrador.csv` con el formato exacto que ya usa NutriLog.

**Restricción crítica — vocabulario cerrado:** se le pasa el catálogo de tags extraído de `index.html`. Solo puede usar etiquetas que ya existen. No inventa tags nuevos. Si no encuentra una que aplique, deja el campo vacío y lo marca para revisión.

**Restricción crítica — formato CSV:** las comas están prohibidas en las columnas 1 a 13, incluso entrecomilladas, porque rompen el parser de Apps Script. Separador para múltiples valores: ` + `. Solo la columna 14 (nota) admite comas.

**Qué se le pide explícitamente:**
- Marcar con baja confianza lo que no distinga bien
- No adivinar porciones cuando no haya referencia de tamaño en la foto
- Ignorar fotos que no sean de comida

**Listo cuando:** genera un CSV válido con las 5 fotos de prueba, sin tags inventados.

---

## Fase 3 — Validación (`validar.py`)

**Qué hace, sin IA de por medio:**

- Verifica que cada fila tenga las 14 columnas
- Verifica que no haya comas en las columnas 1–13
- Verifica que cada tag exista en el catálogo
- Verifica que las fechas sean válidas y no futuras
- Consulta Firebase y detecta si ya existe un registro para esa fecha y hora (evita duplicados)

Este script no opina: pasa o truena, con el motivo exacto.

**Listo cuando:** detecta correctamente un CSV que le rompas a propósito.

---

## Fase 4 — Revisión (✅ existe, distinto de lo planeado)

**Qué hace, en la versión real:** no es un `revision.html` con export a CSV — es la room **Pendientes**, dentro de NutriLog (`index.html`). Una comida por pantalla, foto cargada bajo demanda, y tres decisiones que escriben a Firebase al instante: Aprobar, Corregir (con instrucción para el pipeline) o Quitar. `tools/revisar.py` sigue existiendo como visor local alterno (genera `revision.html`), pero la revisión real ya no depende de él.

**Este sigue siendo el único paso que requiere tu tiempo.** El diseño no cambió: tu trabajo es corregir, no transcribir.

---

## Fase 5 — Subida a revisión (`tools/subir.py`, ✅ existe)

**Qué hace, en la versión real:** no escribe en `registros/` directamente (ese diseño cambió — ver Fase 4). Lee el borrador de Claude Code (`borrador2.json`) y `manifiesto.json`, y deja cada comida en `pipeline/pendientes` + `pipeline/imagenes` para que la room Pendientes la revise. La escritura final a `registros/` ocurre cuando el humano aprueba dentro de la app, no en este script.

**Requisitos de seguridad — los tres ya están:**
- **Modo prueba por defecto:** sin `--subir` solo imprime qué haría, no escribe nada. `--subir` sube de verdad.
- **Idempotencia:** `C:\dev\nutrilog-proceso\subidos.json` lleva registro de los ids ya subidos; si un id ya está ahí, se salta.
- **Anti-duplicado:** antes de subir, consulta `registros/{anio}/{mes}/{diaId}/comidas` y si ya hay una comida real a esa misma hora, se salta y avisa — evita mandar a revisión algo que ya se registró por otro medio (la app, o una corrida anterior ya aprobada).

`--limpiar` borra `pipeline/pendientes`, `pipeline/imagenes`, `pipeline/revisados` y `pipeline/descartados` (no toca `subidos.json` ni `registros/`).

**Listo cuando:** ✅ cumplido — un pendiente de prueba subido con `--subir` aparece en la room Pendientes de NutriLog, y correr `subir.py` de nuevo lo salta por "ya subido".

---

## Fase 6 — Unir todo

Un solo comando que corre Fases 1 a 4 y te deja el HTML de revisión abierto. La escritura queda separada, porque es la única acción irreversible.

**Listo cuando:** de foto a registro en Firebase sin pasos manuales fuera de la revisión.

---

## Riesgos conocidos

| Riesgo | Mitigación |
|---|---|
| Fotos suben a GitHub | `.gitignore` desde la Fase 1, verificado con `git status` |
| Registros duplicados | Chequeo contra `registros/` + idempotencia con `subidos.json`, ambos en `tools/subir.py` |
| Tags inventados rompen el sistema | Vocabulario cerrado + validación determinista (`revisar.py`) |
| Escritura masiva errónea a Firebase | Modo prueba por defecto en `subir.py`; `--subir` es explícito |
| EXIF en UTC en vez de hora local | Verificar contra una foto de hora conocida en Fase 1 |
| Drive en modo streaming | Confirmado en Fase 0 antes de escribir código |

## Precisión esperada

La identificación de alimentos tiene error real. Va a confundir frutos secos entre sí, va a fallar con platillos donde la mitad tapa a la otra mitad, y no va a estimar porciones sin referencia de tamaño.

Por eso la revisión humana es parte del diseño, no un parche. El objetivo no es eliminar tu participación: es cambiar transcripción por corrección.

## Orden de construcción

Una fase a la vez, probada antes de seguir. Si se arma la cadena completa antes de probar la primera pieza, acabas depurando cinco cosas sin saber cuál falló.

**Siguiente paso:** automatizar la Fase 0-2 (hoy `preparar.py` + Claude Code + `subir.py` se corren a mano en orden); Fase 6 ("un solo comando") sigue sin construirse.
