"""
revisar.py - Fases 3 y 4 del pipeline NutriLog

Valida el borrador contra el catalogo de tags y genera un HTML de revision
para telefono: una comida por pantalla, panel de correccion flotante y
tema claro u oscuro. Exporta decisiones.json.

Uso:
    python revisar.py
    python revisar.py --borrador borrador.json
"""

import base64
import json
import sys
from datetime import datetime
from pathlib import Path

PROCESO = Path(r"C:\dev\nutrilog-proceso")
REDUCIDAS = PROCESO / "reducidas"
MANIFIESTO = PROCESO / "manifiesto.json"
SALIDA = PROCESO / "revision.html"

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

CATALOGO = {
    "cubierto": {
        "proteina", "carbohidratos_integrales", "grasas_saludables", "grasas_mono",
        "fibra", "omega3", "vitamina_a", "vitamina_b6", "vitamina_b12", "vitamina_c",
        "vitamina_d", "vitamina_e", "vitamina_k", "colina", "folato", "hierro_hemo",
        "hierro_vegetal", "magnesio", "potasio", "zinc", "calcio", "selenio",
        "cromo", "biotina", "probioticos", "prebioticos", "antioxidantes",
        "antiinflamatorio", "hidratacion", "enzimas_digestivas", "allicina",
        "capsaicina", "curcumina", "glucosinolatos",
    },
    "atencion": {
        "sodio_alto", "sodio_moderado", "grasas_saturadas", "azucar_alta",
        "sin_vegetales", "ultraprocesados", "fritos", "alcohol",
    },
    "contexto": {
        "comida_elaborada", "comida_rapida", "comida_fuera", "compartido",
        "en_ayunas", "recalentado", "bowl_nocturno",
    },
    "suplementos": {
        "menjurje", "omega3_capsula", "doublex_media", "doublex_completa",
        "d3k2_capsula",
    },
}

NUTRIENTES = {
    "menjurje": ["vitamina_c", "vitamina_e", "vitamina_k", "vitamina_b6", "folato",
                 "potasio", "magnesio", "grasas_mono", "grasas_saludables",
                 "curcumina", "capsaicina", "antiinflamatorio", "antioxidantes",
                 "probioticos", "enzimas_digestivas"],
    "omega3_capsula": ["omega3", "vitamina_e"],
    "doublex_media": ["vitamina_a", "vitamina_b6", "vitamina_b12", "vitamina_c",
                      "vitamina_d", "vitamina_e", "folato", "biotina", "calcio",
                      "magnesio", "zinc", "selenio", "cromo", "antioxidantes",
                      "curcumina", "antiinflamatorio"],
    "d3k2_capsula": ["vitamina_d", "vitamina_k"],
}
NUTRIENTES["doublex_completa"] = NUTRIENTES["doublex_media"]


def validar(comidas, manifiesto):
    problemas, usadas = {}, set()
    validas = {f["archivo"] for f in manifiesto}

    for i, c in enumerate(comidas):
        msgs = []
        for f in c.get("fotos", []):
            if f not in validas:
                msgs.append(f"La foto {f} no está en el manifiesto")
            if f in usadas:
                msgs.append(f"La foto {f} ya se usó en otra comida")
            usadas.add(f)

        if not c.get("fotos"):
            msgs.append("Sin fotos asociadas")
        if not (c.get("titulo") or "").strip():
            msgs.append("Falta el título")
        if not (c.get("nota") or "").strip():
            msgs.append("Falta la nota")
        if not c.get("alimentos"):
            msgs.append("Sin alimentos")
        if isinstance(c.get("alimentos"), str):
            msgs.append("Los alimentos vienen como texto, deben ser una lista")

        for campo, validos in CATALOGO.items():
            tags = c.get(f"tags_{campo}") or []
            if len(tags) != len(set(tags)):
                msgs.append(f"Hay etiquetas repetidas en {campo}")
            for t in tags:
                if t not in validos:
                    msgs.append(f"Etiqueta desconocida en {campo}: {t}")

        at = set(c.get("tags_atencion") or [])
        if "sodio_alto" in at and "sodio_moderado" in at:
            msgs.append("sodio_alto y sodio_moderado no pueden ir juntos")

        cub = set(c.get("tags_cubierto") or [])
        for s in c.get("tags_suplementos") or []:
            faltan = [n for n in NUTRIENTES.get(s, []) if n not in cub]
            if faltan:
                msgs.append(f"{s}: faltan {len(faltan)} nutrientes en la lista de aporte")

        if (c.get("tags_suplementos") or []) and c.get("confianza") != "baja":
            msgs.append("Con suplementos la confianza debe ser baja")

        if msgs:
            problemas[i] = msgs

    return problemas, sorted(validas - usadas)


