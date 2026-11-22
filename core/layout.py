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

def _ref_cap_metrics(font_path: str, cap_h: float):
    """Mide miny y maxy de 'H' (sin tilde ni descendente) para fijar altura y linea base reales."""
    g_ref = text_to_geom(font_path, "H", cap_height_mm=cap_h).buffer(0)
    if g_ref.is_empty:
        return 0.0, cap_h
    return g_ref.bounds[1], g_ref.bounds[3]

def _set_cap_height(geom, font_path: str, target_cap_h: float):
    """Escala el renglon segun la altura real de 'H' sin que la tilde achique el cuerpo de la letra."""
    if geom is None or geom.is_empty or target_cap_h <= 0:
        return geom
    r_miny, r_maxy = _ref_cap_metrics(font_path, target_cap_h)
    cur_cap = r_maxy - r_miny
    if cur_cap <= 1e-6:
        return geom
    sy = target_cap_h / cur_cap
    minx, _, maxx, _ = geom.bounds
    cx = (minx + maxx) / 2.0
    return scale(geom, xfact=1.0, yfact=sy, origin=(cx, r_miny))

def _norm_fecha(f: str) -> str:
    s = re.sub(r"[/\-\s]+", ".", (f or "").strip())
    return re.sub(r"\.+", ".", s).strip(".")

def _norm_encabezado(enc: str) -> str:
    t = (enc or "").strip().upper()
    if re.fullmatch(r"Q\.?\s*E\.?\s*P\.?\s*D\.?", t):
        return "Q.E.P.D."
    return t

def _format_ubicacion(sector: str, seccion: str, parcela: str) -> str:
    partes = []
    for raw in (sector, seccion, parcela):
        limpio = re.sub(r"\s+", "", (raw or "").strip().strip("."))
        if limpio:
            partes.append(limpio)
    return re.sub(r"\.+", ".", ".".join(partes)).strip(".")

