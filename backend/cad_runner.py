"""Sandboxed runner: executes an AI-generated CAD script on an STL mesh.
Usage: python cad_runner.py input.stl script.py output.stl components.json
"""
import sys
import json
import traceback
import numpy as np
import trimesh

AXES = {
    "+x": np.array([1.0, 0, 0]), "-x": np.array([-1.0, 0, 0]),
    "+y": np.array([0, 1.0, 0]), "-y": np.array([0, -1.0, 0]),
    "+z": np.array([0, 0, 1.0]), "-z": np.array([0, 0, -1.0]),
}


def _vec(v):
    if isinstance(v, str):
        return AXES[v.lower()].copy()
    a = np.asarray(v, dtype=float)
    return a / (np.linalg.norm(a) or 1.0)


def box(size, center=(0, 0, 0)):
    """Boite alignee aux axes. size=(sx,sy,sz) en mm, center=(x,y,z)."""
    m = trimesh.creation.box(extents=[float(s) for s in size])
    m.apply_translation(np.asarray(center, dtype=float))
    return m


def box_minmax(mn, mx):
    mn = np.asarray(mn, float); mx = np.asarray(mx, float)
    return box(mx - mn, (mn + mx) / 2)


def cylinder(radius, height, center=(0, 0, 0), axis="z", sections=64):
    m = trimesh.creation.cylinder(radius=float(radius), height=float(height), sections=sections)
    ax = str(axis).lower().strip("+-")
    if ax == "x":
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    elif ax == "y":
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    m.apply_translation(np.asarray(center, dtype=float))
    return m


def rounded_rect_prism(width, height, depth, radius, center=(0, 0, 0), normal="+z", width_axis=None):
    """Prisme a coins arrondis (ex: fenetre d'ecran). width x height dans le plan, depth le long de normal."""
    from shapely.geometry import box as sbox
    r = max(0.0, min(float(radius), width / 2 - 0.01, height / 2 - 0.01))
    poly = sbox(-width / 2 + r, -height / 2 + r, width / 2 - r, height / 2 - r).buffer(r, resolution=8) if r > 0 else sbox(-width / 2, -height / 2, width / 2, height / 2)
    m = trimesh.creation.extrude_polygon(poly, float(depth))
    m.apply_translation([0, 0, -depth / 2])
    return orient(m, center, normal, width_axis)


def _frame(normal, width_axis=None):
    n = _vec(normal)
    if width_axis is not None:
        u = _vec(width_axis)
    else:
        # largeur horizontale par defaut (perpendiculaire a Z), sinon X
        u = np.cross([0, 0, 1.0], n)
        if np.linalg.norm(u) < 1e-6:
            u = np.array([1.0, 0, 0])
        u = -u if u[0] < 0 or (abs(u[0]) < 1e-6 and u[1] < 0) else u
    u = u - n * np.dot(u, n)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    return u, v, n


def orient(m, center, normal="+z", width_axis=None):
    """Place un mesh construit en local (X=largeur, Y=hauteur, Z=normale) a center, oriente selon normal."""
    u, v, n = _frame(normal, width_axis)
    T = np.eye(4)
    T[:3, 0] = u; T[:3, 1] = v; T[:3, 2] = n
    T[:3, 3] = np.asarray(center, dtype=float)
    m = m.copy()
    m.apply_transform(T)
    return m


def translate(m, v):
    m = m.copy(); m.apply_translation(np.asarray(v, float)); return m


def rotate(m, angle_deg, axis="z", center=None):
    m = m.copy()
    c = m.bounds.mean(axis=0) if center is None else np.asarray(center, float)
    m.apply_transform(trimesh.transformations.rotation_matrix(np.radians(angle_deg), _vec(axis if isinstance(axis, str) and axis[0] in "+-" else "+" + axis if isinstance(axis, str) else axis), c))
    return m


def _clean(m):
    if isinstance(m, trimesh.Scene):
        m = m.dump(concatenate=True)
    return m


def union(*meshes):
    ms = [_clean(m) for m in meshes if m is not None]
    if len(ms) == 1:
        return ms[0]
    return trimesh.boolean.union(ms, engine="manifold", check_volume=False)


def difference(a, *cutters):
    cs = [_clean(c) for c in cutters if c is not None]
    if not cs:
        return a
    return trimesh.boolean.difference([_clean(a)] + cs, engine="manifold", check_volume=False)


def intersection(*meshes):
    return trimesh.boolean.intersection([_clean(m) for m in meshes], engine="manifold", check_volume=False)


def get_component(name):
    key = name.lower()
    for c in COMPONENTS:
        if c["id"].lower() == key or c["name"].lower() == key:
            return c
    for c in COMPONENTS:
        if key in c["id"].lower() or key in c["name"].lower():
            return c
    raise ValueError(f"Composant inconnu: {name}. Disponibles: {[c['id'] for c in COMPONENTS]}")


