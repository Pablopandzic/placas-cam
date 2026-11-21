import os
import shutil
import subprocess
import sys
BASE = os.path.dirname(os.path.abspath(__file__))

DIRS = [
    "assets/fuentes",
    "core",
    "config",
    "salida",
    "web",
]

FILES = {}

FILES["config/maquina.yaml"] = """placa_default:
  ancho_mm: 600.0
  alto_mm: 400.0
  margen_seguridad_mm: 22.0
  origen: "inferior_izquierda"

herramienta:
  nombre: "PCD_70deg_0.4mm"
  angulo_grados: 70.0
  punta_mm: 0.4
  profundidad_z_mm: 0.5
  ancho_corte_superficie_mm: 1.10

dxf:
  version: "R2000"
  tolerancia_aplanado_mm: 0.002
  tolerancia_arcos_mm: 0.01

capas:
  contorno: "01_CONTORNO_PLACA"
  texto: "02_TEXTO_GRABADO_Z05"
  simbolos: "03_SIMBOLOS_GRABADO_Z05"
  ubicacion: "04_UBICACION_GRABADO_Z05"
"""

FILES["core/__init__.py"] = ""

FILES["core/text_geom.py"] = """import math
import unicodedata
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union

FEATURES = {"kern": True, "liga": False, "clig": False, "dlig": False, "calt": False}

class FlattenPen(BasePen):
    def __init__(self, glyphset, tol):
        super().__init__(glyphset)
        self.tol = tol
        self.contours = []
        self.cur = []

    def _moveTo(self, p):
        self.cur = [p]

    def _lineTo(self, p):
        if p != self.cur[-1]:
            self.cur.append(p)

    def _curveToOne(self, p1, p2, p3):
        p0 = self.cur[-1]
        m = max(
            math.hypot(p0[0] - 2*p1[0] + p2[0], p0[1] - 2*p1[1] + p2[1]),
            math.hypot(p1[0] - 2*p2[0] + p3[0], p1[1] - 2*p2[1] + p3[1])
        )
        n = max(1, math.ceil(math.sqrt(0.75 * m / self.tol)))
        for i in range(1, n + 1):
            t = i / n
            u = 1 - t
            self.cur.append((
                u**3*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t**3*p3[0],
                u**3*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t**3*p3[1]
            ))

    def _closePath(self):
        if len(self.cur) >= 3:
            self.contours.append(self.cur)
        self.cur = []

    def _endPath(self):
        self.cur = []

def _winding(x, y, rings):
    w = 0
    for r in rings:
        for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]):
            side = (x2 - x1) * (y - y1) - (x - x1) * (y2 - y1)
            if y1 <= y < y2 and side > 0:
                w += 1
            elif y2 <= y < y1 and side < 0:
                w -= 1
    return w

def nonzero_fill(rings, min_area=1e-6):
    lines = unary_union([LineString(r + [r[0]]) for r in rings])
    faces = [f for f in polygonize(lines) if f.area > min_area]
    keep = [f for f in faces if _winding(*f.representative_point().coords[0], rings) != 0]
    return unary_union(keep)

def cap_height_units(tt, gs):
    bp = BoundsPen(gs)
    gs[tt.getBestCmap()[ord("H")]].draw(bp)
    return bp.bounds[3]

def text_to_geom(font_path: str, text: str, cap_height_mm: float, tol_mm: float = 0.002):
    text = unicodedata.normalize("NFC", text)
    if not text.strip():
        return None
    tt = TTFont(font_path)
    gs = tt.getGlyphSet()
    cap = cap_height_units(tt, gs)
    s = cap_height_mm / cap

    with open(font_path, "rb") as f:
        face = hb.Face(hb.Blob(f.read()))
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hb.Font(face), buf, FEATURES)

    x, glyphs = 0, []
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        if info.codepoint == 0:
            raise ValueError(f"Carácter no soportado por la fuente en: {text!r}")
        pen = FlattenPen(gs, tol_mm / s)
        gs[tt.getGlyphName(info.codepoint)].draw(pen)
        ox, oy = x + pos.x_offset, pos.y_offset
        rings = [[((px + ox) * s, (py + oy) * s) for px, py in c] for c in pen.contours]
        if rings:
            glyphs.append(nonzero_fill(rings))
        x += pos.x_advance

    if not glyphs:
        return None
    return unary_union(glyphs)
"""