def _cruz_diagrama_memorial(alto_mm=130.0, ancho_mm=90.0, pared_mm=3.0, ref_int=24.0):
    brazo_ext = ref_int + (2.0 * pared_mm)
    y_brazo_inf = alto_mm - 30.0 - brazo_ext
    y_brazo_sup = alto_mm - 30.0
    outer = unary_union([
        box(-brazo_ext / 2.0, 0.0, brazo_ext / 2.0, alto_mm),
        box(-ancho_mm / 2.0, y_brazo_inf, ancho_mm / 2.0, y_brazo_sup)
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

def _fit_text_line_cap(font_path: str, text: str, target_h: float, max_w: float):
    g = text_to_geom(font_path, text, cap_height_mm=target_h).buffer(0)
    if g.is_empty:
        return g
    g = _set_cap_height(g, font_path, target_h)
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
                cg = text_to_geom(font_path, ch, cap_height_mm=target_h).buffer(0)
                if cg.is_empty:
                    valid = False
                    break
                cg = _set_cap_height(cg, font_path, target_h)
                char_geoms.append(cg)
        if valid:
            min_gap = 0.45
            space_w = target_h * 0.24
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
                fx = max_w / max(1e-6, w_orig)
                return scale(g, xfact=fx, yfact=1.0, origin=(0, 0))

    fx = max_w / max(1e-6, w_orig)
    return scale(g, xfact=fx, yfact=1.0, origin=(0, 0))

def _place_line_by_baseline(font_path: str, text: str, target_h: float, max_w: float, center_x: float, top_y: float):
    g = _fit_text_line_cap(font_path, text, target_h, max_w)
    if g is None or g.is_empty:
        return None, top_y
    r_miny, r_maxy = _ref_cap_metrics(font_path, target_h)
    cur_cap = r_maxy - r_miny
    sy = (target_h / cur_cap) if cur_cap > 1e-6 else 1.0
    cap_top = r_miny + (r_maxy - r_miny) * sy
    cap_base = r_miny
    dy = top_y - cap_top
    g_placed = translate(_center_x(g, center_x), yoff=dy)
    return g_placed, (cap_base + dy)

def _render_multiline_by_baseline(font_path: str, text: str, target_h: float, max_w: float, center_x: float, top_y: float, line_gap: float):
    raw_lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    if not raw_lines:
        return None, top_y
    geoms = []
    cur_top = top_y
    last_base = top_y
    for idx, line in enumerate(raw_lines):
        g_l, base_y = _place_line_by_baseline(font_path, line, target_h, max_w, center_x, cur_top)
        if g_l is not None and not g_l.is_empty:
            geoms.append(g_l)
            last_base = base_y
            cur_top = base_y - line_gap
    return (unary_union(geoms).buffer(0) if geoms else None), last_base

def build_plate_geometries(data: dict):
    cliente = (data.get("cliente") or "memorial").lower().strip()
    es_jardin = (cliente == "jardin_paz")
    W = float(data.get("ancho_mm") or (400.0 if es_jardin else 600.0))
    H = float(data.get("alto_mm") or (600.0 if es_jardin else 400.0))
    contorno = box(0, 0, W, H)

    font_serif = _get_serif_font()
    font_sans = FONT_SANS
    font_main = font_sans if es_jardin else font_serif

    encabezado = _norm_encabezado(data.get("encabezado") or "")
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

    H_QEPD = 23.0
    GAP_QEPD_NOMBRE = 22.0 if es_diagrama_memorial else 20.0
    H_NOMBRE = 28.0 if es_diagrama_memorial else 30.0
    GAP_NOMBRE_FECHA = 10.0 if es_diagrama_memorial else 20.0
    H_FECHA = 20.0
    GAP_FECHA_FRASE = 15.0 if es_diagrama_memorial else 14.0
    H_DEDICATORIA = 20.0
    GAP_ENTRE_PERSONAS = GAP_FECHA_FRASE if es_diagrama_memorial else 22.0

    H_UBIC = 20.0 if es_diagrama_memorial else 14.0

    simbolos = []
    cur_top_y = H - MARGEN_SUP_DIAGRAMA

    if simb_sup == "cruz":
        g_cs = _cruz_latina(110.0, 80.0, 2.3, 27.4)
        g_cs = translate(g_cs, xoff=(W - 80.0) / 2.0, yoff=H - 20.0 - 110.0)
        simbolos.append(g_cs)
        cur_top_y = H - 20.0 - 110.0 - 18.0
    elif simb_sup == "david":
        g_ds = _estrella_david(DAVID_W, DAVID_H, 2.3)
        g_ds = translate(g_ds, xoff=(W - DAVID_W) / 2.0, yoff=H - 20.0 - DAVID_H)
        simbolos.append(g_ds)
        cur_top_y = H - 20.0 - DAVID_H - 18.0
    elif simb_sup == "dibujo":
        g_ms = _marcador_reserva_dibujo(30.0, 26.0)
        g_ms = translate(g_ms, xoff=(W - 30.0) / 2.0, yoff=H - 20.0 - 26.0)
        simbolos.append(g_ms)
        cur_top_y = H - 20.0 - 26.0 - 18.0

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

    # Si no lleva sigla (Q.E.P.D. vacio), conserva el hueco superior para que el nombre quede en su Y habitual alineado a la cruz
    if encabezado:
        g_enc, base_enc = _render_multiline_by_baseline(font_main, encabezado, H_QEPD, ancho_util, eje_x_texto, cur_top_y, 10.0)
        if g_enc is not None and not g_enc.is_empty:
            textos.append(g_enc)
            cur_top_y = base_enc - GAP_QEPD_NOMBRE
    else:
        cur_top_y = cur_top_y - H_QEPD - GAP_QEPD_NOMBRE

    if titulo_familia:
        g_fam, base_fam = _render_multiline_by_baseline(font_main, titulo_familia, 24.0, ancho_util, eje_x_texto, cur_top_y, 10.0)
        if g_fam is not None and not g_fam.is_empty:
            textos.append(g_fam)
            cur_top_y = base_fam - 14.0

    font_ded = font_sans if es_diagrama_memorial else font_main

    for idx, p in enumerate(personas):
        nom = (p.get("nombre") or "").strip().upper()
        fn = _norm_fecha(p.get("fecha_nac", ""))
        ff = _norm_fecha(p.get("fecha_fall", ""))
        fec_str = f"{fn}  {ff}".strip() if (fn and ff) else (fn or ff)

        if en_linea and fec_str:
            nom_flat = " ".join(nom.splitlines())
            g_l, base_l = _place_line_by_baseline(font_main, f"{nom_flat}  {fec_str}", H_NOMBRE, ancho_util, eje_x_texto, cur_top_y)
            if g_l is not None and not g_l.is_empty:
                textos.append(g_l)
                cur_top_y = base_l
        else:
            g_n, base_n = _render_multiline_by_baseline(font_main, nom, H_NOMBRE, ancho_util, eje_x_texto, cur_top_y, 10.0)
            if g_n is not None and not g_n.is_empty:
                textos.append(g_n)
                cur_top_y = base_n
            if dedicatoria and dedicatoria_antes_fecha and idx == 0:
                cur_top_y -= GAP_NOMBRE_FECHA
                g_d, base_d = _render_multiline_by_baseline(font_ded, dedicatoria, H_DEDICATORIA, ancho_util, eje_x_texto, cur_top_y, 10.0)
                if g_d is not None and not g_d.is_empty:
                    textos.append(g_d)
                    cur_top_y = base_d
            if fec_str:
                cur_top_y -= GAP_NOMBRE_FECHA
                g_f, base_f = _place_line_by_baseline(font_main, fec_str, H_FECHA, ancho_util, eje_x_texto, cur_top_y)
                if g_f is not None and not g_f.is_empty:
                    textos.append(g_f)
                    cur_top_y = base_f

        if idx < len(personas) - 1:
            cur_top_y -= GAP_ENTRE_PERSONAS

    if dedicatoria and not dedicatoria_antes_fecha:
        cur_top_y -= GAP_FECHA_FRASE
        g_d, base_d = _render_multiline_by_baseline(font_ded, dedicatoria, H_DEDICATORIA, ancho_util, eje_x_texto, cur_top_y, 10.0)
        if g_d is not None and not g_d.is_empty:
            textos.append(g_d)
            cur_top_y = base_d

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
        y_target_inf = max(MARGEN_INF_UBIC + 18.0, cur_top_y - h_inf - 12.0)
        simbolos.append(translate(g_minf, xoff=eje_x_texto - w_inf / 2.0, yoff=y_target_inf))

    # Ubicacion abajo izquierda (ej. X.10.250 o X2.10.250 en Microsoft Sans Serif)
    ubicacion_geoms = []
    ubic_str = _format_ubicacion(sector, seccion, parcela)
    if ubic_str:
        g_ub = text_to_geom(font_sans, ubic_str, cap_height_mm=H_UBIC).buffer(0)
        if not g_ub.is_empty:
            g_ub = _set_cap_height(g_ub, font_sans, H_UBIC)
            g_ub = translate(g_ub, xoff=MARGEN_LATERAL - g_ub.bounds[0], yoff=MARGEN_INF_UBIC - g_ub.bounds[1])
            ubicacion_geoms.append(g_ub)

    return {
        "01_CONTORNO_PLACA": contorno,
        "02_TEXTO_GRABADO_Z05": unary_union(textos).buffer(0) if textos else None,
        "03_SIMBOLOS_GRABADO_Z05": unary_union(simbolos).buffer(0) if simbolos else None,
        "04_UBICACION_GRABADO_Z05": unary_union(ubicacion_geoms).buffer(0) if ubicacion_geoms else None,
        "_dims": (W, H)
    }
