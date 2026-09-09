# CLAUDE.md

Guía de trabajo para este repo. Léela antes de tocar `index.html`.

## Mapa de index.html

El archivo tiene **2447 líneas** (~150 KB) y es la app completa (HTML+CSS+JS en un solo archivo). Bloques funcionales, de arriba a abajo:

| Líneas | Bloque |
|---|---|
| 1-9 | `<head>`: manifest, meta, título, fuentes Google (Fraunces, DM Sans) |
| 10-26 | **Config e inicialización de Firebase** (SDK modular vía `<script type="module">`, CDN gstatic 11.8.1). Expone `window._fbGet`, `window._fbSet`, `window._fbGetMes` |
| 27-170 | **Estilos CSS** (variables de tema oscuro, hero, nav, calendario, meal-card, tags, formulario de registro, bottom-nav, overlays de chat/revisar/editar). El módulo Pendientes no agrega clases nuevas aquí — usa estilos inline, igual que el editor y los demás overlays |
| 172-233 | `<body>`: hero, debug-panel, nav secundaria (Hoy/Racha/Buscar/Filtrar), calendario, `<main>` con las 8 "rooms", footer con bottom-nav (Dashboard/Alertas/Consejos/Análisis/Añadir/**Pendientes** con badge `#pend-badge`) |
| 234-309 | **Catálogo de tags** `TAG_CATALOG` (macro, vitamina, mineral, funcional, bioactivo, alerta, contexto, suplemento) |
| 311-322 | Objeto `DATA` en memoria (meta, contexto, dias, resumen, alertas, consejos, **pendientes**) — se llena desde Firebase, no está hardcodeado |
| 324-348 | **Código muerto**: `formState`, `onIframeLoad`, `showFormStatus` — remanente del viejo flujo de Google Forms vía `<iframe>` (ya no hay `<iframe>` en el DOM ni nada que llame a `onIframeLoad`). `showFormStatus` sí sigue en uso, pero ahora llamado directo por `submitGForm` |
| 349-387 | Utilidades de hora: `horaA24`, `normalizarHora` |
| 388-459 | **Escritura a RTDB**: `generarComidaId`, `guardarComidaEnFirebase` (escribe comida + meta si no existe; helper compartido — la usan tanto `submitGForm` como la room Pendientes), `submitGForm` (guarda comida + meta del día desde el textarea CSV) |
| 460-497 | `renderRegistro()` — HTML del formulario de registro (room "registro") |
| 498-542 | **Parser de CSV genérico**: `parseCSVText`, `csvRowsToDias` (no se usa para Firebase, es utilidad de CSV de texto plano) |
| 543-659 | Exportar/preparar análisis en texto plano: `exportarAnalisisCSV`, `toggleAnalisisCustomFechas`, `validarRangoAnalisisCustom`, `prepararAnalisis` |
| 660-783 | **Llamada al proxy de Apps Script para análisis IA**: `ejecutarAnalisisIA` (fetch a `PROXY_URL`, parsea JSON de respuesta rápida/profunda) |
| 784-809 | `guardarAnalisisEnFirebase` — persiste alertas/consejos generados por la IA |
| 810-883 | **Lectura de RTDB**: `cargarRegistros` (carga meses vía `_fbGetMes`), `cargarAlertas`, `cargarConsejos` |
| 884-1032 | Funciones de render puro: stats automáticas, `renderAnalisis`, `renderComida`, `renderDia`, `renderResumen`, `renderAlertas`, `renderConsejos`, `renderContexto` |
| 1033-1036 | `render()` — stub vacío, no hace nada (comentario: "hero simplificado — fecha dinámica") |
| 1037-1045 | Captura global de errores (`window.onerror`) y logging (`window._log`) al `#debug-panel` |
| 1046-1077 | Estado de la app (`appState`) y generación del calendario (`generarCAL_MESES`, desde abril 2026 al mes actual) |
| 1078-1342 | **Navegación secundaria**: `irAHoy`, panel Racha, panel Buscar (`ejecutarBusqueda`), panel Filtrar (`aplicarFiltroCalendario`), render del calendario (`renderCalendar`), `updateSecNav` |
| 1343-1452 | **Sistema de "rooms"**: objeto `ROOMS` (mapa vista→room→render, incluye la entrada `pendientes`), `construirDia`, `updateView`, `invalidarVista`, `selectDia`, `setView`, `window.onload` (carga inicial — incluye `cargarPendientes()` en el `Promise.all`, con try/catch propio para que un fallo ahí nunca tumbe la carga de registros) |
| 1411-1426 | `exportCSV` — exporta todos los registros a un `.csv` descargable |
| 1427-1436 | `toggle(h)` — abre/cierra el acordeón de una meal-card y persiste el estado en `appState.comidasAbiertas` para sobrevivir a un re-render |
| 1455-1906 | **Módulo "Revisar"** (`rv*`): parseo/validación de la fila CSV antes de enviarla, wizard de 2 pasos, catálogo de tags para el modal (`RV_TAG_CATALOG`), `rvEnviar` (guarda en Firebase) |
| 1763-1906 | **Editor de comida existente** (`abrirEditarComida`, `guardarEdicionComida`, `eliminarComida`) — edita/borra un nodo `comidas/{id}` en Firebase |
| 1908-2172 | **Módulo "Pendientes"** (`pend*`): revisión dentro de la app de los registros propuestos por el pipeline externo — ver detalle abajo |
| 2173-2198 | `formatHora`, `bottomNav` (cambia `appState.view` y refresca) |
| 2199 | **`PROXY_URL`** — constante con el endpoint del Apps Script (ver Arquitectura) |
| 2201-2216 | `SYSTEM_PROMPT` — prompt fijo para el asistente IA (define el formato CSV de 14 columnas) |
| 2217-2268 | `enviarAIA` — variante simple de una sola llamada al proxy |
| 2269-2370 | **Chat IA** (`abrirIAChat`, `enviarIAChat`, `detectarCSV`, `usarCSV`) — conversación multi-turno contra `PROXY_URL`, detecta una línea CSV en la respuesta y la pasa al formulario |
| 2371-2440 | HTML de los overlays: chat IA, panel Revisar, panel Editar, modal de tags de Revisar, **panel flotante de Corregir de Pendientes** (`#pend-corregir-float`) |
| 2441-2445 | Registro del **service worker** (`navigator.serviceWorker.register('./sw.js')`) |

### Módulo "Pendientes" (líneas 1908-2172)

Room de revisión mobile-first para lo que deja el pipeline externo en `pipeline/pendientes`: una comida por pantalla, foto cargada bajo demanda, tres acciones (Aprobar / Corregir / Quitar).

- `diaIdDesdeFecha(fecha)` — deriva `"vie04"` de `"2026-09-04"`; es el único lugar en JS que replica el criterio de `dia_id()` de `tools/contexto.py` (en Python solo).
- `cargarPendientes()` — nunca rechaza (try/catch propio); si falla, deja `DATA.pendientes = []` y sigue. Se llama en `window.onload` junto a `cargarRegistros`/`cargarAlertas`/`cargarConsejos`.
- `renderPendientes(el)` / `pendPintar()` — arman el shell de la room una sola vez (construcción diferida, igual que las otras rooms) y repintan solo `#pend-card` en cada avance.
- `pendCargarFotos(id)` — pide `pipeline/imagenes/{id}` solo cuando esa comida está en pantalla; cachea en `PEND_IMG_CACHE`.
- `pendAprobar()` — arma el objeto `comida` (sin `confianza`/`dudas`/`problemas`/`fotos`) y llama a `guardarComidaEnFirebase` (línea 397, la misma que usa `submitGForm`); borra el pendiente y su imagen.
- `pendQuitar()` — **mueve** (no borra) a `pipeline/descartados/{id}`; conserva la imagen. Reversible a propósito: no hay deshacer en la UI.
- `pendAbrirCorregir` / `pendConfirmarCorregir` — panel flotante sin backdrop (`#pend-corregir-float`, HTML en la línea ~2433) que se reposiciona con `window.visualViewport` para no quedar tapado por el teclado on-screen; mueve el pendiente completo a `pipeline/revisados/{id}` con el campo `instruccion` (texto tal cual del usuario — nunca toca `nota`), conserva la imagen.

### Archivos fuera de index.html
- `sw.js` — service worker mínimo (solo `skipWaiting`, sin caché real; el `fetch` listener está vacío)
- `manifest.json` — PWA manifest ("NutriLog", iconos 192/512, `display: standalone`)
- `icon-192.png`, `icon-512.png` — iconos de la PWA
- `README.md` — una línea de descripción

## Arquitectura

### Firebase Realtime Database — rutas exactas
```
registros/{anio}/{mes}/{diaId}/meta/
    fecha        "2026-04-29"
    dia_id       "lun29"
    etiqueta     "Lunes 29 de abril"
    resumen_dia  string

registros/{anio}/{mes}/{diaId}/comidas/{comidaId}/
    titulo       string
    hora         "HH:MM" (24h, normalizada por normalizarHora)
    icono        emoji
    alimentos    array de strings
    tags/
        cubierto     array
        atencion     array
        contexto     array
        suplementos  array
    nota         string | null

alertas/{alerta_N}   { icono, titulo, detalle, tipo }
consejos/{consejo_N} { emoji, texto }

pipeline/pendientes/{id}
    fecha, hora, titulo, icono, nota   strings
    alimentos                          array de strings
    tags/ { cubierto, atencion, contexto, suplementos }   arrays
    confianza    "alta" | "media" | "baja"
    dudas        array de strings
    problemas    array de strings (validaciones de tools/revisar.py)
    fotos        array de nombres de archivo (NO imágenes)

pipeline/imagenes/{id}
    imagenes     array de strings base64 jpeg

pipeline/revisados/{id}    → mismo shape que pendientes/{id} + instruccion (texto libre del usuario, "Corregir")
pipeline/descartados/{id}  → mismo shape que pendientes/{id}, sin campo extra ("Quitar")
```
- `{anio}` = "YYYY", `{mes}` = "MM" con cero a la izquierda.
- `{comidaId}` se autogenera como `{diaId}_c{n}` (`generarComidaId`, línea 388).
- `meta` no se sobreescribe si ya existe (se escribe solo la primera vez que se registra un día).
- **`guardarComidaEnFirebase(fecha, diaId, comida, resumenDiaFallback)`** (línea 397) encapsula generar `comidaId` + escribir la comida + escribir `meta` si falta. La usan tanto `submitGForm` (flujo CSV) como `pendAprobar` (room Pendientes) — es el único punto de escritura de una comida nueva, no lo dupliques si agregas un tercer flujo.
- La lectura completa (`cargarRegistros`, línea 810) recorre todos los meses definidos en `CAL_MESES` (desde abril 2026 hasta el mes actual) con `_fbGetMes` y arma `DATA.dias` en memoria; no hay listeners en tiempo real (`onValue`), todo es lectura puntual (`get`) + recarga manual tras cada escritura.
- `pipeline/*` lo escribe un pipeline externo (fuera de este repo — ver `tools/`) y lo consume/limpia la room Pendientes dentro de la app. `{id}` es la key de Firebase, nunca un campo dentro del objeto.

**Deuda técnica conocida:** `pipeline/imagenes/{id}` no se borra cuando un pendiente se mueve a `revisados` o `descartados` (a propósito — el pipeline podría necesitar reprocesar esa foto), y nada limpia `pipeline/revisados`/`pipeline/descartados` una vez que el pipeline los consume. Con el tiempo van a acumular base64 huérfano. Se resolverá del lado del pipeline (un futuro `enviar.py` o similar), no desde `index.html`.

### Sistema de "rooms" (rutas de navegación)
- Hay 8 `<div class="room" id="room-*">` fijos en el DOM (línea 194-203): `dia`, `resumen`, `contexto`, `alertas`, `consejos`, `registro`, `analisis`, `pendientes`.
- El objeto `ROOMS` (línea 1344) mapea cada vista a su `id` de room y a una función `render(el)`.
- **Construcción diferida**: cada room se renderiza (`conf.render(el)`) solo la primera vez que se visita; luego queda marcado `construido = true` y no se vuelve a tocar su `innerHTML` salvo invalidación explícita. La room `pendientes` es la excepción parcial: su shell se construye una sola vez, pero `pendPintar()` reescribe `#pend-card` en cada avance sin pasar por `invalidarVista`.
- **Mostrar/ocultar**: `updateView()` (línea ~1367) pone `hidden = true` en todos los rooms excepto el de la vista activa. No se destruye ni recrea el DOM al navegar, solo se oculta/muestra.
- **Invalidación**: tras cualquier escritura en Firebase (nueva comida, edición, borrado, guardar análisis) se llama `invalidarVista('dia')` / `invalidarVista('resumen')` / etc., lo que fuerza a `updateView()` a volver a llamar `render(el)` la próxima vez que esa vista se muestre.
- La navegación se dispara desde: bottom-nav (`bottomNav`, línea 2190), pills de nav secundaria (`irAHoy`, `toggleRacha`, `toggleBuscar`, `toggleFiltrar`), clic en un día del calendario (`selectDia`), o internamente (`setView`).

### Flujo de la llamada al proxy de Apps Script
1. La app hace `fetch(PROXY_URL + '?...', { method: 'GET', redirect: 'follow' })` — nunca `POST`, todo por querystring.
2. Tres puntos de entrada usan el mismo `PROXY_URL` (línea 1922):
   - `ejecutarAnalisisIA(modo)` (línea 650) → `?p={periodo}&n={nivel}&m={rapido|profundo}` → el proxy devuelve `{ text }`; si `modo==='profundo'`, `text` es un JSON string con `{ analisis, alertas[], consejos[] }` que se parsea y se puede guardar en Firebase (`guardarAnalisisEnFirebase`).
   - `enviarAIA()` (línea 1940) → `?msg={prompt}&system={SYSTEM_PROMPT}` → un solo turno, el proxy devuelve `{ text }` con una línea CSV que se inyecta directo en `#csv-input`.
   - `enviarIAChat()` (línea 2040) → `?msg={JSON.stringify(mensajes)}` (historial completo de la conversación) → el proxy devuelve `{ text }`; el cliente busca una línea que matchee `^\d{4}-\d{2}-\d{2},` (`detectarCSV`) y si la encuentra la ofrece como CSV listo para usar.
3. El proxy en sí (el Apps Script del otro lado de `PROXY_URL`) **no vive en este repo** — es una caja negra que llama a un modelo (Haiku para "rápido", Sonnet para "profundo") y responde JSON. Todo lo que sabemos de su contrato son los parámetros de querystring y la forma de la respuesta descritos arriba.
4. Nada de esto pasa por el formulario de Google Forms/Sheets que insinúa el footer ("· Google Sheets") — ese texto es un remanente de una versión anterior; la escritura real es directa a Firebase (ver arriba).

## Reglas de trabajo

- Todo vive en `index.html`. No crear archivos JS o CSS separados sin autorización explícita.
- No agregar frameworks, npm, ni build tools.
- La URL del proxy de Apps Script (`PROXY_URL`, línea 1922) **nunca se modifica**. Si un cambio parece requerirlo, detente y pregunta.
- Cambios quirúrgicos: una modificación a la vez, esperando confirmación. No reescribir bloques completos.
- Antes de editar, mostrar qué se va a cambiar y por qué.
- Usa lectura parcial guiada por el mapa de arriba (`Read` con `offset`/`limit`, o `Grep`). No cargues el archivo completo salvo que sea indispensable.
- El despliegue es GitHub Pages vía `git push`.
