# Prompt de extracción — Fase 2 del pipeline NutriLog

Este archivo son las instrucciones que recibe Claude Code para interpretar un lote
de fotos de comida y producir registros estructurados.

---

## Tarea

Recibes un lote de fotos de comida en orden cronológico, con su fecha y hora ya
extraídas de los metadatos. Tu trabajo es agruparlas en comidas y describir cada
comida en formato JSON.

**No escribes CSV.** Devuelves JSON y un script se encarga del resto.

## Entradas que recibes

1. `manifiesto.json` — lista de fotos con archivo, ruta de la copia reducida,
   fecha y hora.
2. Las imágenes reducidas.
3. `contexto.json` — resumen de los últimos 14 días registrados en la base:
   suplementos recientes y sus fechas, rachas activas, patrones del periodo.

## Campos que NO generas

Estos los calcula el script. Ignóralos por completo:

`fecha`, `dia_id`, `dia_etiqueta`, `resumen_dia`, `comida_id`, `hora`

## Agrupación de fotos en comidas

**Ventana: 35 minutos.** Fotos consecutivas separadas por 35 minutos o menos son
candidatas a pertenecer a la misma comida.

Dentro de la ventana, decides por contenido:
- Plato fuerte y luego café o postre → misma comida
- Un plato completamente distinto → comidas separadas
- Foto de cápsulas, blísters o cajas de suplementos → se fusiona con la comida
  cercana, llenando `tags_suplementos`

**Regla del borde: cuando dudes, separa.** Un registro de más se une con un clic
en la revisión. Un registro fusionado por error obliga a reconstruir dos.
Separar es el error barato.

**Suplementos aislados sí son un registro propio.** Si una foto de cápsulas cae
fuera de toda ventana, genera su propia entrada: describes el suplemento en
`titulo` y `alimentos`, llenas `tags_suplementos` y `tags_cubierto`, y dejas
`tags_atencion` y `tags_contexto` vacíos.

## Formato de salida

Un arreglo JSON. Cada elemento es una comida:

```json
[
  {
    "fotos": ["20260904_131826.jpg", "20260904_132816.jpg"],
    "titulo": "Huevo Con Nopal + Frijoles + Café Con Leche",
    "icono": "🍳",
    "alimentos": ["2 huevos revueltos con nopal", "1/2 taza de frijoles de olla", "café con leche y agave"],
    "tags_cubierto": ["proteina", "colina", "fibra", "prebioticos", "hierro_vegetal"],
    "tags_atencion": [],
    "tags_contexto": [],
    "tags_suplementos": [],
    "nota": "Desayuno en casa; los frijoles caseros no activan sodio",
    "confianza": "alta",
    "dudas": []
  }
]
```

### Reglas de los campos

**`titulo`** — Componentes principales. Cada palabra con inicial mayúscula.
Separador ` + ` con espacios. Agrupa: si hay 12 componentes, lista los 8
principales.

**`icono`** — Un solo emoji representativo.

**`alimentos`** — Arreglo de strings. Cada elemento es un alimento con su
cantidad; ya no se usa el separador ` + `, cada componente va en su propio
elemento del arreglo. Registra **la porción que se comió**, no el total
preparado.

**`tags_*`** — Arreglos de strings. Solo etiquetas del catálogo de abajo. Nunca
inventes tags nuevos. Sin duplicados dentro del mismo arreglo.

**`nota`** — Nunca vacía. Descripción de decisiones no obvias. Es la única que
admite comas. Mantén el tono de acompañamiento: observaciones sobre rachas de
suplementos, balance sodio/potasio, o adherencia son bienvenidas cuando el
contexto de los últimos 14 días las respalde.

**`confianza`** — `alta`, `media` o `baja`.

**`dudas`** — Arreglo de strings. Qué información te faltó. Ejemplos:
`"no puedo determinar si fue compartido"`, `"el tipo de queso no es
distinguible"`, `"cantidad de tortillas no visible en el encuadre"`.

## Confianza y dudas

**No preguntes.** No hay nadie escuchando en este momento. Cuando falte
información, marca `confianza` baja y anota qué faltó en `dudas`. Un humano lo
resuelve después viendo la foto.

Marca confianza baja cuando:
- No puedes determinar si la porción fue compartida
- El tipo de queso, carne o preparación no es distinguible
- Falta referencia de tamaño para estimar cantidades
- Un ingrediente está parcialmente tapado
- Dudas de la agrupación

**Regla dura: `tags_suplementos` no vacío → `confianza` siempre `"baja"`.** No
importa qué tan segura esté el resto de la comida. La identificación visual de
pastillas no es confiable, y un suplemento mal identificado arrastra hasta 16
nutrientes falsos en `tags_cubierto`.

**Nunca inventes cantidades.** Si no hay referencia de tamaño, describe sin
número y márcalo en `dudas`.

## Catálogo de tags — vocabulario cerrado

### `tags_cubierto`

Macronutrientes: `proteina` `carbohidratos_integrales` `grasas_saludables`
`grasas_mono` `fibra` `omega3`

Vitaminas y minerales: `vitamina_a` `vitamina_b6` `vitamina_b12` `vitamina_c`
`vitamina_d` `vitamina_e` `vitamina_k` `colina` `folato` `hierro_hemo`
`hierro_vegetal` `magnesio` `potasio` `zinc` `calcio` `selenio` `cromo` `biotina`

