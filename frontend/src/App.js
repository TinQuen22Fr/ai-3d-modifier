import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "@/App.css";
import { Toaster, toast } from "sonner";
import {
  Box, Cpu, Download, Layers, Trash2, Grid3x3, Crosshair, Image as ImageIcon, Upload, PanelLeftClose, PanelLeftOpen, Pencil, Check,
} from "lucide-react";
import Viewer3D from "./components/Viewer3D";
import ChatPanel from "./components/ChatPanel";
import UploadZone from "./components/UploadZone";
import ComponentLibrary from "./components/ComponentLibrary";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "./components/ui/dialog";
import { http, errMsg, stlUrl, downloadUrl, renderUrl } from "./lib/api";

const VIEWS = [
  ["iso", "Iso"],
  ["front", "Face"],
  ["back", "Arrière"],
  ["right", "Droite"],
  ["left", "Gauche"],
  ["top", "Dessus"],
  ["bottom", "Dessous"],
];

const fmt = (n) => (n == null ? "-" : Number(n).toFixed(1));

export default function App() {
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState(null);
  const [messages, setMessages] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [points, setPoints] = useState([]);
  const [pickMode, setPickMode] = useState(false);
  const [wire, setWire] = useState(false);
  const [components, setComponents] = useState([]);
  const [labels, setLabels] = useState({});
  const [libOpen, setLibOpen] = useState(false);
  const [renderOpen, setRenderOpen] = useState(false);
  const [sidebar, setSidebar] = useState(true);
  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const viewerRef = useRef(null);
  const versionInputRef = useRef(null);

  const loadProjects = useCallback(async () => {
    try {
      const { data } = await http.get("/projects");
      setProjects(data);
      return data;
    } catch (e) {
      toast.error(errMsg(e));
      return [];
    }
  }, []);

  const loadComponents = useCallback(async () => {
    const { data } = await http.get("/components");
    setComponents(data.items);
    setLabels(data.labels);
  }, []);

  const openProject = useCallback(async (pid) => {
    try {
      const { data } = await http.get(`/projects/${pid}`);
      setProject(data);
      setMessages(data.messages || []);
      setPoints([]);
      setPickMode(false);
      localStorage.setItem("stl-last-project", pid);
    } catch (e) {
      toast.error(errMsg(e));
    }
  }, []);

  useEffect(() => {
    loadComponents().catch(() => {});
    loadProjects().then((list) => {
      const last = localStorage.getItem("stl-last-project");
      const target = list.find((p) => p.id === last) || list[0];
      if (target) openProject(target.id);
    });
  }, [loadProjects, loadComponents, openProject]);

  const current = useMemo(
    () => project?.versions?.find((v) => v.id === project.current_version_id) || project?.versions?.[project.versions.length - 1],
    [project]
  );

  const uploadNew = async (file) => {
    if (!file.name.toLowerCase().endsWith(".stl")) return toast.error("Seuls les fichiers .stl sont acceptés");
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await http.post("/projects", fd);
      toast.success(`Pièce « ${data.name} » importée`);
      await loadProjects();
      await openProject(data.id);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setUploading(false);
    }
  };

  const uploadVersion = async (file) => {
    if (!file || !project) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await http.post(`/projects/${project.id}/versions`, fd);
      toast.success("Nouvelle version importée");
      await openProject(project.id);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setUploading(false);
    }
  };

  const selectVersion = async (vid) => {
    if (!project || vid === current?.id) return;
    try {
      await http.post(`/projects/${project.id}/current`, { version_id: vid });
      setProject((p) => ({ ...p, current_version_id: vid }));
      setPoints([]);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const deleteProject = async (p) => {
    if (!window.confirm(`Supprimer le projet « ${p.name} » et toutes ses versions ?`)) return;
    await http.delete(`/projects/${p.id}`);
    const list = await loadProjects();
    if (project?.id === p.id) {
      if (list[0]) openProject(list[0].id);
      else {
        setProject(null);
        setMessages([]);
      }
    }
  };

  const rename = async () => {
    const name = nameDraft.trim();
    setRenaming(false);
    if (!name || name === project.name) return;
    await http.patch(`/projects/${project.id}`, { name });
    setProject((p) => ({ ...p, name }));
    loadProjects();
  };

  const onPick = async (pt) => {
    if (!current) return;
    if (points.length >= 8) return toast.error("8 points maximum");
    const tmp = { point: pt, note: "" };
    setPoints((ps) => [...ps, tmp]);
    try {
      const { data } = await http.post("/point-info", { version_id: current.id, point: pt });
      setPoints((ps) => ps.map((p) => (p === tmp ? { ...p, point: data.point, normal: data.normal, thickness: data.thickness } : p)));
    } catch (_) {}
  };

  const onVersionCreated = (v) => {
    setProject((p) => ({ ...p, versions: [...p.versions, v], current_version_id: v.id }));
    loadProjects();
  };

  const st = current?.stats;

  return (
    <div className="app">
      <Toaster theme="dark" position="top-center" richColors />
      <header className="topbar">
        <div className="brand" data-testid="brand">
          <button className="icon-btn" onClick={() => setSidebar(!sidebar)} data-testid="toggle-sidebar-btn" title="Projets">
            {sidebar ? <PanelLeftClose size={17} /> : <PanelLeftOpen size={17} />}
          </button>
          <div className="logo"><Box size={17} /></div>
          <span className="brand-name">Atelier STL</span>
          <span className="brand-tag">IA</span>
        </div>
        <div className="topbar-center">
          {project &&
            (renaming ? (
              <div className="rename">
                <input
                  className="input sm"
                  autoFocus
                  value={nameDraft}
                  onChange={(e) => setNameDraft(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && rename()}
                  onBlur={rename}
                  data-testid="project-name-input"
                />
                <button className="icon-btn" onClick={rename}><Check size={15} /></button>
              </div>
            ) : (
              <button className="project-name" onClick={() => { setNameDraft(project.name); setRenaming(true); }} data-testid="project-name">
                {project.name} <Pencil size={13} />
              </button>
            ))}
        </div>
        <div className="topbar-actions">
          <button className="btn ghost sm" onClick={() => setLibOpen(true)} data-testid="open-library-btn">
            <Cpu size={15} /> Modules
          </button>
          {current && (
            <a className="btn primary sm" href={downloadUrl(current.id)} data-testid="download-stl-btn">
              <Download size={15} /> Télécharger v{current.number}
            </a>
          )}
        </div>
      </header>

      <div className="body">
        {sidebar && (
          <nav className="sidebar" data-testid="projects-sidebar">
            <UploadZone compact onFile={uploadNew} uploading={uploading} testId="sidebar-upload" />
            <div className="sidebar-label">Mes pièces</div>
            <div className="project-list">
              {projects.length === 0 && <div className="muted small pad">Aucune pièce pour l'instant.</div>}
              {projects.map((p) => (
                <div
                  key={p.id}
                  className={`project-item ${project?.id === p.id ? "active" : ""}`}
                  onClick={() => openProject(p.id)}
                  data-testid={`project-item-${p.id}`}
                >
                  <Layers size={15} />
                  <div className="project-item-main">
                    <div className="project-item-name">{p.name}</div>
                    <div className="project-item-sub">{p.versions_count} version{p.versions_count > 1 ? "s" : ""}</div>
                  </div>
                  <button
                    className="icon-btn tiny hover-show"
                    onClick={(e) => { e.stopPropagation(); deleteProject(p); }}
                    data-testid={`delete-project-${p.id}`}
                    title="Supprimer"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>
          </nav>
        )}

        <main className="stage">
          {!project ? (
            <div className="hero" data-testid="empty-state">
              <div className="hero-inner">
                <h1>Modifiez vos pièces 3D <span className="accent">en discutant</span></h1>
                <p className="hero-sub">
                  Importez un fichier .stl, puis demandez à l'IA d'adapter la pièce : remplacer une fenêtre d'écran par un emplacement OLED SSD1306 ou SH1106, ajouter des trous de fixation, reboucher une ouverture...
                </p>
                <UploadZone onFile={uploadNew} uploading={uploading} testId="hero-upload" />
                <div className="hero-steps">
                  <div><span>1</span> Importez votre .stl</div>
                  <div><span>2</span> Cliquez la zone à modifier</div>
                  <div><span>3</span> Décrivez le changement</div>
                  <div><span>4</span> Téléchargez la nouvelle version</div>
                </div>
              </div>
            </div>
          ) : (
            <>
              <div className="viewer-wrap">
                <Viewer3D
                  ref={viewerRef}
                  url={current ? stlUrl(current.id) : null}
                  points={points}
                  pickMode={pickMode}
                  onPick={onPick}
                  wireframe={wire}
                />
                <div className="view-toolbar" data-testid="view-toolbar">
                  {VIEWS.map(([k, l]) => (
                    <button key={k} className="tb-btn" onClick={() => viewerRef.current?.setView(k)} data-testid={`view-${k}-btn`}>{l}</button>
                  ))}
                  <span className="tb-sep" />
                  <button className={`tb-btn ${wire ? "on" : ""}`} onClick={() => setWire(!wire)} title="Fil de fer" data-testid="wireframe-btn"><Grid3x3 size={14} /></button>
                  <button className={`tb-btn ${pickMode ? "on" : ""}`} onClick={() => setPickMode(!pickMode)} title="Désigner un point" data-testid="toolbar-pick-btn"><Crosshair size={14} /></button>
                  <button className="tb-btn" onClick={() => setRenderOpen(true)} title="Vues envoyées à l'IA" data-testid="show-render-btn"><ImageIcon size={14} /></button>
                </div>
                {pickMode && (
                  <div className="pick-hint" data-testid="pick-hint">
                    <Crosshair size={14} /> Cliquez sur la pièce pour placer un point (P{points.length + 1}). Glissez pour tourner.
                  </div>
                )}
                {st && (
                  <div className="stats-card" data-testid="stats-card">
                    <div className="stats-title">v{current.number} · {current.source === "ai" ? "IA" : "import"}</div>
                    <div className="stats-dims">
                      <span><b>X</b> {fmt(st.size[0])}</span>
                      <span><b>Y</b> {fmt(st.size[1])}</span>
                      <span><b>Z</b> {fmt(st.size[2])}</span>
                      <span className="muted">mm</span>
                    </div>
                    <div className="stats-sub">
                      {st.faces.toLocaleString("fr-FR")} triangles · {st.watertight ? <span className="ok">étanche</span> : <span className="warn">non étanche</span>}
                      {st.volume_cm3 != null && ` · ${st.volume_cm3} cm³`}
                    </div>
                  </div>
                )}
              </div>

              <div className="versions" data-testid="versions-bar">
                <div className="versions-label">Versions</div>
                <div className="versions-track">
                  {project.versions.map((v) => (
                    <button
                      key={v.id}
                      className={`version-chip ${v.id === current?.id ? "active" : ""} src-${v.source}`}
                      onClick={() => selectVersion(v.id)}
                      title={v.label}
                      data-testid={`version-chip-${v.number}`}
                    >
                      <span className="vnum">v{v.number}</span>
                      <span className="vlabel">{v.label}</span>
                    </button>
                  ))}
                </div>
                <input ref={versionInputRef} type="file" accept=".stl" hidden onChange={(e) => { uploadVersion(e.target.files?.[0]); e.target.value = ""; }} data-testid="upload-version-input" />
                <button className="btn ghost sm" onClick={() => versionInputRef.current?.click()} disabled={uploading} data-testid="upload-version-btn" title="Importer un .stl comme nouvelle version">
                  <Upload size={14} /> Importer
                </button>
              </div>
            </>
          )}
        </main>

        {project && (
          <ChatPanel
            key={project.id}
            project={project}
            messages={messages}
            setMessages={setMessages}
            points={points}
            setPoints={setPoints}
            pickMode={pickMode}
            setPickMode={setPickMode}
            onVersionCreated={onVersionCreated}
            onShowVersion={selectVersion}
            components={components}
            baseVersion={current}
          />
        )}
      </div>

      <ComponentLibrary open={libOpen} onOpenChange={setLibOpen} components={components} labels={labels} reload={loadComponents} />

      <Dialog open={renderOpen} onOpenChange={setRenderOpen}>
        <DialogContent className="render-dialog">
          <DialogHeader>
            <DialogTitle>Vues envoyées à l'IA (v{current?.number})</DialogTitle>
            <DialogDescription className="muted">
              L'IA reçoit ces 4 vues avec les cotes, en plus des points que vous désignez.
            </DialogDescription>
          </DialogHeader>
          {current && <img src={renderUrl(current.id)} alt="vues" className="render-img" data-testid="render-img" />}
        </DialogContent>
      </Dialog>
    </div>
  );
}
