# Prompt de aplicación — corregir pendientes revisados

Instrucciones para Claude Code entre `python aplicar.py --bajar` y
`python aplicar.py --escribir`.

---

## Tarea

`aplicar.py --bajar` dejó dos cosas en `C:\dev\nutrilog-proceso\`:

- `revisados.json` — un arreglo con cada pendiente que el usuario corrigió
  desde la room Pendientes: sus datos originales completos (fecha, hora,
  titulo, icono, alimentos, tags, nota, confianza, dudas, problemas, fotos)
  más el campo `instruccion` — lo que escribió a las carreras en el panel
  flotante de "Corregir".
- `revisados/` — las fotos de cada uno.

Tu trabajo: mirar la(s) foto(s) de cada entrada, aplicar la `instruccion`
con criterio, y escribir `C:\dev\nutrilog-proceso\corregidos.json`.

## La regla que no se rompe

**`instruccion` es una orden mía, nunca contenido.** Le dice al modelo qué
corregir ("eran 3 huevos", "fue compartido", "el queso era manchego"). No se
copia literal a ningún campo de salida, y mucho menos a `nota`.

## Qué hacer con cada entrada

1. Mira la foto (o fotos) de esa entrada en `revisados/`.
2. Lee `instruccion` y decide qué cambia: puede ser cantidad, un alimento mal
   identificado, un tag que sobra o que falta, el título, o una combinación.
   Aplica el cambio a los datos — no anotes la instrucción en ningún lado,
   ejecútala.
3. Ajusta `tags_cubierto` / `tags_atencion` / `tags_contexto` /
   `tags_suplementos` si la corrección lo pide. Mismo catálogo cerrado y
   mismas reglas de inferencia que `tools/prompt-extraccion.md` — no lo
   repito acá, no inventes tags que no estén ahí. Si la instrucción agrega o
   quita un suplemento, recuerda las dos acciones simultáneas de esa misma
   guía (tag + sus nutrientes en `tags_cubierto`).
4. **Redacta `nota` de nuevo, desde cero.** No es editar la nota vieja ni
   resumir la instrucción — es una nota nueva que describe la comida ya
   corregida, con el mismo tono de acompañamiento de `prompt-extraccion.md`.
5. Ya no hay `confianza`, `dudas` ni `problemas` en la salida — esto ya pasó
   por revisión humana. Si algo sigue sin quedar claro después de aplicar la
   instrucción, resuélvelo con tu mejor juicio o dilo dentro de la nota en
   prosa; no hay un campo aparte para eso en esta etapa.

## Formato de salida

Un arreglo JSON en `corregidos.json`. Un elemento por entrada de
`revisados.json`, en el mismo orden:

```json
[
  {
    "id": "20260904_131826",
    "titulo": "Huevo Con Nopal + Frijoles + Café Con Leche",
    "icono": "🍳",
    "alimentos": ["3 huevos revueltos con nopal", "1/2 taza de frijoles de olla", "café con leche y agave"],
    "tags_cubierto": ["proteina", "colina", "fibra", "prebioticos", "hierro_vegetal"],
    "tags_atencion": [],
    "tags_contexto": [],
    "tags_suplementos": [],
    "nota": "Ajustado a 3 huevos según corrección; el resto de la comida no cambió."
  }
]
```

- `id` — el mismo de `revisados.json`, para que `aplicar.py --escribir` lo
  pueda emparejar. Nunca lo inventes ni lo cambies.
- `alimentos` — arreglo de strings, un alimento con su cantidad por elemento
  (mismo formato que ya usa `prompt-extraccion.md`).
- `tags_*` — arreglos de strings, sin duplicados, solo del catálogo cerrado.
- No incluyas `fecha`, `hora`, `dia_id`, `comida_id`, `confianza`, `dudas`,
  `problemas` ni `fotos` — `aplicar.py` ya tiene lo que necesita de
  `revisados.json` y arma el resto.

## Antes de entregar

1. ¿Cada elemento tiene el `id` correcto y existe en `revisados.json`?
2. ¿La `instruccion` original quedó aplicada a los datos, no copiada a `nota`?
3. ¿`nota` es una redacción nueva, no la nota vieja ni la instrucción?
4. ¿Los tags existen todos en el catálogo cerrado? ¿Sin duplicados?
5. ¿`sodio_alto` y `sodio_moderado` no coexisten en ningún elemento?
6. ¿Hay comas dentro de `titulo`? (En `alimentos` y `nota` sí se permiten.)
