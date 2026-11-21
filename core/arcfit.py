import math

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
