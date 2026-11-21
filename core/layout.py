import os
import re
from shapely.geometry import box, LineString
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
    s = re.sub(r"[/\-]", ".", (f or "").strip())
    return re.sub(r"\.+", ".", s).strip(".")

def _cruz_latina(alto_mm=110.0, ancho_mm=80.0, pared_mm=2.3, interior_mm=27.4):
    brazo_ext = interior_mm + (2.0 * pared_mm)  # 32.0 mm exterior -> 27.4 mm luz interior
    y_cruz = alto_mm * 0.64
    outer = unary_union([
        box(-brazo_ext / 2.0, 0.0, brazo_ext / 2.0, alto_mm),
        box(-ancho_mm / 2.0, y_cruz - brazo_ext / 2.0, ancho_mm / 2.0, y_cruz + brazo_ext / 2.0)
    ]).buffer(0)
    inner = outer.buffer(-pared_mm, join_style="mitre")
    geom = outer.difference(inner) if (inner is not None and not inner.is_empty) else outer
    minx, miny, _, _ = geom.bounds
    return translate(geom, xoff=-minx, yoff=-miny)

def _marcador_reserva_dibujo(ancho_mm=24.0, alto_mm=18.0):
    grosor = 0.8
    marco_ext = box(0, 0, ancho_mm, alto_mm)
    marco_int = box(grosor, grosor, ancho_mm - grosor, alto_mm - grosor)
    marco = marco_ext.difference(marco_int)
    diag1 = LineString([(grosor, grosor), (ancho_mm - grosor, alto_mm - grosor)]).buffer(grosor * 0.45)
    diag2 = LineString([(grosor, alto_mm - grosor), (ancho_mm - grosor, grosor)]).buffer(grosor * 0.45)
    return unary_union([marco, diag1, diag2]).buffer(0)

def _fit_text_line(font_path: str, text: str, cap_h: float, max_w: float):
    """
    1) Genera el texto a cap_h exacto (ej. 30mm).
    2) Si excede max_w, primero comprime el tracking (espacio entre letras) sin que se toquen (min 0.4mm).
    3) Si aun asi excede max_w, recien ahi escala altura y ancho proporcionalmente al maximo posible.
    """
    g = text_to_geom(font_path, text, cap_height_mm=cap_h).buffer(0)
    if g.is_empty:
        return g
    w_orig = g.bounds[2] - g.bounds[0]
    if w_orig <= max_w:
        return g

    # Paso 1: comprimir tracking entre caracteres manteniendo cap_h intacto
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
            # Ancho con espacio minimo de seguridad (0.45 mm entre letras para que no se toquen)
            min_gap = 0.45
            space_w = cap_h * 0.24
            sum_char_w = sum((cg.bounds[2] - cg.bounds[0]) if cg is not None else space_w for cg in char_geoms)
            n_gaps = len(chars) - 1
            min_total_w = sum_char_w + n_gaps * min_gap

            if min_total_w <= max_w:
                # Cabe manteniendo los 30mm de alto con tracking comprimido exacto a max_w
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
                # Comprimir al maximo posible sin tocarse y luego escalar proporcionalmente
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

    # Paso 2: escalar proporcionalmente al ancho maximo disponible
    factor = max_w / w_orig
    return scale(g, xfact=factor, yfact=factor, origin=(0, 0))