FILES["core/arcfit.py"] = """import math

def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])

def _circle(a, b, c):
    d = 2 * (a[0]*(b[1]-c[1]) + b[0]*(c[1]-a[1]) + c[0]*(a[1]-b[1]))
    if abs(d) < 1e-12:
        return None
    sa, sb, sc = a[0]**2+a[1]**2, b[0]**2+b[1]**2, c[0]**2+c[1]**2
    ux = (sa*(b[1]-c[1]) + sb*(c[1]-a[1]) + sc*(a[1]-b[1])) / d
    uy = (sa*(c[0]-b[0]) + sb*(a[0]-c[0]) + sc*(b[0]-a[0])) / d
    return ux, uy, math.hypot(a[0]-ux, a[1]-uy)

def _line_ok(pts, tol):
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    L = math.hypot(x1-x0, y1-y0)
    return L > 1e-9 and all(
        abs((x1-x0)*(y0-y) - (x0-x)*(y1-y0)) / L <= tol for x, y in pts[1:-1]
    )

def _arc_bulge(pts, tol, rmax):
    mid = pts[len(pts)//2]
    c = _circle(pts[0], mid, pts[-1])
    if not c or c[2] > rmax:
        return None
    ux, uy, R = c
    if any(abs(math.hypot(x-ux, y-uy) - R) > tol for x, y in pts):
        return None
    ccw = _cross(pts[0], mid, pts[-1]) > 0
    a0 = math.atan2(pts[0][1]-uy, pts[0][0]-ux)
    def sweep(p):
        a = math.atan2(p[1]-uy, p[0]-ux)
        return (a - a0) % (2*math.pi) if ccw else (a0 - a) % (2*math.pi)
    sw = [sweep(p) for p in pts[1:]]
    if any(b < a for a, b in zip(sw, sw[1:])) or sw[-1] > math.pi:
        return None
    return math.tan((sw[-1] if ccw else -sw[-1]) / 4)

def fit_ring(ring, tol=0.01, rmax=5000.0, max_window=400):
    pts = list(ring) + [ring[0]]
    out, i, n = [], 0, len(pts)
    while i < n - 1:
        j_best, b_best, j = i + 1, 0.0, i + 2
        while j < n and j - i <= max_window:
            seg = pts[i:j+1]
            b = 0.0 if _line_ok(seg, tol) else _arc_bulge(seg, tol, rmax)
            if b is None:
                break
            j_best, b_best = j, b
            j += 1
        out.append((pts[i][0], pts[i][1], b_best))
        i = j_best
    return out
"""

FILES["core/dxf_writer.py"] = """import os
import ezdxf
from ezdxf import units
from ezdxf.upright import upright_all
from shapely.geometry.polygon import orient
from core.arcfit import fit_ring

LAYER_COLORS = {
    "01_CONTORNO_PLACA": 7,
    "02_TEXTO_GRABADO_Z05": 1,
    "03_SIMBOLOS_GRABADO_Z05": 5,
    "04_UBICACION_GRABADO_Z05": 3,
}

def write_dxf(path: str, layer_geoms: dict, tol: float = 0.01, version: str = "R2000"):
    doc = ezdxf.new(version, setup=False)
    doc.units = units.MM
    doc.header["$MEASUREMENT"] = 1
    for name, color in LAYER_COLORS.items():
        doc.layers.add(name, color=color)

    msp = doc.modelspace()
    for layer, geom in layer_geoms.items():
        if geom is None or geom.is_empty:
            continue
        polys = geom.geoms if hasattr(geom, "geoms") else [geom]
        for poly in polys:
            if poly.is_empty or poly.area < 1e-6:
                continue
            poly = orient(poly, 1.0)
            for ring in (poly.exterior, *poly.interiors):
                pts = fit_ring(list(ring.coords)[:-1], tol)
                msp.add_lwpolyline(pts, format="xyb", close=True, dxfattribs={"layer": layer})

    upright_all(msp)
    doc.audit()
    tmp = path + ".tmp"
    doc.saveas(tmp)
    os.replace(tmp, path)
"""