def b64(nombre):
    ruta = REDUCIDAS / (Path(nombre).stem + ".jpg")
    return base64.b64encode(ruta.read_bytes()).decode("ascii") if ruta.exists() else None


def cuando(fecha, hora):
    if not fecha or not hora:
        return "Sin fecha"
    d = datetime.strptime(fecha, "%Y-%m-%d")
    h, m = hora.split(":")
    h = int(h)
    suf = "am" if h < 12 else "pm"
    h12 = 12 if h % 12 == 0 else h % 12
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}, {h12}:{m}{suf}"


PLANTILLA = r"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Revisar registros</title>
<style>
:root{
  --fondo:#F7F8F8; --papel:#FFFFFF; --tinta:#16181A; --suave:#555C63;
  --linea:#DBDFE2; --tenue:#EDEFF0; --sombra:rgba(20,24,28,.16);
  --si:#1D6B44; --dudo:#875505; --no:#A63125;
  --si-bg:#E5F1E9; --dudo-bg:#FAF1DC; --no-bg:#F9E8E6;
  --sup:#1B5480; --sup-bg:#E3EDF7;
}
html[data-tema="oscuro"]{
  --fondo:#131619; --papel:#1C2126; --tinta:#EDF0F2; --suave:#98A1A9;
  --linea:#2D343A; --tenue:#252B31; --sombra:rgba(0,0,0,.5);
  --si:#63C48F; --dudo:#DFB258; --no:#E97F72;
  --si-bg:#172C22; --dudo-bg:#2E2618; --no-bg:#331E1C;
  --sup:#8FBEE6; --sup-bg:#1A2733;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--fondo);color:var(--tinta);
  font:17px/1.55 -apple-system,"Segoe UI",Roboto,sans-serif;-webkit-text-size-adjust:100%}
.barra{position:sticky;top:0;z-index:30;background:var(--fondo);
  border-bottom:1px solid var(--linea);padding:10px 16px;
  display:flex;justify-content:space-between;align-items:center;gap:10px}
.barra h1{font-size:16px;margin:0;font-weight:650;flex:1}
.avance{font-size:15px;color:var(--suave);white-space:nowrap}
.tema{width:40px;height:40px;flex:0 0 40px;border-radius:10px;border:1px solid var(--linea);
  background:var(--papel);color:var(--tinta);cursor:pointer;display:grid;place-items:center;padding:0}
.tema svg{width:20px;height:20px;stroke:currentColor;fill:none;stroke-width:1.8;
  stroke-linecap:round;stroke-linejoin:round}
.pista{height:3px;background:var(--tenue);position:sticky;top:61px;z-index:29}
.pista i{display:block;height:100%;background:var(--tinta);width:0;transition:width .25s}
main{max-width:640px;margin:0 auto;padding:18px 16px 160px}
body.panel-visible main{padding-bottom:340px}
.cuando{font-size:15px;color:var(--suave);margin:0 0 4px}
.titulo{font-size:23px;line-height:1.25;margin:0;font-weight:650}
.sello{display:inline-block;margin-top:10px;font-size:14px;padding:3px 11px;
  border-radius:16px;font-weight:600}
.sello.baja{background:var(--no-bg);color:var(--no)}
.sello.media{background:var(--dudo-bg);color:var(--dudo)}
.sello.alta{background:var(--si-bg);color:var(--si)}
.fotos{margin-top:16px}
.fotos img{width:100%;border-radius:12px;margin-bottom:10px;display:block;
  border:1px solid var(--linea)}
.bloque{background:var(--papel);border:1px solid var(--linea);border-radius:12px;
  padding:16px;margin:16px 0}
.bloque h3{font-size:15px;color:var(--suave);margin:0 0 10px;font-weight:600}
.comio{margin:0;padding-left:20px}
.comio li{margin:5px 0}
.grupo{margin:12px 0}
.grupo:first-child{margin-top:0}
.grupo b{display:block;font-size:14px;color:var(--suave);margin-bottom:6px;font-weight:600}
.eti{display:inline-block;font-size:15px;padding:3px 10px;border-radius:6px;
  background:var(--tenue);margin:0 5px 5px 0}
