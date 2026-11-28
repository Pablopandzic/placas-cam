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

def _norm_fecha(f: str) -> str:
    s = re.sub(r"[/\-\s]+", ".", (f or "").strip())
    s = re.sub(r"\.+", ".", s).strip(".")
    if not s:
        return ""
    partes = s.split(".")
    limpias = []
    for idx, p in enumerate(partes):
        p_c = p.strip()
        if not p_c:
            continue
        if idx < 2 and p_c.isdigit():
            p_c = str(int(p_c))
        limpias.append(p_c)
    return ".".join(limpias)


def _norm_encabezado(enc: str) -> str:
    t = (enc or "").strip().upper()
    if re.fullmatch(r"Q\.?\s*E\.?\s*P\.?\s*D\.?", t):
        return "Q.E.P.D."
    return t

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

def _fit_line(font_path: str, text: str, cap_h: float, max_w: float):
    g = text_to_geom(font_path, text, cap_height_mm=cap_h).buffer(0)
    if g.is_empty:
        return g
    w_orig = g.bounds[2] - g.bounds[0]
    if w_orig <= max_w:
        return g
    # Si el texto contiene puntos (fechas o ubicacion), escalar como bloque continuo para conservar puntos uniformes
    if "." in text:
        factor = max_w / max(1e-6, w_orig)
        return scale(g, xfact=factor, yfact=factor, origin=(0, 0))

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
                factor = max_w / max(1e-6, w_orig)
                return scale(g, xfact=factor, yfact=factor, origin=(0, 0))

    factor = max_w / max(1e-6, w_orig)
    return scale(g, xfact=factor, yfact=factor, origin=(0, 0))

def _ref_h_no_tilde(font_path: str, cap_h: float) -> float:
    g_ref = text_to_geom(font_path, "H", cap_height_mm=cap_h).buffer(0)
    if g_ref.is_empty:
        return cap_h
    return max(1e-6, g_ref.bounds[3] - g_ref.bounds[1])


def _escala_comun_nombres(personas_list, font_path: str, cap_h: float, max_w: float, en_linea: bool):
    """Calcula un unico factor de escala horizontal comun para todos los nombres de la placa."""
    factor_comun = 1.0
    for p in personas_list:
        nom = (p.get("nombre") or "").strip().upper()
        if not nom:
            continue
        fn = _norm_fecha(p.get("fecha_nac", ""))
        ff = _norm_fecha(p.get("fecha_fall", ""))
        fec_str = f"{fn}      {ff}".strip() if (fn and ff) else (fn or ff)
        lineas = [" ".join(nom.splitlines()) + (f"  {fec_str}" if (en_linea and fec_str) else "")] if en_linea else [l.strip() for l in nom.splitlines() if l.strip()]
        for ln in lineas:
            g_tmp = text_to_geom(font_path, ln, cap_height_mm=cap_h).buffer(0)
            if not g_tmp.is_empty:
                w_tmp = g_tmp.bounds[2] - g_tmp.bounds[0]
                if w_tmp > max_w and w_tmp > 1e-6:
                    factor_comun = min(factor_comun, max_w / w_tmp)
    return factor_comun