FILES["core/layout.py"] = """import os
from shapely.geometry import box, Polygon
from shapely.affinity import translate, scale
from shapely.ops import unary_union
from core.text_geom import text_to_geom

FONT_SERIF = "assets/fuentes/SerifMemorial.otf"
FONT_SANS = "assets/fuentes/micross.ttf"

def _get_serif_font():
    return FONT_SERIF if os.path.exists(FONT_SERIF) else FONT_SANS

def _center_x(geom, target_x=300.0):
    if geom is None or geom.is_empty:
        return geom
    minx, _, maxx, _ = geom.bounds
    cx = (minx + maxx) / 2.0
    return translate(geom, xoff=target_x - cx)

def _align_bottom_y(geom, target_y):
    if geom is None or geom.is_empty:
        return geom
    _, miny, _, _ = geom.bounds
    return translate(geom, yoff=target_y - miny)

def _cruz_latina(altura_mm=85.0):
    # Cruz hueca con espesor de pared limpio para grabado
    w = altura_mm * 0.62
    brazo = altura_mm * 0.21
    y_cruz = altura_mm * 0.64
    outer = unary_union([
        box(-brazo/2, 0, brazo/2, altura_mm),
        box(-w/2, y_cruz - brazo/2, w/2, y_cruz + brazo/2)
    ])
    inner = outer.buffer(-3.2, join_style="mitre")
    return outer.difference(inner)

def _estrella_david(altura_mm=78.0):
    import math
    R = altura_mm / 2.0
    r_in = R * 0.56
    t1_out = [(R*math.cos(math.radians(90 + 120*i)), R*math.sin(math.radians(90 + 120*i))) for i in range(3)]
    t2_out = [(R*math.cos(math.radians(-90 + 120*i)), R*math.sin(math.radians(-90 + 120*i))) for i in range(3)]
    outer = unary_union([Polygon(t1_out), Polygon(t2_out)])
    inner = outer.buffer(-3.0, join_style="mitre")
    return outer.difference(inner)

def build_plate_geometries(data: dict):
    W, H = 600.0, 400.0
    contorno = box(0, 0, W, H)
    font_main = _get_serif_font()

    encabezado = data.get("encabezado", "Q.E.P.D.").strip().upper()
    nombre = data.get("nombre", "").strip().upper()
    fecha_nac = data.get("fecha_nac", "").strip()
    fecha_fall = data.get("fecha_fall", "").strip()
    simbolo_izq = data.get("simbolo_izq", "cruz")
    simbolo_der = data.get("simbolo_der", "ninguno")
    sector = data.get("sector", "").strip().upper()
    seccion = data.get("seccion", "").strip()
    parcela = data.get("parcela", "").strip()

    textos = []
    # 1. Encabezado (Y = 325 mm)
    if encabezado:
        g_enc = text_to_geom(font_main, encabezado, cap_height_mm=16.0)
        g_enc = _align_bottom_y(_center_x(g_enc, 300.0), 325.0)
        textos.append(g_enc)

    # 2. Nombre completo (Y = 282 mm) con auto-escalado según ancho disponible
    ancho_max_nombre = 530.0
    if simbolo_izq != "ninguno":
        ancho_max_nombre -= 75.0
    if simbolo_der != "ninguno":
        ancho_max_nombre -= 75.0

    g_nom = None
    if nombre:
        h_nom = 23.0
        g_nom = text_to_geom(font_main, nombre, cap_height_mm=h_nom)
        w_actual = g_nom.bounds[2] - g_nom.bounds[0]
        if w_actual > ancho_max_nombre:
            factor = ancho_max_nombre / w_actual
            g_nom = scale(g_nom, xfact=factor, yfact=factor, origin=(0, 0))
        g_nom = _align_bottom_y(_center_x(g_nom, 300.0), 282.0)
        textos.append(g_nom)

    # 3. Fechas (Y = 246 mm)
    fechas_str = ""
    if fecha_nac and fecha_fall:
        fechas_str = f"{fecha_nac}    {fecha_fall}"
    elif fecha_nac or fecha_fall:
        fechas_str = fecha_nac or fecha_fall

    if fechas_str:
        g_fec = text_to_geom(font_main, fechas_str, cap_height_mm=17.5)
        g_fec = _align_bottom_y(_center_x(g_fec, 300.0), 246.0)
        textos.append(g_fec)

    # 4. Símbolos laterales (ajustados al espacio libre respecto al nombre)
    simbolos = []
    nombre_minx = g_nom.bounds[0] if g_nom else 140.0
    nombre_maxx = g_nom.bounds[2] if g_nom else 460.0

    if simbolo_izq == "cruz":
        espacio_izq = max(45.0, nombre_minx - 32.0)
        alt_cruz = min(86.0, espacio_izq * 1.15)
        cruz = _cruz_latina(alt_cruz)
        cx_target = (22.0 + nombre_minx) / 2.0
        cruz = _align_bottom_y(_center_x(cruz, cx_target), 255.0)
        simbolos.append(cruz)

    if simbolo_der == "estrella":
        espacio_der = max(45.0, (W - 32.0) - nombre_maxx)
        alt_est = min(80.0, espacio_der * 1.05)
        est = _estrella_david(alt_est)
        cx_target = (nombre_maxx + (W - 22.0)) / 2.0
        est = _align_bottom_y(_center_x(est, cx_target), 258.0)
        simbolos.append(est)
    elif simbolo_der == "cruz":
        espacio_der = max(45.0, (W - 32.0) - nombre_maxx)
        alt_cruz = min(86.0, espacio_der * 1.15)
        cruz = _cruz_latina(alt_cruz)
        cx_target = (nombre_maxx + (W - 22.0)) / 2.0
        cruz = _align_bottom_y(_center_x(cruz, cx_target), 255.0)
        simbolos.append(cruz)

    # 5. Ubicación abajo izquierda (Y = 20 mm, X = 22 mm)
    ubicacion_geoms = []
    x_cursor = 22.0
    if sector:
        g_sec = text_to_geom(FONT_SANS, sector, cap_height_mm=15.0)
        g_sec = translate(g_sec, xoff=x_cursor - g_sec.bounds[0], yoff=20.0 - g_sec.bounds[1])
        ubicacion_geoms.append(g_sec)
        x_cursor = g_sec.bounds[2] + 7.0

    num_str = f"{seccion}.{parcela}".strip(".")
    if num_str:
        g_num = text_to_geom(FONT_SANS, num_str, cap_height_mm=11.5)
        g_num = translate(g_num, xoff=x_cursor - g_num.bounds[0], yoff=20.0 - g_num.bounds[1])
        ubicacion_geoms.append(g_num)

    return {
        "01_CONTORNO_PLACA": contorno,
        "02_TEXTO_GRABADO_Z05": unary_union(textos) if textos else None,
        "03_SIMBOLOS_GRABADO_Z05": unary_union(simbolos) if simbolos else None,
        "04_UBICACION_GRABADO_Z05": unary_union(ubicacion_geoms) if ubicacion_geoms else None,
    }
"""

