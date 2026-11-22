import os
import re
import math
from shapely.geometry import box, LineString, Polygon
from shapely.affinity import translate, scale
from shapely.ops import unary_union
from core.text_geom import text_to_geom

FONT_SERIF = "assets/fuentes/SerifMemorial.otf"
FONT_SANS = "assets/fuentes/micross.ttf"

def _get_serif_font():
    return FONT_SERIF if os.path.exists(FONT_SERIF) else FONT_SANS

def _center_x(geom, target_x):
    if geom is None or geom.is_empty:
        return geom
    minx, _, maxx, _ = geom.bounds
    return translate(geom, xoff=target_x - ((minx + maxx) / 2.0))

def _align_bottom_y(geom, target_y):
    if geom is None or geom.is_empty:
        return geom
    _, miny, _, _ = geom.bounds
    return translate(geom, yoff=target_y - miny)

def _norm_fecha(f: str) -> str:
    s = re.sub(r"[/\-\s]+", ".", (f or "").strip())
    return re.sub(r"\.+", ".", s).strip(".")

def _cruz_diagrama_memorial(alto_mm=130.0, ancho_mm=90.0, pared_mm=3.0, ref_int=24.0):
    brazo_ext = ref_int + (2.0 * pared_mm)
    y_cruz = alto_mm * 0.64
    outer = unary_union([
        box(-brazo_ext / 2.0, 0.0, brazo_ext / 2.0, alto_mm),
        box(-ancho_mm / 2.0, y_cruz - brazo_ext / 2.0, ancho_mm / 2.0, y_cruz + brazo_ext / 2.0)
    ]).buffer(0)
    inner = outer.buffer(-pared_mm, join_style="mitre")
    geom = outer.difference(inner) if (inner is not None and not inner.is_empty) else outer
    minx, miny, _, _ = geom.bounds
    return translate(geom, xoff=-minx, yoff=-miny)

def _cruz_latina(alto_mm=110.0, ancho_mm=80.0, pared_mm=2.3, interior_mm=27.4):
    brazo_ext = interior_mm + (2.0 * pared_mm)
    y_cruz = alto_mm * 0.64
    outer = unary_union([
        box(-brazo_ext / 2.0, 0.0, brazo_ext / 2.0, alto_mm),
        box(-ancho_mm / 2.0, y_cruz - brazo_ext / 2.0, ancho_mm / 2.0, y_cruz + brazo_ext / 2.0)
    ]).buffer(0)
    inner = outer.buffer(-pared_mm, join_style="mitre")
    geom = outer.difference(inner) if (inner is not None and not inner.is_empty) else outer
    minx, miny, _, _ = geom.bounds
    return translate(geom, xoff=-minx, yoff=-miny)

def _estrella_david(ancho_mm=90.0, alto_mm=90.0, pared_mm=2.3):
    R = min(ancho_mm, alto_mm) / 2.0
    grosor_barra = pared_mm * 2.0 + 3.8
    tris_outer = []
    for offset_deg in (90.0, 270.0):
        pts_ext = []
        pts_int = []
        R_in = max(5.0, R - grosor_barra * 2.0)
        for k in range(3):
            ang = math.radians(offset_deg + k * 120.0)
            pts_ext.append((R * math.cos(ang), R * math.sin(ang)))
            pts_int.append((R_in * math.cos(ang), R_in * math.sin(ang)))
        t_frame = Polygon(pts_ext).difference(Polygon(pts_int))
        tris_outer.append(t_frame)
    outer = unary_union(tris_outer).buffer(0)
    inner = outer.buffer(-pared_mm, join_style="mitre")
    geom = outer.difference(inner) if (inner is not None and not inner.is_empty) else outer
    minx, miny, maxx, maxy = geom.bounds
    geom = scale(geom, xfact=ancho_mm / (maxx - minx), yfact=alto_mm / (maxy - miny), origin=(minx, miny))
    minx, miny, _, _ = geom.bounds
    return translate(geom, xoff=-minx, yoff=-miny)