def _render_multiline_centered(font_path: str, text: str, cap_h: float, max_w: float, line_gap: float, center_x: float):
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
    W = float(data.get("ancho_mm") or 600.0)
    H = float(data.get("alto_mm") or 400.0)
    contorno = box(0, 0, W, H)
    font_main = _get_serif_font()

    encabezado = (data.get("encabezado") or "").strip().upper()
    titulo_familia = (data.get("titulo_familia") or "").strip().upper()
    dedicatoria = (data.get("dedicatoria") or "").strip().upper()

    simb_izq = (data.get("simb_izq") or "ninguno").lower()
    simb_der = (data.get("simb_der") or "ninguno").lower()
    simb_inf = (data.get("simb_inf") or "ninguno").lower()

    sector = (data.get("sector") or "").strip().upper()
    seccion = (data.get("seccion") or "").strip()
    parcela = (data.get("parcela") or "").strip()

    personas = [p for p in (data.get("personas") or []) if (p.get("nombre") or "").strip()]
    modo_disposicion = data.get("modo_fechas") or "auto"
    en_linea = (modo_disposicion == "lado") or (modo_disposicion == "auto" and len(personas) >= 5)

    # Cotas fijas de taller
    MARGEN_LATERAL = 20.0
    MARGEN_SUP = 20.0
    MARGEN_INF_UBIC = 20.0
    RESGUARDO_CRUZ_NOMBRE = 10.0

    CRUZ_ALTO = 110.0
    CRUZ_ANCHO = 80.0
    CRUZ_ESPESOR = 2.3

    H_QEPD = 23.0
    GAP_QEPD_NOMBRE = 20.0
    H_NOMBRE = 30.0
    GAP_NOMBRE_FECHA = 20.0
    H_FECHA = 20.0
    GAP_ENTRE_PERSONAS = 22.0

    # Ancho disponible descontando margenes de 20mm + simbolos + 10mm de resguardo minimo
    x_min_texto = MARGEN_LATERAL
    x_max_texto = W - MARGEN_LATERAL

    if simb_izq == "cruz":
        x_min_texto = max(x_min_texto, MARGEN_LATERAL + CRUZ_ANCHO + RESGUARDO_CRUZ_NOMBRE)
    elif simb_izq == "dibujo":
        x_min_texto = max(x_min_texto, MARGEN_LATERAL + 22.0 + RESGUARDO_CRUZ_NOMBRE)

    if simb_der == "cruz":
        x_max_texto = min(x_max_texto, W - MARGEN_LATERAL - CRUZ_ANCHO - RESGUARDO_CRUZ_NOMBRE)
    elif simb_der == "dibujo":
        x_max_texto = min(x_max_texto, W - MARGEN_LATERAL - 22.0 - RESGUARDO_CRUZ_NOMBRE)

    # Mantener centrado simetrico respecto a W/2
    semi_ancho = min((W / 2.0) - x_min_texto, x_max_texto - (W / 2.0))
    ancho_util = max(80.0, semi_ancho * 2.0)

    y_cursor = H - MARGEN_SUP
    textos = []

    # 1. Q.E.P.D. -> 23mm de alto, a 20mm del borde superior, y 20mm hasta el primer nombre
    if encabezado:
        g_enc = _render_multiline_centered(font_main, encabezado, H_QEPD, ancho_util, 6.0, W / 2.0)
        if g_enc and not g_enc.is_empty:
            h_enc = g_enc.bounds[3] - g_enc.bounds[1]
            y_cursor -= h_enc
            textos.append(translate(g_enc, yoff=y_cursor - g_enc.bounds[1]))
            y_cursor -= GAP_QEPD_NOMBRE

    # 2. Titulo familia opcional
    if titulo_familia:
        g_fam = _render_multiline_centered(font_main, titulo_familia, 24.0, ancho_util, 8.0, W / 2.0)
        if g_fam and not g_fam.is_empty:
            h_fam = g_fam.bounds[3] - g_fam.bounds[1]
            y_cursor -= h_fam
            textos.append(translate(g_fam, yoff=y_cursor - g_fam.bounds[1]))
            y_cursor -= 16.0

    # 3. Personas y Fechas (Nombre 30mm, separacion 20mm, Numeros 20mm)
    y_inicio_personas = y_cursor
    geoms_personas_temp = []
    y_rel = 0.0

    for idx, p in enumerate(personas):
        nom = (p.get("nombre") or "").strip().upper()
        fn = _norm_fecha(p.get("fecha_nac", ""))
        ff = _norm_fecha(p.get("fecha_fall", ""))
        fec_str = f"{fn}    {ff}".strip() if (fn and ff) else (fn or ff)

        if en_linea and fec_str:
            nom_flat = " ".join(nom.splitlines())
            g_l = _fit_text_line(font_main, f"{nom_flat}   {fec_str}", H_NOMBRE, ancho_util)
            if not g_l.is_empty:
                h_l = g_l.bounds[3] - g_l.bounds[1]
                y_rel -= h_l
                geoms_personas_temp.append(_align_bottom_y(_center_x(g_l, W / 2.0), y_rel))
        else:
            g_n = _render_multiline_centered(font_main, nom, H_NOMBRE, ancho_util, 8.0, W / 2.0)
            if g_n and not g_n.is_empty:
                h_n = g_n.bounds[3] - g_n.bounds[1]
                y_rel -= h_n
                geoms_personas_temp.append(translate(g_n, yoff=y_rel - g_n.bounds[1]))

            if fec_str:
                y_rel -= GAP_NOMBRE_FECHA
                g_f = _fit_text_line(font_main, fec_str, H_FECHA, ancho_util)
                if not g_f.is_empty:
                    h_f = g_f.bounds[3] - g_f.bounds[1]
                    y_rel -= h_f
                    geoms_personas_temp.append(_align_bottom_y(_center_x(g_f, W / 2.0), y_rel))

        if idx < len(personas) - 1:
            y_rel -= GAP_ENTRE_PERSONAS

    g_ded = _render_multiline_centered(font_main, dedicatoria, 14.0, W - 2 * MARGEN_LATERAL, 6.0, W / 2.0) if dedicatoria else None
    alto_ded = (g_ded.bounds[3] - g_ded.bounds[1] + 14.0) if (g_ded and not g_ded.is_empty) else 0.0
    alto_dib_inf = 24.0 if simb_inf == "dibujo" else 0.0
    y_limite_inf = MARGEN_INF_UBIC + 20.0 + alto_ded + alto_dib_inf

    alto_bloque_personas = abs(y_rel)
    espacio_disponible = max(35.0, y_inicio_personas - y_limite_inf)
    factor_v = min(1.0, espacio_disponible / alto_bloque_personas) if alto_bloque_personas > 0 else 1.0

    grupo_personas = unary_union(geoms_personas_temp) if geoms_personas_temp else None
    if grupo_personas is not None and not grupo_personas.is_empty:
        if factor_v < 1.0:
            grupo_personas = scale(grupo_personas, xfact=factor_v, yfact=factor_v, origin=(W / 2.0, 0.0))
        grupo_personas = translate(grupo_personas, yoff=y_inicio_personas)
        textos.append(grupo_personas)
        y_cursor = grupo_personas.bounds[1] - 14.0

    if g_ded and not g_ded.is_empty:
        h_d = g_ded.bounds[3] - g_ded.bounds[1]
        y_cursor -= h_d
        textos.append(translate(g_ded, yoff=y_cursor - g_ded.bounds[1]))
        y_cursor -= 8.0

    # 4. Cruz (11mm alto x 8mm ancho x 2.3mm espesor, a 20mm de arriba y 20mm del costado)
    simbolos = []
    if simb_izq == "cruz":
        g_ci = _cruz_latina(CRUZ_ALTO, CRUZ_ANCHO, CRUZ_ESPESOR)
        g_ci = translate(g_ci, xoff=MARGEN_LATERAL, yoff=H - MARGEN_SUP - CRUZ_ALTO)
        simbolos.append(g_ci)
    elif simb_izq == "dibujo":
        g_mi = _marcador_reserva_dibujo(22.0, 22.0)
        g_mi = translate(g_mi, xoff=MARGEN_LATERAL, yoff=H - MARGEN_SUP - 22.0)
        simbolos.append(g_mi)

    if simb_der == "cruz":
        g_cd = _cruz_latina(CRUZ_ALTO, CRUZ_ANCHO, CRUZ_ESPESOR)
        g_cd = translate(g_cd, xoff=W - MARGEN_LATERAL - CRUZ_ANCHO, yoff=H - MARGEN_SUP - CRUZ_ALTO)
        simbolos.append(g_cd)
    elif simb_der == "dibujo":
        g_md = _marcador_reserva_dibujo(22.0, 22.0)
        g_md = translate(g_md, xoff=W - MARGEN_LATERAL - 22.0, yoff=H - MARGEN_SUP - 22.0)
        simbolos.append(g_md)

    if simb_inf == "dibujo":
        w_inf, h_inf = 24.0, 16.0
        g_minf = _marcador_reserva_dibujo(w_inf, h_inf)
        y_target_inf = max(MARGEN_INF_UBIC + 18.0, y_cursor - h_inf - 2.0)
        g_minf = translate(g_minf, xoff=(W / 2.0) - w_inf / 2.0, yoff=y_target_inf)
        simbolos.append(g_minf)

    # 5. Ubicacion abajo izquierda a 20mm del borde izquierdo y 20mm del borde inferior
    ubicacion_geoms = []
    x_cur = MARGEN_LATERAL
    y_ub = MARGEN_INF_UBIC
    if sector:
        g_sec = text_to_geom(FONT_SANS, sector, cap_height_mm=14.0).buffer(0)
        g_sec = translate(g_sec, xoff=x_cur - g_sec.bounds[0], yoff=y_ub - g_sec.bounds[1])
        ubicacion_geoms.append(g_sec)
        x_cur = g_sec.bounds[2] + 6.0

    num_str = f"{seccion}.{parcela}".strip(".")
    if num_str:
        g_num = text_to_geom(FONT_SANS, num_str, cap_height_mm=11.0).buffer(0)
        g_num = translate(g_num, xoff=x_cur - g_num.bounds[0], yoff=y_ub - g_num.bounds[1])
        ubicacion_geoms.append(g_num)

    return {
        "01_CONTORNO_PLACA": contorno,
        "02_TEXTO_GRABADO_Z05": unary_union(textos).buffer(0) if textos else None,
        "03_SIMBOLOS_GRABADO_Z05": unary_union(simbolos).buffer(0) if simbolos else None,
        "04_UBICACION_GRABADO_Z05": unary_union(ubicacion_geoms).buffer(0) if ubicacion_geoms else None,
        "_dims": (W, H)
    }