def _place_block_top_down(font_path: str, text: str, cap_h: float, max_w: float, center_x: float, top_y: float, line_gap: float = 8.0):
    raw_lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    if not raw_lines:
        return None, top_y
    geoms = []
    cur_top = top_y
    last_bottom = top_y
    h_ref = _ref_h_no_tilde(font_path, cap_h)
    for line in raw_lines:
        g = _fit_line(font_path, line, cap_h, max_w)
        if g.is_empty:
            continue
        g = _center_x(g, center_x)
        # Usar alto de referencia sin tilde para que acentos (A, E, I, O, U) no corran el bloque hacia abajo
        con_tilde = re.search("[\u00c1\u00c9\u00cd\u00d3\u00da\u00dc\u00d1]", line) is not None
        h_l = h_ref if con_tilde else (g.bounds[3] - g.bounds[1])
        g = translate(g, yoff=(cur_top - h_l) - (0.0 if con_tilde else g.bounds[1]))
        geoms.append(g)
        last_bottom = g.bounds[1]
        cur_top = last_bottom - line_gap
    return (unary_union(geoms).buffer(0) if geoms else None), last_bottom

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
    H_FECHA = 20.0 * (20.0 / 18.67)
    GAP_FECHA_FRASE = 15.0 if es_diagrama_memorial else 14.0
    H_DEDICATORIA = 18.0
    GAP_ENTRE_PERSONAS = GAP_FECHA_FRASE if es_diagrama_memorial else 22.0

    H_UBIC_SEC = 25.0 if es_diagrama_memorial else 25.0
    H_UBIC_NUM = 20.0 if es_diagrama_memorial else 20.0

    simbolos = []
    cur_top_y = H - (22.0 if es_diagrama_memorial else 20.0)

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

    if encabezado:
        g_enc, bot_enc = _place_block_top_down(font_main, encabezado, H_QEPD, ancho_util, eje_x_texto, cur_top_y, 8.0)
        if g_enc is not None and not g_enc.is_empty:
            textos.append(g_enc)
            cur_top_y = bot_enc - GAP_QEPD_NOMBRE
    else:
        cur_top_y = cur_top_y - H_QEPD - GAP_QEPD_NOMBRE

    if titulo_familia:
        g_fam, bot_fam = _place_block_top_down(font_main, titulo_familia, 24.0, ancho_util, eje_x_texto, cur_top_y, 8.0)
        if g_fam is not None and not g_fam.is_empty:
            textos.append(g_fam)
            cur_top_y = bot_fam - 14.0

    font_ded = font_sans if es_diagrama_memorial else font_main

    font_nombres = font_sans if en_linea else font_main
    factor_nombres = _escala_comun_nombres(personas, font_nombres, H_NOMBRE, ancho_util, en_linea)
    ded_colocada = False
    for idx, p in enumerate(personas):
        nom = (p.get("nombre") or "").strip().upper()
        fn = _norm_fecha(p.get("fecha_nac", ""))
        ff = _norm_fecha(p.get("fecha_fall", ""))
        fec_str = (fn + " " * 6 + ff) if (fn and ff) else (fn or ff)
        top_bloque = cur_top_y

        if en_linea:
            # Todos los renglones "en linea" comparten fuente y factor de escala
            nom_flat = " ".join(nom.splitlines())
            linea = (nom_flat + " " * 2 + fec_str) if fec_str else nom_flat
            g_l, bot_l = _place_block_top_down(font_sans, linea, H_NOMBRE, float("inf"), eje_x_texto, top_bloque, 8.0)
            if g_l is not None and not g_l.is_empty:
                if factor_nombres < 0.999999:
                    g_l = scale(g_l, xfact=factor_nombres, yfact=factor_nombres, origin=(eje_x_texto, top_bloque))
                    g_l = _center_x(g_l, eje_x_texto)
                    bot_l = g_l.bounds[1]
                textos.append(g_l)
                cur_top_y = bot_l
        else:
            # Tamano natural (sin compresion de _fit_line) + unica escala comun anclada al tope del bloque
            g_n, bot_n = _place_block_top_down(font_main, nom, H_NOMBRE, float("inf"), eje_x_texto, top_bloque, 8.0)
            if g_n is not None and not g_n.is_empty:
                if factor_nombres < 0.999999:
                    g_n = scale(g_n, xfact=factor_nombres, yfact=factor_nombres, origin=(eje_x_texto, top_bloque))
                    g_n = _center_x(g_n, eje_x_texto)
                    bot_n = g_n.bounds[1]
                g_n = translate(g_n, yoff=3.87)
                textos.append(g_n)
                cur_top_y = bot_n + 3.87
            if dedicatoria and dedicatoria_antes_fecha and idx == 0:
                ded_colocada = True
                cur_top_y -= GAP_NOMBRE_FECHA
                g_d, bot_d = _place_block_top_down(font_ded, dedicatoria, H_DEDICATORIA, ancho_util, eje_x_texto, cur_top_y, 8.0)
                if g_d is not None and not g_d.is_empty:
                    textos.append(g_d)
                    cur_top_y = bot_d
            if fec_str:
                cur_top_y -= GAP_NOMBRE_FECHA
                g_f, bot_f = _place_block_top_down(font_sans, fec_str, H_FECHA, ancho_util, eje_x_texto, cur_top_y, 8.0)
                if g_f is not None and not g_f.is_empty:
                    g_f = _center_x(g_f, eje_x_texto)
                    textos.append(g_f)
                    cur_top_y = bot_f

        if idx < len(personas) - 1:
            cur_top_y -= GAP_ENTRE_PERSONAS

    if dedicatoria and not ded_colocada:
        cur_top_y -= GAP_FECHA_FRASE
        g_d, bot_d = _place_block_top_down(font_ded, dedicatoria, H_DEDICATORIA, ancho_util, eje_x_texto, cur_top_y, 8.0)
        if g_d is not None and not g_d.is_empty:
            textos.append(g_d)
            cur_top_y = bot_d

    if simb_izq == "cruz":
        if es_diagrama_memorial:
            g_ci = _cruz_diagrama_memorial(CRUZ_ALTO, CRUZ_ANCHO, CRUZ_ESPESOR, 24.0)
            simbolos.append(translate(g_ci, xoff=MARGEN_LATERAL, yoff=H - 40.0 - CRUZ_ALTO))
        else:
            g_ci = _cruz_latina(110.0, 80.0, 2.3, 27.4)
            simbolos.append(translate(g_ci, xoff=MARGEN_LATERAL, yoff=H - 20.0 - 110.0))
    elif simb_izq == "dibujo":
        g_mi = _marcador_reserva_dibujo(22.0, 22.0)
        simbolos.append(translate(g_mi, xoff=MARGEN_LATERAL, yoff=H - 20.0 - 22.0))

    if simb_der == "cruz":
        if es_diagrama_memorial:
            g_cd = _cruz_diagrama_memorial(CRUZ_ALTO, CRUZ_ANCHO, CRUZ_ESPESOR, 24.0)
            simbolos.append(translate(g_cd, xoff=W - MARGEN_LATERAL - CRUZ_ANCHO, yoff=H - 40.0 - CRUZ_ALTO))
        else:
            g_cd = _cruz_latina(110.0, 80.0, 2.3, 27.4)
            simbolos.append(translate(g_cd, xoff=W - MARGEN_LATERAL - 80.0, yoff=H - 20.0 - 110.0))
    elif simb_der == "dibujo":
        g_md = _marcador_reserva_dibujo(22.0, 22.0)
        simbolos.append(translate(g_md, xoff=W - MARGEN_LATERAL - 22.0, yoff=H - 20.0 - 22.0))

    if simb_inf == "dibujo":
        w_inf, h_inf = 24.0, 16.0
        g_minf = _marcador_reserva_dibujo(w_inf, h_inf)
        y_target_inf = max(MARGEN_INF_UBIC + 18.0, cur_top_y - h_inf - 12.0)
        simbolos.append(translate(g_minf, xoff=eje_x_texto - w_inf / 2.0, yoff=y_target_inf))

    ubicacion_geoms = []
    sec_limpio = re.sub(r"\s+", "", (sector or "").strip().strip("."))
    num_partes = [re.sub(r"\s+", "", (x or "").strip().strip(".")) for x in (seccion, parcela)]
    num_str = ".".join([p for p in num_partes if p])

    x_cur = MARGEN_LATERAL
    if sec_limpio:
        label_sec = f"{sec_limpio}." if num_str else sec_limpio
        g_sec = text_to_geom(font_sans, label_sec, cap_height_mm=H_UBIC_SEC).buffer(0)
        if not g_sec.is_empty:
            g_sec = translate(g_sec, xoff=x_cur - g_sec.bounds[0], yoff=MARGEN_INF_UBIC - g_sec.bounds[1])
            ubicacion_geoms.append(g_sec)
            x_cur = g_sec.bounds[2]

    if num_str:
        g_num = text_to_geom(font_sans, num_str, cap_height_mm=H_UBIC_NUM).buffer(0)
        if not g_num.is_empty:
            g_num = translate(g_num, xoff=x_cur - g_num.bounds[0], yoff=MARGEN_INF_UBIC - g_num.bounds[1])
            ubicacion_geoms.append(g_num)

    return {
        "01_CONTORNO_PLACA": contorno,
        "02_TEXTO_GRABADO_Z05": unary_union(textos).buffer(0) if textos else None,
        "03_SIMBOLOS_GRABADO_Z05": unary_union(simbolos).buffer(0) if simbolos else None,
        "04_UBICACION_GRABADO_Z05": unary_union(ubicacion_geoms).buffer(0) if ubicacion_geoms else None,
        "_dims": (W, H)
    }