def _marcador_reserva_dibujo(ancho_mm=24.0, alto_mm=18.0):
    grosor = 0.8
    marco_ext = box(0, 0, ancho_mm, alto_mm)
    marco_int = box(grosor, grosor, ancho_mm - grosor, alto_mm - grosor)
    marco = marco_ext.difference(marco_int)
    diag1 = LineString([(grosor, grosor), (ancho_mm - grosor, alto_mm - grosor)]).buffer(grosor * 0.5)
    diag2 = LineString([(grosor, alto_mm - grosor), (ancho_mm - grosor, grosor)]).buffer(grosor * 0.5)
    return unary_union([marco, diag1, diag2]).buffer(0)

def _fit_text_line(font_path: str, text: str, cap_h: float, max_w: float):
    g = text_to_geom(font_path, text, cap_height_mm=cap_h).buffer(0)
    if g.is_empty:
        return g
    w_orig = g.bounds[2] - g.bounds[0]
    if w_orig <= max_w:
        return g
    chars = list(text)
    if len(chars) > 1:
        char_geoms = []
        valid = True
        for ch in chars:
            if ch == " ":
                char_geoms.append(None)
            else:
                cg = text_to_geom(font_path, ch, cap_height_mm=cap_h).buffer(0)
                if cg.is_empty:
                    valid = False
                    break
                char_geoms.append(cg)
        if valid:
            min_gap = 0.45
            space_w = cap_h * 0.24
            sum_char_w = sum((cg.bounds[2] - cg.bounds[0]) if cg is not None else space_w for cg in char_geoms)
            n_gaps = len(chars) - 1
            min_total_w = sum_char_w + n_gaps * min_gap
            if min_total_w <= max_w:
                gap = (max_w - sum_char_w) / n_gaps
                x_cur = 0.0
                placed = []
                for cg in char_geoms:
                    if cg is None:
                        x_cur += space_w + gap
                    else:
                        w_c = cg.bounds[2] - cg.bounds[0]
                        placed.append(translate(cg, xoff=x_cur - cg.bounds[0]))
                        x_cur += w_c + gap
                return unary_union(placed).buffer(0)
            else:
                x_cur = 0.0
                placed = []
                for cg in char_geoms:
                    if cg is None:
                        x_cur += space_w + min_gap
                    else:
                        w_c = cg.bounds[2] - cg.bounds[0]
                        placed.append(translate(cg, xoff=x_cur - cg.bounds[0]))
                        x_cur += w_c + min_gap
                g = unary_union(placed).buffer(0)
                w_orig = g.bounds[2] - g.bounds[0]
                factor = max_w / w_orig
                return scale(g, xfact=factor, yfact=factor, origin=(0, 0))
    factor = max_w / max(1e-6, w_orig)
    return scale(g, xfact=factor, yfact=factor, origin=(0, 0))

def _render_multiline_centered(font_path: str, text: str, cap_h: float, max_w: float, center_x: float, line_gap: float = 10.0):
    raw_lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    if not raw_lines:
        return None
    geoms = []
    y_rel = 0.0
    for idx, line in enumerate(raw_lines):
        g = _fit_text_line(font_path, line, cap_h, max_w)
        if g.is_empty:
            continue
        h_g = g.bounds[3] - g.bounds[1]
        y_rel -= h_g
        geoms.append(_align_bottom_y(_center_x(g, center_x), y_rel))
        if idx < len(raw_lines) - 1:
            y_rel -= line_gap
    return unary_union(geoms).buffer(0) if geoms else None