FILES["app.py"] = """import os
import re
import json
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from core.layout import build_plate_geometries
from core.dxf_writer import write_dxf

app = FastAPI(title="Placas CAM - Configurador Web-to-DXF")

class OrdenPlaca(BaseModel):
    orden_id: str = "00001"
    encabezado: str = "Q.E.P.D."
    nombre: str
    fecha_nac: str = ""
    fecha_fall: str = ""
    simbolo_izq: str = "cruz"
    simbolo_der: str = "ninguno"
    sector: str = ""
    seccion: str = ""
    parcela: str = ""

def _geom_to_svg_paths(geom, color="#111111"):
    if geom is None or geom.is_empty:
        return ""
    polys = geom.geoms if hasattr(geom, "geoms") else [geom]
    paths = []
    for p in polys:
        if p.is_empty:
            continue
        d = []
        ext = list(p.exterior.coords)
        d.append("M " + " L ".join(f"{x:.2f},{400.0 - y:.2f}" for x, y in ext) + " Z")
        for interior in p.interiors:
            pts = list(interior.coords)
            d.append("M " + " L ".join(f"{x:.2f},{400.0 - y:.2f}" for x, y in pts) + " Z")
        paths.append(f'<path d="{" ".join(d)}" fill="{color}" fill-rule="evenodd"/>')
    return "\\n".join(paths)

@app.get("/", response_class=HTMLResponse)
def index():
    with open("web/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/preview")
def preview_svg(orden: OrdenPlaca):
    try:
        geoms = build_plate_geometries(orden.model_dump())
        svg_texto = _geom_to_svg_paths(geoms["02_TEXTO_GRABADO_Z05"], "#111111")
        svg_simb = _geom_to_svg_paths(geoms["03_SIMBOLOS_GRABADO_Z05"], "#1d4ed8")
        svg_ubic = _geom_to_svg_paths(geoms["04_UBICACION_GRABADO_Z05"], "#111111")
        svg = f'''<svg viewBox="0 0 600 400" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;background:#f8fafc;border:2px solid #94a3b8;box-shadow:0 4px 12px rgba(0,0,0,0.08)">
            <rect x="0" y="0" width="600" height="400" fill="#ffffff" stroke="#334155" stroke-width="1.5"/>
            <rect x="22" y="22" width="556" height="356" fill="none" stroke="#e2e8f0" stroke-dasharray="4 4" stroke-width="0.8"/>
            {svg_texto}
            {svg_simb}
            {svg_ubic}
        </svg>'''
        return {"svg": svg, "serif_activa": os.path.exists("assets/fuentes/SerifMemorial.otf")}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/generar-dxf")
def generar_dxf(orden: OrdenPlaca):
    try:
        geoms = build_plate_geometries(orden.model_dump())
        safe_name = re.sub(r"[^A-Z0-9_]", "", orden.nombre.upper().replace(" ", "_")) or "PLACA"
        safe_id = re.sub(r"[^A-Z0-9_-]", "", orden.orden_id.upper()) or "ORD"
        filename = f"{safe_id}_{safe_name}.dxf"
        out_path = os.path.join("salida", filename)
        write_dxf(out_path, geoms)
        return FileResponse(out_path, media_type="application/dxf", filename=filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/ocr-orden")
async def ocr_orden(file: UploadFile = File(...)):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="Falta configurar GEMINI_API_KEY en Windows para leer fotos.")
    from google import genai
    from google.genai import types
    img_bytes = await file.read()
    client = genai.Client(api_key=api_key)
    prompt = '''Extrae los datos de esta orden de confección de placa funeraria en JSON puro:
    {
      "orden_id": "numero de orden",
      "encabezado": "Q.E.P.D. o EN AMOROSA MEMORIA DE",
      "nombre": "NOMBRE Y APELLIDO LITERAL EN MAYUSCULAS",
      "fecha_nac": "DD.MM.AAAA",
      "fecha_fall": "DD.MM.AAAA",
      "simbolo_izq": "cruz o ninguno",
      "simbolo_der": "estrella o cruz o ninguno",
      "sector": "letra de sector",
      "seccion": "numero de seccion",
      "parcela": "numero de parcela"
    }'''
    res = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[types.Part.from_bytes(data=img_bytes, mime_type=file.content_type), prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    return json.loads(res.text)
"""

