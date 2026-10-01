import sys, asyncio, io
sys.path.insert(0, "/app/backend")
import trimesh, numpy as np
from cad_engine import load_mesh, repair, mesh_stats, render_views, point_info, run_script, to_stl_bytes
from components_default import DEFAULT_COMPONENTS

# Boitier test 80x30x40, paroi 2mm, ouvert a l'arriere, fente ecran horizontale 50x8 en face avant (y=-15)
outer = trimesh.creation.box(extents=[80, 30, 40])
inner = trimesh.creation.box(extents=[76, 30, 36]); inner.apply_translation([0, 2, 0])
slot = trimesh.creation.box(extents=[50, 6, 8]); slot.apply_translation([0, -15, 5])
part = trimesh.boolean.difference([outer, inner, slot], engine="manifold")
data = part.export(file_type="stl")
open("/tmp/test_part.stl", "wb").write(data)

m = repair(load_mesh(data))
print("stats", mesh_stats(m))
print("point", point_info(m, [10, -15.2, -8]))
open("/tmp/render_in.png", "wb").write(render_views(m, [{"point": [10, -15, -8]}]))

code = '''
fill = box_minmax([-25.2, -15.0, 0.8], [25.2, -13.0, 9.2])
part = union(mesh, fill)
cut, add = screen_mount("ssd1306_096", center=[0, -15, 3], outward_normal="-y", wall_thickness=2.0)
result = difference(union(part, add), cut)
'''
res = asyncio.run(run_script(to_stl_bytes(m), code, DEFAULT_COMPONENTS))
print("run", {k: v for k, v in res.items() if k != "stl"})
if res.get("ok"):
    out = load_mesh(res["stl"])
    print("out stats", mesh_stats(out))
    open("/tmp/render_out.png", "wb").write(render_views(out))
bad = asyncio.run(run_script(to_stl_bytes(m), "result = foo()", DEFAULT_COMPONENTS))
print("error case", bad.get("ok"), bad.get("error"))