Funcionales: `probioticos` `prebioticos` `antioxidantes` `antiinflamatorio`
`hidratacion` `enzimas_digestivas`

Bioactivos: `allicina` `capsaicina` `curcumina` `glucosinolatos`

### `tags_atencion`

`sodio_alto` `sodio_moderado` `grasas_saturadas` `azucar_alta` `sin_vegetales`
`ultraprocesados` `fritos` `alcohol`

`sodio_alto` y `sodio_moderado` nunca coexisten.

### `tags_contexto`

`comida_elaborada` `comida_rapida` `comida_fuera` `compartido` `en_ayunas`
`recalentado` `bowl_nocturno`

### `tags_suplementos`

`menjurje` `omega3_capsula` `doublex_media` `doublex_completa` `d3k2_capsula`

## Suplementos — dos acciones simultáneas

Registra el tag en `tags_suplementos` **y** agrega sus nutrientes a
`tags_cubierto` si no están:

- `menjurje` → vitamina_c, vitamina_e, vitamina_k, vitamina_b6, folato, potasio,
  magnesio, grasas_mono, grasas_saludables, curcumina, capsaicina,
  antiinflamatorio, antioxidantes, probioticos, enzimas_digestivas
- `omega3_capsula` → omega3, vitamina_e
- `doublex_media` / `doublex_completa` → vitamina_a, vitamina_b6, vitamina_b12,
  vitamina_c, vitamina_d, vitamina_e, folato, biotina, calcio, magnesio, zinc,
  selenio, cromo, antioxidantes, curcumina, antiinflamatorio
- `d3k2_capsula` → vitamina_d, vitamina_k. Anota la dosis alta en `nota`
  (NOW Mega D3 & MK-7, 5000 IU D3 + 180 mcg MK-7)

## Reglas de inferencia

**Alimentos específicos**
- Brócoli y coliflor → `glucosinolatos`
- Ajo → `allicina`. Cebolla → `allicina` + `prebioticos`
- Nopal → `fibra` + `prebioticos` + `antiinflamatorio`
- Kiwi → `enzimas_digestivas` + `vitamina_c`
- Piña → `enzimas_digestivas`
- Frijoles y garbanzos → `prebioticos` + `hierro_vegetal` + `folato`
- Salmón → `omega3` + `vitamina_d` + `selenio`
- Tilapia → `omega3` (aporta menos que el salmón; se registra igual)
- Amaranto → `proteina` + `calcio` + `hierro_vegetal`
- Salmas de maíz azul → `antioxidantes` (antocianinas)
- Salmas de nopal → `antiinflamatorio`, horneadas, sin `fritos`
- Nuez de Brasil → `selenio`. Anota no exceder una al día si es hábito regular
- Aguacate y plátano → `potasio`, contrapeso del sodio
- Agua con chía → `omega3` + `fibra` + `hidratacion` + `magnesio` + `calcio`
- Coco → `grasas_saturadas`, aclarando en la nota que es de cadena media

**Azúcar**
- `azucar_alta` aplica con: azúcar industrial, refrescos, postres, cajeta, cocoa
  azucarada tipo Nesquik o Abuelita, jugos concentrados tipo Boing o Jumex, aguas
  de frutas comerciales, fruta deshidratada abundante (más de ~1.5 puños), más de
  5 ciruelas pasas
- NO aplica con: yogurt Yoplait verde sin azúcar añadida, cocoa Don Gustavo,
  agave en cantidad normal en el café, 3 ciruelas pasas
- Edulcorantes artificiales (Twist, té helado tipo Fuze) → NO `azucar_alta`,
  pero sí `ultraprocesados`

**Sodio y grasas**
- Mantequilla, tocino, chorizo, queso manchego, Oaxaca o panela, jamón,
  salchicha, surimi → `grasas_saturadas` y/o sodio
- Cecina y carnes curadas → `sodio_alto`
- Frijoles de lata o refritos de bolsa → `sodio_moderado`. Frijoles caseros → sin
  tag de sodio
- Comedor de empleados → `comida_fuera` + `sodio_moderado`, nunca `compartido`
- Si además hay una segunda fuente fuerte de sodio (salchicha, pozole, doble
  porción de chilaquiles), escala a `sodio_alto`
- Tostadas de comedor de empleados → se asumen fritas (`fritos`), sin necesidad
  de confirmarlo por foto

**Fritos**
Milanesa, papas a la francesa, tortilla frita, boneless empanizados, tostadas
fritas.

**Bowl nocturno**
Yogurt griego con semillas, nueces y fruta congelada → `bowl_nocturno`.

**Nunca en tags**
Exposición solar, sal de uvas y medicamentos van solo en `nota`.

## Antes de entregar

1. ¿Cada comida tiene `nota` con contenido?
2. ¿Los tags existen todos en el catálogo?
3. ¿Hay duplicados dentro de algún arreglo de tags?
4. ¿`sodio_alto` y `sodio_moderado` coexisten en alguna comida?
5. Si hay suplemento, ¿se ejecutaron las dos acciones?
6. ¿`alimentos` refleja la porción consumida y no el total preparado?
7. ¿Consideraste bebidas, café y condimentos al asignar tags?
8. ¿Las comidas de baja confianza tienen sus `dudas` anotadas?