def screen_mount(component, center, outward_normal, wall_thickness, width_axis=None,
                 clearance=0.3, window_margin=0.5, recess=True, mount="posts",
                 rotate90=False, window_chamfer=True):
    """Genere (cut, add) pour monter un ecran derriere une paroi.
    center = point au centre de la zone visible, SUR LA FACE EXTERIEURE de la paroi.
    outward_normal = normale exterieure de la paroi ('+y', '-y', [x,y,z]...).
    wall_thickness = epaisseur de la paroi (mm).
    mount: 'posts' (plots de fixation interieurs), 'holes' (trous traversants), 'none'.
    Retourne (cut_mesh, add_mesh): result = difference(union(mesh, add), cut)
    """
    c = get_component(component) if isinstance(component, str) else component
    d = c["dims"]
    u, v, n = _frame(outward_normal, width_axis)
    if rotate90:
        u, v = v, -u
    width_axis_vec = u
    t = float(wall_thickness)
    center = np.asarray(center, float)
    inner = center - n * t  # point sur la face interieure
    vw, vh = d["view_w"] + 2 * window_margin, d["view_h"] + 2 * window_margin
    vox, voy = d.get("view_offset_x", 0.0), d.get("view_offset_y", 0.0)
    gw, gh, gt = d["glass_w"] + 2 * clearance, d["glass_h"] + 2 * clearance, d.get("glass_t", 1.5)
    pw, ph = d["pcb_w"], d["pcb_h"]

    def place(local_m, local_center_xy, z_from_inner):
        p = inner + u * local_center_xy[0] + v * local_center_xy[1] + n * z_from_inner
        return orient(local_m, p, n, width_axis_vec)

    cuts, adds = [], []
    # glass center relative to view center
    gx, gy = -vox, -voy
    # fenetre traversante
    win = rounded_rect_prism(vw, vh, t + 2.0, 0.6, center=(0, 0, 0), normal="+z")
    cuts.append(place(win, (0, 0), t / 2))
    if window_chamfer and t > 1.6:
        ch = min(1.0, t * 0.4)
        cham = trimesh.creation.extrude_polygon(__import__("shapely.geometry", fromlist=["box"]).box(-vw / 2 - ch, -vh / 2 - ch, vw / 2 + ch, vh / 2 + ch), ch + 0.01)
        cuts.append(place(cham, (0, 0), t - ch))
    rec = 0.0
    if recess:
        rec = max(0.0, min(gt, t - 1.0))
        if rec > 0.05:
            g = box((gw, gh, rec + 0.5), (0, 0, 0))
            cuts.append(place(g, (gx, gy), rec / 2 - 0.25))
    pcb_cx, pcb_cy = gx + d.get("glass_offset_x", 0.0), gy + d.get("glass_offset_y", 0.0)
    hx, hy, hd = d["hole_dx"] / 2, d["hole_dy"] / 2, d["hole_d"]
    holes = [(pcb_cx + sx * hx, pcb_cy + sy * hy) for sx in (-1, 1) for sy in (-1, 1)]
    if mount == "holes":
        for h in holes:
            cuts.append(place(cylinder(hd / 2 + 0.1, t + 2.0), h, t / 2))
    elif mount == "posts":
        post_h = max(0.4, gt - rec)  # le PCB repose sur le dessus des plots
        post_r = hd / 2 + 1.2
        for h in holes:
            adds.append(place(cylinder(post_r, post_h + 0.2, sections=32), h, -(post_h / 2) + 0.1))
            # avant-trou pour vis auto-taraudeuse (ne traverse pas la face avant)
            cuts.append(place(cylinder(hd / 2 * 0.85, post_h + 1.0, sections=24), h, -(post_h / 2) - 0.3))
    cut = union(*cuts) if cuts else None
    add = union(*adds) if adds else None
    return cut, add


def fill_box(mn, mx):
    """Boite de remplissage definie par coins min/max (pour reboucher une ancienne ouverture)."""
    return box_minmax(mn, mx)


def main():
    inp, script_path, out, comp_path = sys.argv[1:5]
    global COMPONENTS
    with open(comp_path) as f:
        COMPONENTS = json.load(f)
    mesh = trimesh.load(inp, force="mesh")
    with open(script_path) as f:
        code = f.read()
    env = {
        "np": np, "numpy": np, "trimesh": trimesh, "mesh": mesh, "original": mesh.copy(),
        "box": box, "box_minmax": box_minmax, "cylinder": cylinder, "rounded_rect_prism": rounded_rect_prism,
        "orient": orient, "translate": translate, "rotate": rotate, "union": union, "difference": difference,
        "intersection": intersection, "screen_mount": screen_mount, "get_component": get_component,
        "fill_box": fill_box, "COMPONENTS": COMPONENTS, "result": None,
    }
    try:
        exec(compile(code, "script_ia.py", "exec"), env)
        res = env.get("result")
        if res is None:
            raise RuntimeError("Le script n'a pas defini la variable `result`.")
        res = _clean(res)
        if not isinstance(res, trimesh.Trimesh) or len(res.faces) == 0:
            raise RuntimeError("`result` est vide ou n'est pas un mesh.")
        res.export(out)
        print(json.dumps({"ok": True, "faces": int(len(res.faces))}))
    except Exception as e:
        tb = traceback.format_exc(limit=6)
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}", "traceback": tb[-2500:]}))
        sys.exit(0)


COMPONENTS = []

if __name__ == "__main__":
    main()
