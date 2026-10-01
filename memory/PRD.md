# Atelier STL IA — PRD

## Problème
Application simple (en français) : importer une pièce 3D .stl puis la modifier par chat IA, ex. remplacer une fenêtre d'écran horizontale par un emplacement pour écran OLED SSD1306 / SH1106 128x64. À terme : réutilisable pour d'autres modules électroniques.

## Choix utilisateur
- IA : Claude Sonnet 4.5 + Gemini 3 (Flash / 3.1 Pro) via clé universelle Emergent
- Désignation de points en cliquant sur la pièce 3D
- Historique des versions + téléchargement .stl
- Interface 100 % français
- Économiser les crédits : tests limités, l'utilisateur teste lui-même en preview

## Architecture
- Backend FastAPI : server.py (API /api), cad_engine.py (chargement/réparation STL, stats, rendu 4 vues matplotlib, analyse de points : normale + épaisseur de paroi), cad_runner.py (exécution sandbox subprocess du script IA, helpers trimesh+manifold3d : box, fill_box, cylinder, union/difference, screen_mount...), prompts.py, components_default.py
- Stockage MongoDB + GridFS (STL + rendus)
- Chat en streaming SSE, auto-correction jusqu'à 3 tentatives si le script échoue
- Frontend React + three.js (viewer, picking, marqueurs P1..), chat, versions, bibliothèque de modules éditable

## Implémenté (2026-10)
- Import STL, projets, renommage, suppression
- Viewer 3D (vues prédéfinies, fil de fer), désignation de points avec épaisseur de paroi
- Chat IA → script → nouvelle version ; script visible ; erreurs affichées
- Versions : sélection = base des prochaines modifs ; import d'une version ; téléchargement
- Bibliothèque modules (SSD1306 0.96", SH1106 1.3" ; cotes approximatives éditables ; ajout de modules)
- Vue « ce que voit l'IA »

## Backlog
- P1 : vérifier/ajuster les cotes réelles des modules de l'utilisateur
- P2 : autres modules (boutons, connecteurs USB-C, capteurs), aperçu avant/après, export 3MF
