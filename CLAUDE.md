# CLAUDE.md

Guía de trabajo para este repo. Léela antes de tocar `index.html`.

## Mapa de index.html

El archivo tiene **2162 líneas** (~135 KB) y es la app completa (HTML+CSS+JS en un solo archivo). Bloques funcionales, de arriba a abajo:

| Líneas | Bloque |
|---|---|
| 1-9 | `<head>`: manifest, meta, título, fuentes Google (Fraunces, DM Sans) |
| 10-26 | **Config e inicialización de Firebase** (SDK modular vía `<script type="module">`, CDN gstatic 11.8.1). Expone `window._fbGet`, `window._fbSet`, `window._fbGetMes` |
| 27-170 | **Estilos CSS** (variables de tema oscuro, hero, nav, calendario, meal-card, tags, formulario de registro, bottom-nav, overlays de chat/revisar/editar) |
| 172-229 | `<body>`: hero, debug-panel, nav secundaria (Hoy/Racha/Buscar/Filtrar), calendario, `<main>` con los 7 "rooms", footer con bottom-nav (Dashboard/Alertas/Consejos/Análisis/Añadir) |
| 234-303 | **Catálogo de tags** `TAG_CATALOG` (macro, vitamina, mineral, funcional, bioactivo, alerta, contexto, suplemento) |
| 309-316 | Objeto `DATA` en memoria (meta, contexto, dias, resumen, alertas, consejos) — se llena desde Firebase, no está hardcodeado |
| 318-341 | **Código muerto**: `formState`, `onIframeLoad`, `showFormStatus` — remanente del viejo flujo de Google Forms vía `<iframe>` (ya no hay `<iframe>` en el DOM ni nada que llame a `onIframeLoad`). `showFormStatus` sí sigue en uso, pero ahora llamado directo por `submitGForm` |
| 343-380 | Utilidades de hora: `horaA24`, `normalizarHora` |
| 382-448 | **Escritura a RTDB**: `generarComidaId`, `submitGForm` (guarda comida + meta del día desde el textarea CSV) |
| 450-486 | `renderRegistro()` — HTML del formulario de registro (room "registro") |
| 491-532 | **Parser de CSV genérico**: `parseCSVText`, `csvRowsToDias` (no se usa para Firebase, es utilidad de CSV de texto plano) |
| 533-649 | Exportar/preparar análisis en texto plano: `exportarAnalisisCSV`, `toggleAnalisisCustomFechas`, `validarRangoAnalisisCustom`, `prepararAnalisis` |
| 650-772 | **Llamada al proxy de Apps Script para análisis IA**: `ejecutarAnalisisIA` (fetch a `PROXY_URL`, parsea JSON de respuesta rápida/profunda) |
| 774-799 | `guardarAnalisisEnFirebase` — persiste alertas/consejos generados por la IA |
| 800-873 | **Lectura de RTDB**: `cargarRegistros` (carga meses vía `_fbGetMes`), `cargarAlertas`, `cargarConsejos` |
| 874-1022 | Funciones de render puro: stats automáticas, `renderAnalisis`, `renderComida`, `renderDia`, `renderResumen`, `renderAlertas`, `renderConsejos`, `renderContexto` |
| 1023-1025 | `render()` — stub vacío, no hace nada (comentario: "hero simplificado — fecha dinámica") |
| 1027-1034 | Captura global de errores (`window.onerror`) y logging (`window._log`) al `#debug-panel` |
| 1036-1064 | Estado de la app (`appState`) y generación del calendario (`generarCAL_MESES`, desde abril 2026 al mes actual) |
| 1069-1332 | **Navegación secundaria**: `irAHoy`, panel Racha, panel Buscar (`ejecutarBusqueda`), panel Filtrar (`aplicarFiltroCalendario`), render del calendario (`renderCalendar`), `updateSecNav` |
| 1334-1441 | **Sistema de "rooms"**: objeto `ROOMS` (mapa vista→room→render), `construirDia`, `updateView`, `invalidarVista`, `selectDia`, `setView`, `window.onload` (carga inicial) |
| 1400-1414 | `exportCSV` — exporta todos los registros a un `.csv` descargable |
| 1416-1425 | `toggle(h)` — abre/cierra el acordeón de una meal-card y persiste el estado en `appState.comidasAbiertas` para sobrevivir a un re-render |
| 1443-1900 | **Módulo "Revisar"** (`rv*`): parseo/validación de la fila CSV antes de enviarla, wizard de 2 pasos, catálogo de tags para el modal (`RV_TAG_CATALOG`), `rvEnviar` (guarda en Firebase) |
| 1751-1894 | **Editor de comida existente** (`abrirEditarComida`, `guardarEdicionComida`, `eliminarComida`) — edita/borra un nodo `comidas/{id}` en Firebase |
| 1896-1920 | `formatHora`, `bottomNav` (cambia `appState.view` y refresca) |
| 1922 | **`PROXY_URL`** — constante con el endpoint del Apps Script (ver Arquitectura) |
| 1924-1938 | `SYSTEM_PROMPT` — prompt fijo para el asistente IA (define el formato CSV de 14 columnas) |
| 1940-1967 | `enviarAIA` — variante simple de una sola llamada al proxy |
| 1969-2091 | **Chat IA** (`abrirIAChat`, `enviarIAChat`, `detectarCSV`, `usarCSV`) — conversación multi-turno contra `PROXY_URL`, detecta una línea CSV en la respuesta y la pasa al formulario |
| 2094-2155 | HTML de los overlays: chat IA, panel Revisar, panel Editar, modal de tags de Revisar |
| 2156-2160 | Registro del **service worker** (`navigator.serviceWorker.register('./sw.js')`) |

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
```
- `{anio}` = "YYYY", `{mes}` = "MM" con cero a la izquierda.
- `{comidaId}` se autogenera como `{diaId}_c{n}` (`generarComidaId`, línea 382).
- `meta` no se sobreescribe si ya existe (se escribe solo la primera vez que se registra un día).
- La lectura completa (`cargarRegistros`, línea 800) recorre todos los meses definidos en `CAL_MESES` (desde abril 2026 hasta el mes actual) con `_fbGetMes` y arma `DATA.dias` en memoria; no hay listeners en tiempo real (`onValue`), todo es lectura puntual (`get`) + recarga manual tras cada escritura.

### Sistema de "rooms" (rutas de navegación)
- Hay 7 `<div class="room" id="room-*">` fijos en el DOM (línea 195-201): `dia`, `resumen`, `contexto`, `alertas`, `consejos`, `registro`, `analisis`.
- El objeto `ROOMS` (línea 1334) mapea cada vista a su `id` de room y a una función `render(el)`.
- **Construcción diferida**: cada room se renderiza (`conf.render(el)`) solo la primera vez que se visita; luego queda marcado `construido = true` y no se vuelve a tocar su `innerHTML` salvo invalidación explícita.
- **Mostrar/ocultar**: `updateView()` (línea 1357) pone `hidden = true` en todos los rooms excepto el de la vista activa. No se destruye ni recrea el DOM al navegar, solo se oculta/muestra.
- **Invalidación**: tras cualquier escritura en Firebase (nueva comida, edición, borrado, guardar análisis) se llama `invalidarVista('dia')` / `invalidarVista('resumen')` / etc. (línea 1383), lo que fuerza a `updateView()` a volver a llamar `render(el)` la próxima vez que esa vista se muestre.
- La navegación se dispara desde: bottom-nav (`bottomNav`, línea 1913), pills de nav secundaria (`irAHoy`, `toggleRacha`, `toggleBuscar`, `toggleFiltrar`), clic en un día del calendario (`selectDia`), o internamente (`setView`).

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
