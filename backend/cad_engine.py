"""CAD helpers: mesh loading, stats, multi-view rendering, point analysis, script execution."""
import io
import os
import sys
import json
import asyncio
import tempfile
import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cad_runner.py")


def load_mesh(data: bytes) -> trimesh.Trimesh:
    m = trimesh.load(io.BytesIO(data), file_type="stl", force="mesh")
    if isinstance(m, trimesh.Scene):
        m = m.dump(concatenate=True)
    if len(m.faces) == 0:
        raise ValueError("Fichier STL vide ou invalide")
    return m


def repair(m: trimesh.Trimesh) -> trimesh.Trimesh:
    m = m.copy()
    m.merge_vertices()
    m.update_faces(m.nondegenerate_faces())
    m.update_faces(m.unique_faces())
    m.remove_unreferenced_vertices()
    if not m.is_watertight:
        trimesh.repair.fill_holes(m)
    trimesh.repair.fix_normals(m)
    return m


def to_stl_bytes(m: trimesh.Trimesh) -> bytes:
    return m.export(file_type="stl")


def mesh_stats(m: trimesh.Trimesh) -> dict:
    b = m.bounds
    ext = b[1] - b[0]
    st = {
        "faces": int(len(m.faces)),
        "vertices": int(len(m.vertices)),
        "bounds_min": [round(float(x), 3) for x in b[0]],
        "bounds_max": [round(float(x), 3) for x in b[1]],
        "size": [round(float(x), 3) for x in ext],
        "watertight": bool(m.is_watertight),
    }
    try:
        st["volume_cm3"] = round(float(abs(m.volume)) / 1000.0, 3) if m.is_watertight else None
    except Exception:
        st["volume_cm3"] = None
    return st


def _shade(mesh, light):
    nrm = mesh.face_normals
    inten = np.clip(np.abs(nrm @ light), 0, 1)
    base = np.array([0.55, 0.70, 0.95])
    cols = np.outer(0.30 + 0.70 * inten, base)
    return np.clip(cols, 0, 1)


def render_views(m: trimesh.Trimesh, points=None) -> bytes:
    """Rend 4 vues orthographiques (face, droite, dessus, iso) avec reperes en mm."""
    mesh = m
    if len(m.faces) > 14000:
        try:
            mesh = m.simplify_quadric_decimation(face_count=14000)
        except Exception:
            idx = np.random.default_rng(0).choice(len(m.faces), 14000, replace=False)
            mesh = trimesh.Trimesh(m.vertices, m.faces[idx], process=False)
    tris = mesh.vertices[mesh.faces]
    b = m.bounds
    c = b.mean(axis=0)
    r = float((b[1] - b[0]).max()) / 2 * 1.08 + 1e-6
    views = [
        ("FACE (vue depuis -Y, X vers la droite, Z en haut)", 0, -90),
        ("DROITE (vue depuis +X, Y vers la droite, Z en haut)", 0, 0),
        ("DESSUS (vue depuis +Z, X droite, Y haut)", 90, -90),
        ("ISO (depuis -X -Y +Z)", 28, -125),
    ]
    fig = plt.figure(figsize=(12, 10), dpi=85)
    for i, (title, elev, azim) in enumerate(views):
        ax = fig.add_subplot(2, 2, i + 1, projection="3d")
        ax.set_proj_type("ortho")
        ev, az = np.radians(elev), np.radians(azim)
        view_dir = np.array([np.cos(ev) * np.cos(az), np.cos(ev) * np.sin(az), np.sin(ev)])
        light = view_dir * 0.8 + np.array([0.3, -0.2, 0.5])
        light /= np.linalg.norm(light)
        pc = Poly3DCollection(tris, facecolors=_shade(mesh, light), edgecolors="none", linewidths=0)
        ax.add_collection3d(pc)
        ax.set_xlim(c[0] - r, c[0] + r); ax.set_ylim(c[1] - r, c[1] + r); ax.set_zlim(c[2] - r, c[2] + r)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev=elev, azim=azim)
        ax.set_xlabel("X (mm)", fontsize=8); ax.set_ylabel("Y (mm)", fontsize=8); ax.set_zlabel("Z (mm)", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.set_title(title, fontsize=9)
        if points:
            for j, p in enumerate(points):
                pt = p.get("point") or p
                ax.scatter([pt[0]], [pt[1]], [pt[2]], color="red", s=40, depthshade=False)
                ax.text(pt[0], pt[1], pt[2], f" P{j + 1}", color="red", fontsize=10, weight="bold")
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def point_info(m: trimesh.Trimesh, point) -> dict:
    p = np.asarray(point, float).reshape(1, 3)
    closest, dist, tri = trimesh.proximity.closest_point(m, p)
    fid = int(tri[0])
    n = m.face_normals[fid]
    q = closest[0]
    thickness = None
    try:
        origin = (q - n * 0.02).reshape(1, 3)
        locs, _, _ = m.ray.intersects_location(origin, (-n).reshape(1, 3))
        if len(locs):
            d = np.linalg.norm(locs - q, axis=1)
            d = d[d > 0.05]
            if len(d):
                thickness = round(float(d.min()), 3)
    except Exception:
        pass
    return {
        "point": [round(float(x), 3) for x in q],
        "normal": [round(float(x), 4) for x in n],
        "thickness": thickness,
    }


async def run_script(stl_bytes: bytes, code: str, components: list, timeout: int = 90) -> dict:
    with tempfile.TemporaryDirectory() as td:
        inp, sp, out, cp = (os.path.join(td, n) for n in ("in.stl", "script.py", "out.stl", "comp.json"))
        with open(inp, "wb") as f:
            f.write(stl_bytes)
        with open(sp, "w") as f:
            f.write(code)
        with open(cp, "w") as f:
            json.dump(components, f)
        proc = await asyncio.create_subprocess_exec(
            sys.executable, RUNNER, inp, sp, out, cp,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=td,
        )
        try:
            so, se = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return {"ok": False, "error": f"Temps d'exécution dépassé ({timeout}s)"}
        lines = [ln for ln in so.decode(errors="ignore").strip().splitlines() if ln.startswith("{")]
        if not lines:
            return {"ok": False, "error": "Le script a planté", "traceback": se.decode(errors="ignore")[-2500:]}
        res = json.loads(lines[-1])
        if res.get("ok"):
            with open(out, "rb") as f:
                res["stl"] = f.read()
        return res
