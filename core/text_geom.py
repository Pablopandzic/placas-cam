import math
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