def build_plate_geometries(data: dict):
    cliente = (data.get("cliente") or "memorial").lower().strip()
    es_jardin = (cliente == "jardin_paz")
    W = float(data.get("ancho_mm") or (400.0 if es_jardin else 600.0))
    H = float(data.get("alto_mm") or (600.0 if es_jardin else 400.0))
    contorno = box(0, 0, W, H)

    font_serif = _get_serif_font()
    font_sans = FONT_SANS
    font_main = font_sans if es_jardin else font_serif

    encabezado = (data.get("encabezado") or "").strip().upper()
    titulo_familia = (data.get("titulo_familia") or "").strip().upper()
    dedicatoria = (data.get("dedicatoria") or "").strip().upper()
    dedicatoria_antes_fecha = bool(data.get("dedicatoria_antes_fecha", False))
    simb_sup = (data.get("simb_sup") or "ninguno").lower()
    simb_izq = (data.get("simb_izq") or "ninguno").lower()
    simb_der = (data.get("simb_der") or "ninguno").lower()
    simb_inf = (data.get("simb_inf") or "ninguno").lower()
    sector = (data.get("sector") or "").strip().upper()
    seccion = (data.get("seccion") or "").strip()
    parcela = (data.get("parcela") or "").strip()
    personas = [p for p in (data.get("personas") or []) if (p.get("nombre") or "").strip()]
    modo_disposicion = data.get("modo_fechas") or "auto"
    en_linea = (modo_disposicion == "lado") or (modo_disposicion == "auto" and len(personas) >= 5)

    MARGEN_LATERAL = 20.0
    MARGEN_SUP_DIAGRAMA = 22.0 if not es_jardin else 20.0
    MARGEN_INF_UBIC = 20.0

    es_diagrama_memorial = (not es_jardin) and abs(W - 600.0) < 1e-3 and abs(H - 400.0) < 1e-3
    eje_x_texto = 355.0 * (W / 600.0) if not es_jardin else (W / 2.0)

    CRUZ_ALTO = 130.0 if es_diagrama_memorial else 110.0
    CRUZ_ANCHO = 90.0 if es_diagrama_memorial else 80.0
    CRUZ_ESPESOR = 3.0 if es_diagrama_memorial else 2.3
    DAVID_W = 90.0
    DAVID_H = 90.0

    # Alturas y separaciones exactas de taller (sin compresion vertical forzada)
    H_QEPD = 23.0
    GAP_QEPD_NOMBRE = 22.0 if es_diagrama_memorial else 20.0
    H_NOMBRE = 28.0 if es_diagrama_memorial else 30.0
    GAP_NOMBRE_FECHA = 10.0 if es_diagrama_memorial else 20.0
    H_FECHA = 20.0
    GAP_FECHA_FRASE = 15.0 if es_diagrama_memorial else 14.0
    H_DEDICATORIA = 20.0 if es_jardin else 18.0
    GAP_ENTRE_PERSONAS = GAP_FECHA_FRASE if es_diagrama_memorial else 22.0

    simbolos = []
    y_cursor = H - MARGEN_SUP_DIAGRAMA

    if simb_sup == "cruz":
        g_cs = _cruz_latina(110.0, 80.0, 2.3, 27.4)
        g_cs = translate(g_cs, xoff=(W - 80.0) / 2.0, yoff=H - 20.0 - 110.0)
        simbolos.append(g_cs)
        y_cursor = H - 20.0 - 110.0 - 18.0
    elif simb_sup == "david":
        g_ds = _estrella_david(DAVID_W, DAVID_H, 2.3)
        g_ds = translate(g_ds, xoff=(W - DAVID_W) / 2.0, yoff=H - 20.0 - DAVID_H)
        simbolos.append(g_ds)
        y_cursor = H - 20.0 - DAVID_H - 18.0
    elif simb_sup == "dibujo":
        g_ms = _marcador_reserva_dibujo(30.0, 26.0)
        g_ms = translate(g_ms, xoff=(W - 30.0) / 2.0, yoff=H - 20.0 - 26.0)
        simbolos.append(g_ms)
        y_cursor = H - 20.0 - 26.0 - 18.0

    x_min_sym = MARGEN_LATERAL
    x_max_sym = W - MARGEN_LATERAL
    if simb_izq == "cruz":
        x_min_sym = max(x_min_sym, MARGEN_LATERAL + CRUZ_ANCHO + 10.0)
    elif simb_izq == "dibujo":
        x_min_sym = max(x_min_sym, MARGEN_LATERAL + 24.0 + 10.0)
    if simb_der == "cruz":
        x_max_sym = min(x_max_sym, W - MARGEN_LATERAL - CRUZ_ANCHO - 10.0)
    elif simb_der == "dibujo":
        x_max_sym = min(x_max_sym, W - MARGEN_LATERAL - 24.0 - 10.0)

    semi_ancho = max(40.0, min(eje_x_texto - x_min_sym, x_max_sym - eje_x_texto))
    ancho_util = semi_ancho * 2.0

    textos = []

    if encabezado:
        g_enc = _render_multiline_centered(font_main, encabezado, H_QEPD, ancho_util, eje_x_texto, 10.0)
        if g_enc and not g_enc.is_empty:
            h_enc = g_enc.bounds[3] - g_enc.bounds[1]
            y_cursor -= h_enc
            textos.append(translate(g_enc, yoff=y_cursor - g_enc.bounds[1]))
            y_cursor -= GAP_QEPD_NOMBRE

    if titulo_familia:
        g_fam = _render_multiline_centered(font_main, titulo_familia, 24.0, ancho_util, eje_x_texto, 10.0)
        if g_fam and not g_fam.is_empty:
            h_fam = g_fam.bounds[3] - g_fam.bounds[1]
            y_cursor -= h_fam
            textos.append(translate(g_fam, yoff=y_cursor - g_fam.bounds[1]))
            y_cursor -= 14.0

    y_inicio_personas = y_cursor
    geoms_personas_temp = []
    y_rel = 0.0
    g_ded = _render_multiline_centered(font_sans if es_diagrama_memorial else font_main, dedicatoria, H_DEDICATORIA, ancho_util, eje_x_texto, 10.0)

    for idx, p in enumerate(personas):
        nom = (p.get("nombre") or "").strip().upper()
        fn = _norm_fecha(p.get("fecha_nac", ""))
        ff = _norm_fecha(p.get("fecha_fall", ""))
        fec_str = f"{fn}  {ff}".strip() if (fn and ff) else (fn or ff)

        if en_linea and fec_str:
            nom_flat = " ".join(nom.splitlines())
            g_l = _fit_text_line(font_main, f"{nom_flat}  {fec_str}", H_NOMBRE, ancho_util)
            if not g_l.is_empty:
                h_l = g_l.bounds[3] - g_l.bounds[1]
                y_rel -= h_l
                geoms_personas_temp.append(_align_bottom_y(_center_x(g_l, eje_x_texto), y_rel))
        else:
            g_n = _render_multiline_centered(font_main, nom, H_NOMBRE, ancho_util, eje_x_texto, 10.0)
            if g_n and not g_n.is_empty:
                h_n = g_n.bounds[3] - g_n.bounds[1]
                y_rel -= h_n
                geoms_personas_temp.append(translate(g_n, yoff=y_rel - g_n.bounds[1]))
            if dedicatoria_antes_fecha and idx == 0 and g_ded and not g_ded.is_empty:
                y_rel -= GAP_NOMBRE_FECHA
                h_d = g_ded.bounds[3] - g_ded.bounds[1]
                y_rel -= h_d
                geoms_personas_temp.append(translate(g_ded, yoff=y_rel - g_ded.bounds[1]))
            if fec_str:
                y_rel -= GAP_NOMBRE_FECHA
                g_f = _fit_text_line(font_main, fec_str, H_FECHA, ancho_util)
                if not g_f.is_empty:
                    h_f = g_f.bounds[3] - g_f.bounds[1]
                    y_rel -= h_f
                    geoms_personas_temp.append(_align_bottom_y(_center_x(g_f, eje_x_texto), y_rel))

        if idx < len(personas) - 1:
            y_rel -= GAP_ENTRE_PERSONAS

    grupo_personas = unary_union(geoms_personas_temp) if geoms_personas_temp else None
    if grupo_personas is not None and not grupo_personas.is_empty:
        grupo_personas = translate(grupo_personas, yoff=y_inicio_personas)
        textos.append(grupo_personas)
        y_cursor = grupo_personas.bounds[1] - GAP_FECHA_FRASE

    if g_ded and not g_ded.is_empty and not dedicatoria_antes_fecha:
        h_d = g_ded.bounds[3] - g_ded.bounds[1]
        y_cursor -= h_d
        textos.append(translate(g_ded, yoff=y_cursor - g_ded.bounds[1]))
        y_cursor -= 10.0

    if simb_izq == "cruz":
        if es_diagrama_memorial:
            g_ci = _cruz_diagrama_memorial(CRUZ_ALTO, CRUZ_ANCHO, CRUZ_ESPESOR, 24.0)
            simbolos.append(translate(g_ci, xoff=MARGEN_LATERAL, yoff=H - 40.0 - CRUZ_ALTO))
        else:
            g_ci = _cruz_latina(110.0, 80.0, 2.3, 27.4)
            simbolos.append(translate(g_ci, xoff=MARGEN_LATERAL, yoff=H - MARGEN_SUP_DIAGRAMA - 110.0))
    elif simb_izq == "dibujo":
        g_mi = _marcador_reserva_dibujo(22.0, 22.0)
        simbolos.append(translate(g_mi, xoff=MARGEN_LATERAL, yoff=H - MARGEN_SUP_DIAGRAMA - 22.0))

    if simb_der == "cruz":
        if es_diagrama_memorial:
            g_cd = _cruz_diagrama_memorial(CRUZ_ALTO, CRUZ_ANCHO, CRUZ_ESPESOR, 24.0)
            simbolos.append(translate(g_cd, xoff=W - MARGEN_LATERAL - CRUZ_ANCHO, yoff=H - 40.0 - CRUZ_ALTO))
        else:
            g_cd = _cruz_latina(110.0, 80.0, 2.3, 27.4)
            simbolos.append(translate(g_cd, xoff=W - MARGEN_LATERAL - 80.0, yoff=H - MARGEN_SUP_DIAGRAMA - 110.0))
    elif simb_der == "dibujo":
        g_md = _marcador_reserva_dibujo(22.0, 22.0)
        simbolos.append(translate(g_md, xoff=W - MARGEN_LATERAL - 22.0, yoff=H - MARGEN_SUP_DIAGRAMA - 22.0))

    if simb_inf == "dibujo":
        w_inf, h_inf = 24.0, 16.0
        g_minf = _marcador_reserva_dibujo(w_inf, h_inf)
        y_target_inf = max(MARGEN_INF_UBIC + 18.0, y_cursor - h_inf - 2.0)
        simbolos.append(translate(g_minf, xoff=eje_x_texto - w_inf / 2.0, yoff=y_target_inf))

    ubicacion_geoms = []
    x_cur = MARGEN_LATERAL
    y_ub = MARGEN_INF_UBIC
    if sector:
        g_sec = text_to_geom(font_sans, sector, cap_height_mm=14.0).buffer(0)
        if not g_sec.is_empty:
            g_sec = translate(g_sec, xoff=x_cur - g_sec.bounds[0], yoff=y_ub - g_sec.bounds[1])
            ubicacion_geoms.append(g_sec)
            x_cur = g_sec.bounds[2] + 6.0
    num_str = f"{seccion}.{parcela}".strip(".")
    if num_str:
        g_num = text_to_geom(font_sans, num_str, cap_height_mm=11.0).buffer(0)
        if not g_num.is_empty:
            g_num = translate(g_num, xoff=x_cur - g_num.bounds[0], yoff=y_ub - g_num.bounds[1])
            ubicacion_geoms.append(g_num)

    return {
        "01_CONTORNO_PLACA": contorno,
        "02_TEXTO_GRABADO_Z05": unary_union(textos).buffer(0) if textos else None,
        "03_SIMBOLOS_GRABADO_Z05": unary_union(simbolos).buffer(0) if simbolos else None,
        "04_UBICACION_GRABADO_Z05": unary_union(ubicacion_geoms).buffer(0) if ubicacion_geoms else None,
        "_dims": (W, H)
    }
