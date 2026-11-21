import os
import re
import json
import secrets
from typing import List
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from core.layout import build_plate_geometries
from core.dxf_writer import write_dxf

app = FastAPI(title="Placas CAM - Memorial")
security = HTTPBasic(auto_error=False)

def verificar_acceso(credentials: HTTPBasicCredentials = Depends(security)):
    pwd = os.environ.get("APP_PASSWORD", "").strip()
    if not pwd:
        return True  # En local sin APP_PASSWORD entra directo
    if credentials is None or not secrets.compare_digest(credentials.password, pwd):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acceso restringido al taller",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True

class PersonaItem(BaseModel):
    nombre: str = ""
    fecha_nac: str = ""
    fecha_fall: str = ""

class OrdenPlaca(BaseModel):
    orden_id: str = "00001"
    ancho_mm: float = 600.0
    alto_mm: float = 400.0
    encabezado: str = "Q.E.P.D."
    titulo_familia: str = ""
    personas: List[PersonaItem] = []
    modo_fechas: str = "auto"
    dedicatoria: str = ""
    simb_izq: str = "ninguno"
    simb_der: str = "ninguno"
    simb_inf: str = "ninguno"
    detalle_dibujo: str = ""
    sector: str = ""
    seccion: str = ""
    parcela: str = ""
    nota_taller: str = ""

def _geom_to_svg_paths(geom, H: float, color="#111111"):
    if geom is None or geom.is_empty:
        return ""
    polys = geom.geoms if hasattr(geom, "geoms") else [geom]
    paths = []
    for p in polys:
        if p.is_empty:
            continue
        d = []
        ext = list(p.exterior.coords)
        d.append("M " + " L ".join(f"{x:.2f},{H - y:.2f}" for x, y in ext) + " Z")
        for interior in p.interiors:
            pts = list(interior.coords)
            d.append("M " + " L ".join(f"{x:.2f},{H - y:.2f}" for x, y in pts) + " Z")
        paths.append(f'<path d="{" ".join(d)}" fill="{color}" fill-rule="evenodd"/>')
    return "\n".join(paths)

@app.get("/", response_class=HTMLResponse, dependencies=[Depends(verificar_acceso)])
def index():
    with open("web/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/preview", dependencies=[Depends(verificar_acceso)])
def preview_svg(orden: OrdenPlaca):
    try:
        geoms = build_plate_geometries(orden.model_dump())
        W, H = geoms["_dims"]
        svg_texto = _geom_to_svg_paths(geoms["02_TEXTO_GRABADO_Z05"], H, "#111111")
        has_manual_dib = "dibujo" in (orden.simb_izq, orden.simb_der, orden.simb_inf)
        svg_simb = _geom_to_svg_paths(geoms["03_SIMBOLOS_GRABADO_Z05"], H, "#dc2626" if has_manual_dib else "#1d4ed8")
        svg_ubic = _geom_to_svg_paths(geoms["04_UBICACION_GRABADO_Z05"], H, "#111111")
        m = 18
        svg = f'''<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-height:540px;height:auto;background:#f8fafc;border:2px solid #94a3b8;box-shadow:0 4px 12px rgba(0,0,0,0.08)">
            <rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff" stroke="#334155" stroke-width="1.5"/>
            <rect x="{m}" y="{m}" width="{W-2*m}" height="{H-2*m}" fill="none" stroke="#e2e8f0" stroke-dasharray="4 4" stroke-width="0.8"/>
            {svg_texto}
            {svg_simb}
            {svg_ubic}
        </svg>'''
        return {"svg": svg, "serif_activa": os.path.exists("assets/fuentes/SerifMemorial.otf")}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/generar-dxf", dependencies=[Depends(verificar_acceso)])
