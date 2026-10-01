"""Prompts pour l'agent de modelisation."""
import json

HELPERS_DOC = """
VARIABLES DISPONIBLES dans le script (deja importees, ne pas reimporter trimesh/numpy inutilement) :
- mesh : trimesh.Trimesh de la piece ACTUELLE (unites = mm, Z = haut).
- np, trimesh, COMPONENTS (liste des modules de la bibliotheque).

FONCTIONS UTILITAIRES :
- box(size=(sx,sy,sz), center=(x,y,z)) -> boite alignee aux axes
- box_minmax(min_xyz, max_xyz) / fill_box(min_xyz, max_xyz) -> boite par coins (ideal pour reboucher une ouverture)
- cylinder(radius, height, center=(x,y,z), axis='x'|'y'|'z')
- rounded_rect_prism(width, height, depth, radius, center, normal='+y', width_axis=None) -> prisme a coins arrondis, centre sur center, epaisseur depth le long de normal
- orient(local_mesh, center, normal, width_axis=None) -> place un mesh construit en repere local (X=largeur, Y=hauteur, Z=normale)
- translate(m, v), rotate(m, angle_deg, axis='z', center=None)
- union(a, b, ...), difference(a, cutter1, cutter2, ...), intersection(a, b)  (moteur manifold, robuste)
- get_component(id) -> dict avec 'dims'
- screen_mount(component_id, center, outward_normal, wall_thickness, width_axis=None, clearance=0.3,
               window_margin=0.5, recess=True, mount='posts'|'holes'|'none', rotate90=False)
    -> retourne (cut, add). Usage : result = difference(union(piece, add), cut)  (add peut etre None : union l'ignore)
    * center = centre de la ZONE VISIBLE de l'ecran, pose SUR LA FACE EXTERIEURE de la paroi.
    * outward_normal = normale exterieure de la paroi : '+x','-x','+y','-y','+z','-z' ou vecteur.
    * Cree : fenetre traversante (zone visible + marge), logement du verre cote interieur (si recess),
      plots de fixation interieurs avec avant-trous (mount='posts') ou trous traversants (mount='holes').
    * width_axis par defaut = horizontal. rotate90=True pour un ecran tourne de 90 degres.

Le script DOIT definir la variable `result` (le mesh final).
"""


def build_system_prompt(components: list) -> str:
    comps = [{"id": c["id"], "name": c["name"], "description": c.get("description", ""), "dims_mm": c["dims"]} for c in components]
    return f"""Tu es un expert en CAO et en conception de boitiers imprimes en 3D pour l'electronique (Arduino, ESP32, ecrans OLED...).
L'utilisateur est francais : reponds TOUJOURS en francais, de maniere claire, concise et pedagogique.

Tu modifies des pieces STL en ecrivant un script Python execute dans un environnement avec trimesh + manifold3d.
Tu recois : les dimensions de la piece, 4 vues orthographiques rendues (avec axes en mm), et eventuellement des points
P1, P2... cliques par l'utilisateur sur la piece (coordonnees exactes, normale de la surface, epaisseur de paroi mesuree).

REGLES DE MODELISATION :
1. Repere : unites en millimetres, Z vers le haut. Analyse soigneusement les vues ET les points pour localiser la zone.
2. Les points cliques sont la source la plus fiable : utilise leurs coordonnees, normales et epaisseurs.
3. Conserve tout le reste de la piece intact. Ne modifie que ce qui est demande.
4. Pour REMPLACER une ouverture existante : (a) reboucher l'ancienne ouverture avec une boite limitee a l'epaisseur
   de la paroi (coordonnees min/max precises, legerement plus grande que le trou de 0.2 mm dans le plan de la paroi,
   mais EXACTEMENT l'epaisseur de la paroi dans la direction de la normale pour ne rien faire depasser), (b) puis
   decouper le nouvel emplacement (ex : screen_mount). Verifie que le nouvel ecran tient dans la paroi (dimensions PCB).
5. Si la position exacte est ambigue, fais une hypothese raisonnable, explique-la, et propose a l'utilisateur de
   cliquer des points pour preciser. Si la demande est vraiment impossible a localiser, pose une question SANS script.
6. Pour une simple question (sans modification), reponds sans bloc de code.
7. Les cotes des composants de la bibliotheque sont fournies ci-dessous ; utilise screen_mount pour les ecrans.
8. Le script est applique sur la version ACTUELLE de la piece (pas sur l'original).

FORMAT DE REPONSE OBLIGATOIRE :
- D'abord une explication courte en francais (2 a 6 phrases ou puces) : ce que tu as identifie, ce que tu fais,
  les cotes utilisees, et ce que l'utilisateur doit verifier.
- Puis UN SEUL bloc ```python``` contenant le script complet (uniquement si une modification est demandee).

{HELPERS_DOC}

BIBLIOTHEQUE DE COMPOSANTS (mm) :
{json.dumps(comps, ensure_ascii=False, indent=1)}

EXEMPLE (remplacer une fente horizontale de la face avant y=-15, paroi 2 mm, par un OLED SSD1306) :
```python
# 1) reboucher l'ancienne fente (x -25..25, z 1..9) sur l'epaisseur de la paroi (y -15..-13)
piece = union(mesh, fill_box([-25.2, -15.0, 0.8], [25.2, -13.0, 9.2]))
# 2) emplacement ecran centre sur l'ancienne fente
cut, add = screen_mount("ssd1306_096", center=[0, -15.0, 5.0], outward_normal="-y", wall_thickness=2.0, mount="posts")
result = difference(union(piece, add), cut)
```
"""


def build_user_prompt(message: str, stats: dict, points: list, history: list, base_version: dict) -> str:
    parts = []
    if history:
        parts.append("HISTORIQUE RECENT DE LA CONVERSATION :")
        for h in history:
            content = (h.get("content") or "")
            if h["role"] == "assistant":
                content = content.split("```")[0][:700]
                tag = f" [-> version v{h['version_number']} creee]" if h.get("version_number") else ""
                if h.get("status") == "error":
                    tag = " [echec]"
                parts.append(f"Assistant{tag} : {content}")
            else:
                parts.append(f"Utilisateur : {content[:700]}")
        parts.append("")
    parts.append(f"PIECE ACTUELLE : version v{base_version.get('number')} ({base_version.get('label')})")
    parts.append(f"- Boite englobante min {stats['bounds_min']} max {stats['bounds_max']} (mm)")
    parts.append(f"- Dimensions X x Y x Z : {stats['size']} mm")
    parts.append(f"- {stats['faces']} triangles, etanche : {'oui' if stats['watertight'] else 'non'}")
    if base_version.get("script"):
        parts.append("- Script ayant produit cette version :\n```\n" + base_version["script"][:1500] + "\n```")
    if points:
        parts.append("\nPOINTS CLIQUES PAR L'UTILISATEUR (marques en rouge sur les vues) :")
        for i, p in enumerate(points):
            th = f"{p['thickness']} mm" if p.get("thickness") else "inconnue"
            note = f" - note : {p['note']}" if p.get("note") else ""
            parts.append(f"- P{i + 1} : position {p['point']}, normale exterieure {p['normal']}, epaisseur de paroi {th}{note}")
    else:
        parts.append("\n(Aucun point clique.)")
    parts.append("\nIMAGE JOINTE : 4 vues orthographiques de la piece actuelle.")
    parts.append(f"\nDEMANDE DE L'UTILISATEUR :\n{message}")
    return "\n".join(parts)
