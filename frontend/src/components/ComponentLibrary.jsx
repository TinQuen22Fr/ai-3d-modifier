import React, { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "./ui/dialog";
import { Plus, Save, Trash2, Cpu, ArrowLeft } from "lucide-react";
import { toast } from "sonner";
import { http, errMsg } from "../lib/api";

const EMPTY_DIMS = {
  pcb_w: 30, pcb_h: 30, pcb_t: 1.2, glass_w: 28, glass_h: 20, glass_t: 1.5, glass_offset_x: 0, glass_offset_y: 0,
  view_w: 24, view_h: 13, view_offset_x: 0, view_offset_y: 0, hole_d: 2, hole_dx: 25, hole_dy: 25,
};

export default function ComponentLibrary({ open, onOpenChange, components, labels, reload }) {
  const [edit, setEdit] = useState(null);
  useEffect(() => {
    if (!open) setEdit(null);
  }, [open]);

  const save = async () => {
    try {
      const body = { name: edit.name, category: edit.category, description: edit.description, dims: Object.fromEntries(Object.entries(edit.dims).map(([k, v]) => [k, parseFloat(v) || 0])) };
      if (edit.id) await http.put(`/components/${edit.id}`, body);
      else await http.post("/components", body);
      toast.success("Composant enregistré");
      await reload();
      setEdit(null);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const del = async (c) => {
    if (!window.confirm(`Supprimer ${c.name} ?`)) return;
    await http.delete(`/components/${c.id}`);
    await reload();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="lib-dialog" data-testid="component-library-dialog">
        <DialogHeader>
          <DialogTitle className="lib-title"><Cpu size={18} className="accent" /> Bibliothèque de modules</DialogTitle>
          <DialogDescription className="muted">
            Cotes (en mm) transmises à l'IA. Valeurs par défaut approximatives : vérifiez-les au pied à coulisse sur vos modules.
          </DialogDescription>
        </DialogHeader>
        {!edit ? (
          <div className="lib-list">
            {components.map((c) => (
              <div key={c.id} className="lib-card" data-testid={`component-card-${c.id}`}>
                <div className="lib-card-main">
                  <div className="lib-name">{c.name}</div>
                  <div className="lib-sub">
                    PCB {c.dims.pcb_w}×{c.dims.pcb_h} · verre {c.dims.glass_w}×{c.dims.glass_h} · visible {c.dims.view_w}×{c.dims.view_h} · trous Ø{c.dims.hole_d} ({c.dims.hole_dx}×{c.dims.hole_dy})
                  </div>
                  <code className="lib-id">{c.id}</code>
                </div>
                <div className="lib-actions">
                  <button className="btn ghost sm" onClick={() => setEdit({ ...c, dims: { ...EMPTY_DIMS, ...c.dims } })} data-testid={`edit-component-${c.id}`}>Modifier</button>
                  {!c.builtin && (
                    <button className="icon-btn" onClick={() => del(c)} data-testid={`delete-component-${c.id}`}><Trash2 size={14} /></button>
                  )}
                </div>
              </div>
            ))}
            <button className="btn ghost add-comp" onClick={() => setEdit({ name: "", category: "Ecran", description: "", dims: { ...EMPTY_DIMS } })} data-testid="add-component-btn">
              <Plus size={15} /> Ajouter un module
            </button>
          </div>
        ) : (
          <div className="lib-edit">
            <button className="btn ghost sm" onClick={() => setEdit(null)}><ArrowLeft size={14} /> Retour</button>
            <div className="form-row">
              <label>Nom</label>
              <input className="input" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} data-testid="component-name-input" />
            </div>
            <div className="form-row two">
              <div>
                <label>Catégorie</label>
                <input className="input" value={edit.category} onChange={(e) => setEdit({ ...edit, category: e.target.value })} />
              </div>
              <div>
                <label>Description (pour l'IA)</label>
                <input className="input" value={edit.description} onChange={(e) => setEdit({ ...edit, description: e.target.value })} />
              </div>
            </div>
            <div className="dims-grid">
              {Object.keys(EMPTY_DIMS).map((k) => (
                <div key={k} className="dim">
                  <label>{labels[k] || k}</label>
                  <input
                    className="input"
                    type="number"
                    step="0.1"
                    value={edit.dims[k]}
                    onChange={(e) => setEdit({ ...edit, dims: { ...edit.dims, [k]: e.target.value } })}
                    data-testid={`dim-${k}`}
                  />
                </div>
              ))}
            </div>
            <button className="btn primary" onClick={save} disabled={!edit.name.trim()} data-testid="save-component-btn">
              <Save size={15} /> Enregistrer
            </button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