def generar_dxf(orden: OrdenPlaca):
    try:
        os.makedirs("salida", exist_ok=True)
        geoms = build_plate_geometries(orden.model_dump())
        geoms_dxf = {k: v for k, v in geoms.items() if not k.startswith("_")}
        primer_nom = (orden.personas[0].nombre.splitlines()[0] if (orden.personas and orden.personas[0].nombre) else "PLACA")
        safe_name = re.sub(r"[^A-Z0-9_]", "", primer_nom.upper().replace(" ", "_")) or "PLACA"
        safe_id = re.sub(r"[^A-Z0-9_-]", "", orden.orden_id.upper()) or "ORD"
        dim_tag = f"{int(orden.ancho_mm)}x{int(orden.alto_mm)}"
        dib_tag = "_CON_DIBUJO" if ("dibujo" in (orden.simb_izq, orden.simb_der, orden.simb_inf)) else ""
        filename = f"{safe_id}_{safe_name}_{dim_tag}{dib_tag}.dxf"
        out_path = os.path.join("salida", filename)
        write_dxf(out_path, geoms_dxf)
        return FileResponse(out_path, media_type="application/dxf", filename=filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/ocr-orden", dependencies=[Depends(verificar_acceso)])
async def ocr_orden(file: UploadFile = File(...)):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="Falta configurar GEMINI_API_KEY en el servidor.")
    from google import genai
    from google.genai import types
    img_bytes = await file.read()
    mime = file.content_type or "image/jpeg"
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=45000))
    prompt = '''Analiza esta orden de placa funeraria (si esta rotada 90 grados leela bien).
REGLA CRÍTICA DE RENGLONES: Respeta EXACTAMENTE los saltos de línea (\\n) tal como están escritos en el papel. Por ejemplo, si dice FAMILIA en un renglón y CORVALAN abajo, pon "FAMILIA\\nCORVALAN". Si un nombre largo está dividido en 2 renglones, respeta el salto de línea con \\n.
REGLA DE UBICACIÓN: Busca el Sector, Sección y Parcela tanto en casilleros como escritos abajo a la izquierda o arriba (ej: "J1. 19. 253" -> sector="J1", seccion="19", parcela="253"; "G.6.9" -> sector="G", seccion="6", parcela="9").
REGLA DE SÍMBOLOS: Si hay una cruz latina, pon "cruz". Si hay otro dibujo (rosa, infinito, paloma, estrella), pon "dibujo".

Devuelve un único JSON plano:
{
  "orden_id": "numero de partida u orden si figura",
  "encabezado": "Q.E.P.D. si figura",
  "titulo_familia": "titulo familiar respetando \\n si son 2 renglones, sino vacio",
  "personas": [{"nombre": "NOMBRE RESPETANDO \\n SI ESTA EN 2 RENGLONES", "fecha_nac": "DD.MM.AAAA", "fecha_fall": "DD.MM.AAAA"}],
  "dedicatoria": "epitafio al pie respetando \\n si son 2 renglones",
  "simb_izq": "cruz o dibujo o ninguno",
  "simb_der": "cruz o dibujo o ninguno",
  "simb_inf": "dibujo o ninguno",
  "detalle_dibujo": "solo si hay dibujo distinto de cruz (ej Rosa abajo, Infinito centro), sino vacio",
  "sector": "ej J1, G, A, S",
  "seccion": "ej 19, 6, 41",
  "parcela": "ej 253, 9, 13",
  "nota_taller": "PLACA ROTA / URGENTE / AGREGADO si figura"
}'''
    modelos = ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash-lite"]
    ultimo_error = ""
    for m in modelos:
        try:
            res = client.models.generate_content(
                model=m,
                contents=[types.Part.from_bytes(data=img_bytes, mime_type=mime), prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            data = json.loads(res.text)
            if isinstance(data, list):
                data = data[0] if data else {}
            personas = data.get("personas") or []
            norm_personas = []
            for p in personas:
                norm_personas.append({
                    "nombre": str(p.get("nombre") or "").upper().strip(),
                    "fecha_nac": re.sub(r"[/\-]", ".", str(p.get("fecha_nac") or "")).strip("."),
                    "fecha_fall": re.sub(r"[/\-]", ".", str(p.get("fecha_fall") or "")).strip(".")
                })
            return {
                "orden_id": str(data.get("orden_id") or "").strip(),
                "encabezado": str(data.get("encabezado") or "").upper().strip(),
                "titulo_familia": str(data.get("titulo_familia") or "").upper().strip(),
                "personas": norm_personas or [{"nombre": "", "fecha_nac": "", "fecha_fall": ""}],
                "dedicatoria": str(data.get("dedicatoria") or "").upper().strip(),
                "simb_izq": str(data.get("simb_izq") or "ninguno").lower(),
                "simb_der": str(data.get("simb_der") or "ninguno").lower(),
                "simb_inf": str(data.get("simb_inf") or "ninguno").lower(),
                "detalle_dibujo": str(data.get("detalle_dibujo") or "").strip(),
                "sector": str(data.get("sector") or "").upper().strip(),
                "seccion": str(data.get("seccion") or "").strip(),
                "parcela": str(data.get("parcela") or "").strip(),
                "nota_taller": str(data.get("nota_taller") or "").strip()
            }
        except Exception as e:
            ultimo_error = str(e)
            continue
    raise HTTPException(status_code=503, detail=f"Modelos ocupados: {ultimo_error}")