.eti.atencion{background:var(--no-bg);color:var(--no)}
.eti.suplementos{background:var(--sup-bg);color:var(--sup)}
.nada{color:var(--suave)}
.nota{margin:0;font-size:16px}
.dudas,.fallos{border-radius:12px;padding:14px 16px;margin:16px 0;border:1px solid}
.dudas{background:var(--dudo-bg);border-color:var(--dudo)}
.dudas h3{color:var(--dudo)}
.fallos{background:var(--no-bg);border-color:var(--no)}
.fallos h3{color:var(--no)}
.dudas ul,.fallos ul{margin:0;padding-left:20px}
.dudas li,.fallos li{margin:4px 0}
.navega{display:flex;gap:10px;margin-top:24px}
.navega button{flex:1;min-height:48px;font:600 16px/1 inherit;border-radius:12px;
  border:1px solid var(--linea);background:var(--papel);color:var(--tinta);cursor:pointer}
.navega button[disabled]{opacity:.4}

.panel{position:fixed;left:0;right:0;bottom:76px;z-index:25;display:none;
  background:var(--papel);border-top:2px solid var(--dudo);
  box-shadow:0 -6px 20px var(--sombra)}
body.panel-visible .panel{display:block}
.panel-in{max-width:640px;margin:0 auto;padding:12px 16px 14px}
.panel-cab{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.panel-cab span{font-size:15px;font-weight:600;color:var(--dudo)}
.panel-cab button{background:none;border:none;color:var(--suave);font:600 15px/1 inherit;
  padding:6px 8px;cursor:pointer}
textarea{width:100%;height:84px;font:16px/1.45 inherit;padding:11px;
  border:1px solid var(--linea);border-radius:10px;background:var(--fondo);
  color:var(--tinta);resize:none;display:block}
textarea:focus{outline:2px solid var(--dudo);outline-offset:1px}
.panel-pie{font-size:13px;color:var(--suave);margin:8px 0 0}

.acciones{position:fixed;left:0;right:0;bottom:0;z-index:26;background:var(--fondo);
  border-top:1px solid var(--linea);
  padding:12px 16px calc(12px + env(safe-area-inset-bottom))}
.acciones div{display:flex;gap:10px;max-width:640px;margin:0 auto}
.acciones button{flex:1;min-height:52px;font:600 16px/1 inherit;border-radius:12px;
  border:2px solid;background:var(--papel);cursor:pointer}
.acciones button:focus-visible{outline:3px solid var(--tinta);outline-offset:2px}
.b-si{border-color:var(--si);color:var(--si)}
.b-si.on{background:var(--si);color:var(--papel)}
.b-dudo{border-color:var(--dudo);color:var(--dudo)}
.b-dudo.on{background:var(--dudo);color:var(--papel)}
.b-no{border-color:var(--no);color:var(--no);flex:0 0 82px}
.b-no.on{background:var(--no);color:var(--papel)}
.cierre{text-align:center;padding:36px 0}
.cierre h2{font-size:24px;margin:0 0 20px}
.cuenta{font-size:17px;margin:6px 0}
.bajar{margin-top:28px;min-height:56px;width:100%;font:650 17px/1 inherit;
  border-radius:12px;border:none;background:var(--tinta);color:var(--fondo);cursor:pointer}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style></head>
<body>
<div class="barra">
  <h1>Revisar registros</h1>
  <span class="avance" id="avance"></span>
  <button class="tema" id="tema" onclick="cambiarTema()" aria-label="Cambiar tema"></button>
</div>
<div class="pista"><i id="pista"></i></div>
<main id="lienzo"></main>

<div class="panel" id="panel"><div class="panel-in">
  <div class="panel-cab">
    <span>Qué hay que corregir</span>
    <button onclick="ocultarPanel()">Ocultar</button>
  </div>
  <textarea id="txt" oninput="anotar(this.value)"
    placeholder="Escribe rápido. Ej: eran 3 huevos, fue compartido, el queso era manchego"></textarea>
  <p class="panel-pie">No llega a tu registro. Se corrigen los datos y la nota se vuelve a redactar.</p>
</div></div>

<div class="acciones" id="acciones"><div>
  <button class="b-si" id="bSi" onclick="marcar('aprobada')">Aprobar</button>
  <button class="b-dudo" id="bDudo" onclick="marcar('corregir')">Corregir</button>
  <button class="b-no" id="bNo" onclick="marcar('quitada')">Quitar</button>
</div></div>

<script>
const D = __DATOS__;
const LOTE = "__LOTE__";
let n = 0, est = {};
try { est = JSON.parse(localStorage.getItem("nutrilog:"+LOTE) || "{}"); } catch(e){ est = {}; }
function guardar(){ try { localStorage.setItem("nutrilog:"+LOTE, JSON.stringify(est)); } catch(e){} }
function esc(s){ return String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

const SOL = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.2 5.2l1.4 1.4M17.4 17.4l1.4 1.4M18.8 5.2l-1.4 1.4M6.6 17.4l-1.4 1.4"/></svg>';
const LUNA = '<svg viewBox="0 0 24 24"><path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/></svg>';

function aplicarTema(t){
  document.documentElement.setAttribute("data-tema", t);
  document.getElementById("tema").innerHTML = (t === "oscuro") ? SOL : LUNA;
  try { localStorage.setItem("nutrilog:tema", t); } catch(e){}
}
function cambiarTema(){
  const actual = document.documentElement.getAttribute("data-tema");
  aplicarTema(actual === "oscuro" ? "claro" : "oscuro");
}
(function(){
  let t = null;
  try { t = localStorage.getItem("nutrilog:tema"); } catch(e){}
  if(!t) t = window.matchMedia("(prefers-color-scheme: dark)").matches ? "oscuro" : "claro";
  aplicarTema(t);
})();

function etis(l, k){
  if(!l || !l.length) return '<span class="nada">ninguna</span>';
  return l.map(t => '<span class="eti '+k+'">'+esc(t)+'</span>').join('');
}

function mostrarPanel(){
  document.body.classList.add("panel-visible");
  document.getElementById("txt").focus();
}
function ocultarPanel(){
  document.body.classList.remove("panel-visible");
}

function pintar(){
  if(n >= D.length){ cierre(); return; }
  const c = D[n], e = est[c.id] || {};
  document.getElementById("acciones").style.display = "block";
  document.getElementById("avance").textContent = (n+1) + " de " + D.length;
  document.getElementById("pista").style.width = (n / D.length * 100) + "%";

  let h = '<p class="cuando">' + esc(c.cuando) + '</p>';
  h += '<h2 class="titulo">' + esc(c.icono + " " + c.titulo) + '</h2>';
  h += '<span class="sello ' + c.confianza + '">confianza ' + c.confianza + '</span>';
  h += '<div class="fotos">' + c.fotos.map(f =>
    '<img src="data:image/jpeg;base64,'+f+'" alt="Foto de la comida">').join('') + '</div>';
  if(c.problemas.length)
    h += '<div class="fallos"><h3>Revisa esto antes de aprobar</h3><ul>' +
      c.problemas.map(p => '<li>'+esc(p)+'</li>').join('') + '</ul></div>';
  h += '<div class="bloque"><h3>Qué comiste</h3><ul class="comio">' +
    c.alimentos.map(a => '<li>'+esc(a)+'</li>').join('') + '</ul></div>';
  h += '<div class="bloque">' +
    '<div class="grupo"><b>Aporta</b>' + etis(c.cubierto,'cubierto') + '</div>' +
    '<div class="grupo"><b>Atención</b>' + etis(c.atencion,'atencion') + '</div>' +
    '<div class="grupo"><b>Contexto</b>' + etis(c.contexto,'contexto') + '</div>' +
    '<div class="grupo"><b>Suplementos</b>' + etis(c.suplementos,'suplementos') + '</div></div>';
  h += '<div class="bloque"><h3>Nota</h3><p class="nota">' + esc(c.nota) + '</p></div>';
  if(c.dudas.length)
    h += '<div class="dudas"><h3>No pudo determinar</h3><ul>' +
      c.dudas.map(d => '<li>'+esc(d)+'</li>').join('') + '</ul></div>';
  h += '<div class="navega"><button onclick="ir(-1)"' + (n===0?' disabled':'') + '>Anterior</button>' +
    '<button onclick="ir(1)">' + (n===D.length-1?'Terminar':'Siguiente') + '</button></div>';

  document.getElementById("lienzo").innerHTML = h;
  document.getElementById("txt").value = e.instruccion || "";
  if(e.decision === "corregir") document.body.classList.add("panel-visible");
  else document.body.classList.remove("panel-visible");
  window.scrollTo(0,0);
  reflejar();
}

function reflejar(){
  const e = est[D[n].id] || {};
  document.getElementById("bSi").classList.toggle("on", e.decision === "aprobada");
  document.getElementById("bDudo").classList.toggle("on", e.decision === "corregir");
  document.getElementById("bNo").classList.toggle("on", e.decision === "quitada");
}

function marcar(d){
  const c = D[n], prev = est[c.id] || {};
  est[c.id] = { decision: d, instruccion: prev.instruccion || "" };
  guardar();
  if(d === "corregir"){ mostrarPanel(); }
  else { ocultarPanel(); setTimeout(() => ir(1), 180); }
  reflejar();
}

function anotar(v){
  est[D[n].id] = { decision: "corregir", instruccion: v };
  guardar();
  reflejar();
}

function ir(p){ n = Math.max(0, Math.min(D.length, n + p)); pintar(); }

function cierre(){
  document.getElementById("acciones").style.display = "none";
  document.body.classList.remove("panel-visible");
  document.getElementById("pista").style.width = "100%";
  document.getElementById("avance").textContent = "";
  const v = Object.values(est), c = t => v.filter(x => x.decision === t).length;
  const pend = D.length - v.filter(x => x.decision).length;
  let h = '<div class="cierre"><h2>Revisión terminada</h2>';
  h += '<p class="cuenta">' + c("aprobada") + ' aprobadas</p>';
  h += '<p class="cuenta">' + c("corregir") + ' con correcciones</p>';
  h += '<p class="cuenta">' + c("quitada") + ' quitadas</p>';
  if(pend) h += '<p class="cuenta">' + pend + ' sin decidir</p>';
  h += '<button class="bajar" onclick="bajar()">Descargar decisiones</button>';
  h += '<div class="navega"><button onclick="ir(-1)">Volver a revisar</button></div></div>';
  document.getElementById("lienzo").innerHTML = h;
  window.scrollTo(0,0);
}

function bajar(){
  const salida = D.map(c => ({
    id: c.id, fotos: c.fotos_nombres,
    decision: (est[c.id] || {}).decision || "sin_decidir",
    instruccion: (est[c.id] || {}).instruccion || ""
  }));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(salida, null, 2)],
    {type:"application/json"}));
  a.download = "decisiones.json";
  a.click();
}

