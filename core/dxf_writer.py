import os
import ezdxf
from ezdxf import units
from shapely.geometry.polygon import orient

LAYER_COLORS = {
    "01_CONTORNO_PLACA": 7,
    "02_TEXTO_GRABADO_Z05": 1,
    "03_SIMBOLOS_GRABADO_Z05": 5,
    "04_UBICACION_GRABADO_Z05": 3,
}

def write_dxf(path: str, layer_geoms: dict, tol: float = 0.005, version: str = "R2000"):
    doc = ezdxf.new(version, setup=False)
    doc.units = units.MM
    doc.header["$MEASUREMENT"] = 1
    for name, color in LAYER_COLORS.items():
        doc.layers.add(name, color=color)

    msp = doc.modelspace()
    for layer, geom in layer_geoms.items():
        if geom is None or geom.is_empty:
            continue
        geom_clean = geom.buffer(0)
        polys = geom_clean.geoms if hasattr(geom_clean, "geoms") else [geom_clean]
        for poly in polys:
            if poly.is_empty or poly.area < 1e-5:
                continue
            poly = orient(poly, 1.0)
            for ring in (poly.exterior, *poly.interiors):
                ring_simp = ring.simplify(tol, preserve_topology=True)
                pts = [(float(x), float(y)) for x, y in list(ring_simp.coords)[:-1]]
                if len(pts) >= 3:
                    msp.add_lwpolyline(pts, format="xy", close=True, dxfattribs={"layer": layer})

    doc.audit()
    tmp = path + ".tmp"
    doc.saveas(tmp)
    os.replace(tmp, path)