FILES["web/index.html"] = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Placas CAM 600x400 - Generador DXF</title>
<style>
  body { font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }
  .container { max-width: 1280px; margin: 0 auto; display: grid; grid-template-columns: 380px 1fr; gap: 24px; }
  .card { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }
  h2 { margin-top: 0; font-size: 18px; color: #38bdf8; }
  label { display: block; font-size: 12px; color: #94a3b8; margin-top: 12px; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.05em; }
  input, select { width: 100%; box-sizing: border-box; padding: 9px 12px; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: #fff; font-size: 14px; }
  .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .row3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
  button { width: 100%; margin-top: 18px; padding: 12px; border: none; border-radius: 8px; background: #2563eb; color: white; font-weight: 600; font-size: 15px; cursor: pointer; }
  button:hover { background: #1d4ed8; }
  .btn-ocr { background: #0d9488; margin-top: 0; margin-bottom: 12px; font-size: 13px; padding: 9px; }
  .warn { background: #78350f; color: #fde68a; padding: 10px; border-radius: 6px; font-size: 12px; margin-bottom: 12px; display: none; }
  .meta { font-size: 12px; color: #94a3b8; margin-top: 10px; display: flex; justify-content: space-between; }
</style>
</head>
<body>
<div class="container">
  <div class="card">
    <h2>Orden de Placa (600x400 mm)</h2>
    <input type="file" id="fotoInput" accept="image/*" style="display:none" onchange="subirFoto()">
    <button class="btn-ocr" onclick="document.getElementById('fotoInput').click()">📷 Autocompletar desde Foto de Orden</button>

    <div class="row">
      <div><label>N° Orden</label><input id="orden_id" value="59901"></div>
      <div><label>Encabezado</label><input id="encabezado" value="Q.E.P.D." oninput="actualizar()"></div>
    </div>

    <label>Nombre Completo</label>
    <input id="nombre" value="ANGEL COHEN AAGAARD" oninput="actualizar()">

    <div class="row">
      <div><label>Fecha Nacimiento</label><input id="fecha_nac" value="03.09.1960" oninput="actualizar()"></div>
      <div><label>Fecha Defunción</label><input id="fecha_fall" value="13.12.2025" oninput="actualizar()"></div>
    </div>

    <div class="row">
      <div>
        <label>Símbolo Izquierda</label>
        <select id="simbolo_izq" onchange="actualizar()">
          <option value="cruz" selected>Cruz Latina</option>
          <option value="ninguno">Ninguno</option>
        </select>
      </div>
      <div>
        <label>Símbolo Derecha</label>
        <select id="simbolo_der" onchange="actualizar()">
          <option value="ninguno" selected>Ninguno</option>
          <option value="estrella">Estrella de David</option>
          <option value="cruz">Cruz Latina</option>
        </select>
      </div>
    </div>

    <div class="row3">
      <div><label>Sector</label><input id="sector" value="J" oninput="actualizar()"></div>
      <div><label>Sección</label><input id="seccion" value="39" oninput="actualizar()"></div>
      <div><label>Parcela</label><input id="parcela" value="73" oninput="actualizar()"></div>
    </div>

    <button onclick="descargarDXF()">⬇ Generar y Descargar DXF</button>
  </div>

  <div class="card">
    <h2>Vista Previa CAM Escala 1:1 (600 x 400 mm — Profundidad Z = 0.5 mm)</h2>
    <div id="fontWarn" class="warn">⚠️ Aún no copiaste <b>SerifMemorial.otf</b> en <code>assets/fuentes/</code>. Mostrando respaldo temporal.</div>
    <div id="canvas"></div>
    <div class="meta">
      <span>Fresa: PCD 70° punta 0.4 mm (corte sup. 1.10 mm)</span>
      <span>Capas: 01_CONTORNO | 02_TEXTO | 03_SIMBOLOS | 04_UBICACION</span>
    </div>
  </div>
</div>

<script>
function payload() {
  return {
    orden_id: document.getElementById('orden_id').value,
    encabezado: document.getElementById('encabezado').value,
    nombre: document.getElementById('nombre').value,
    fecha_nac: document.getElementById('fecha_nac').value,
    fecha_fall: document.getElementById('fecha_fall').value,
    simbolo_izq: document.getElementById('simbolo_izq').value,
    simbolo_der: document.getElementById('simbolo_der').value,
    sector: document.getElementById('sector').value,
    seccion: document.getElementById('seccion').value,
    parcela: document.getElementById('parcela').value
  };
}

let timer;
function actualizar() {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    const res = await fetch('/api/preview', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload())
    });
    const data = await res.json();
    if (res.ok) {
      document.getElementById('canvas').innerHTML = data.svg;
      document.getElementById('fontWarn').style.display = data.serif_activa ? 'none' : 'block';
    }
  }, 150);
}

async function descargarDXF() {
  const res = await fetch('/api/generar-dxf', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload())
  });
  if (!res.ok) { alert('Error al generar DXF'); return; }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${payload().orden_id}_${payload().nombre.replace(/\\s+/g,'_')}.dxf`;
  a.click();
}

async function subirFoto() {
  const f = document.getElementById('fotoInput').files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append('file', f);
  const res = await fetch('/api/ocr-orden', { method: 'POST', body: fd });
  const data = await res.json();
  if (!res.ok) { alert(data.detail || 'Error leyendo foto'); return; }
  for (const k of Object.keys(data)) {
    if (document.getElementById(k)) document.getElementById(k).value = data[k];
  }
  actualizar();
}

actualizar();
</script>
</body>
</html>
"""

def main():
    os.makedirs(BASE, exist_ok=True)
    for d in DIRS:
        os.makedirs(os.path.join(BASE, d), exist_ok=True)
    for rel, content in FILES.items():
        full = os.path.join(BASE, rel)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
    win_font = r"C:\Windows\Fonts\micross.ttf"
    dst_font = os.path.join(BASE, "assets", "fuentes", "micross.ttf")
    if os.path.exists(win_font) and not os.path.exists(dst_font):
        shutil.copy2(win_font, dst_font)
    print("Instalando librerias Python...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install",
        "fastapi", "uvicorn", "pydantic", "ezdxf", "shapely",
        "fonttools", "uharfbuzz", "pyyaml", "google-genai", "python-multipart"
    ])
    print("\nLISTO! Todo armado en C:\\placas-cam.")
    print("Para iniciar abre PowerShell en C:\\placas-cam y ejecuta: uvicorn app:app --reload")

if __name__ == "__main__":
    main()