pintar();
</script>
</body></html>"""


def main():
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

    problemas, sueltas = validar(comidas, manifiesto)

    datos = []
    for i, c in enumerate(comidas):
        fotos = c.get("fotos", [])
        meta = por_archivo.get(fotos[0], {}) if fotos else {}
        datos.append({
            "id": f"c{i}",
            "cuando": cuando(meta.get("fecha", ""), meta.get("hora", "")),
            "titulo": c.get("titulo", ""),
            "icono": c.get("icono", ""),
            "alimentos": c.get("alimentos", []),
            "cubierto": c.get("tags_cubierto", []),
            "atencion": c.get("tags_atencion", []),
            "contexto": c.get("tags_contexto", []),
            "suplementos": c.get("tags_suplementos", []),
            "nota": c.get("nota", ""),
            "confianza": c.get("confianza", "media"),
            "dudas": c.get("dudas", []),
            "problemas": problemas.get(i, []),
            "fotos": [b for b in (b64(f) for f in fotos) if b],
            "fotos_nombres": fotos,
        })

    lote = datetime.now().strftime("%Y%m%d_%H%M%S")
    html = PLANTILLA.replace("__DATOS__", json.dumps(datos, ensure_ascii=False))
    html = html.replace("__LOTE__", lote)
    SALIDA.write_text(html, encoding="utf-8")

    print(f"Comidas: {len(comidas)}")
    print(f"Con problemas: {len(problemas)}")
    for i, msgs in problemas.items():
        print(f"\n  Comida {i + 1}: {comidas[i].get('titulo', '')}")
        for m in msgs:
            print(f"    - {m}")
    if sueltas:
        print(f"\nFotos sin comida asignada: {len(sueltas)}")
        for f in sueltas:
            print(f"    - {f}")
    print(f"\nRevision: {SALIDA}")


if __name__ == "__main__":
    main()
