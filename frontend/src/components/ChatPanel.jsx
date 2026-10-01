import React, { useEffect, useRef, useState } from "react";
import { Send, Loader2, Sparkles, MousePointerClick, X, CheckCircle2, AlertTriangle, Eye, Trash2, Square } from "lucide-react";
import { toast } from "sonner";
import Markdown from "./Markdown";
import { streamChat, http, errMsg } from "../lib/api";

const MODEL_LABELS = {
  "claude-sonnet-4-5": "Claude Sonnet 4.5",
  "gemini-3-flash": "Gemini 3 Flash",
  "gemini-3.1-pro": "Gemini 3.1 Pro",
};

export default function ChatPanel({
  project, messages, setMessages, points, setPoints, pickMode, setPickMode,
  onVersionCreated, onShowVersion, components, baseVersion,
}) {
  const [text, setText] = useState("");
  const [model, setModel] = useState(() => localStorage.getItem("stl-model") || "claude-sonnet-4-5");
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(null); // {text, status, errors:[]}
  const scrollRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => localStorage.setItem("stl-model", model), [model]);
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, live]);

  const quick = [
    ...components.filter((c) => c.category === "Ecran").slice(0, 3).map((c) => ({
      label: `Remplacer l'écran par ${c.name.replace("OLED ", "")}`,
      prompt: `Remplace l'emplacement d'écran existant (l'ouverture longue horizontale) par un emplacement pour un écran ${c.name}, centré au même endroit, avec plots de fixation à l'intérieur.`,
    })),
    { label: "Décris cette pièce", prompt: "Décris-moi cette pièce : ses dimensions, ses ouvertures et l'épaisseur des parois." },
  ];

  const send = async (override) => {
    const msg = (override ?? text).trim();
    if (!msg || busy || !project) return;
    setBusy(true);
    setText("");
    setPickMode(false);
    setLive({ text: "", status: "Envoi...", errors: [] });
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    let created = null;
    try {
      await streamChat(
        project.id,
        { message: msg, model, points: points.map((p) => ({ point: p.point, note: p.note || "" })), version_id: baseVersion?.id },
        (ev) => {
          if (ev.type === "user") setMessages((m) => [...m, ev.message]);
          else if (ev.type === "status") setLive((l) => ({ ...l, status: ev.text }));
          else if (ev.type === "delta") setLive((l) => ({ ...l, text: l.text + ev.text }));
          else if (ev.type === "exec_error") setLive((l) => ({ ...l, errors: [...l.errors, ev.text] }));
          else if (ev.type === "error") toast.error(ev.text);
          else if (ev.type === "version") created = ev.version;
          else if (ev.type === "done") setMessages((m) => [...m, ev.message]);
        },
        ctrl.signal
      );
      if (created) {
        setPoints([]);
        onVersionCreated(created);
        toast.success(`Nouvelle version v${created.number} créée`);
      }
    } catch (e) {
      if (e.name !== "AbortError") toast.error(errMsg(e));
    } finally {
      setBusy(false);
      setLive(null);
      abortRef.current = null;
    }
  };

  const clearChat = async () => {
    if (!window.confirm("Effacer toute la conversation de ce projet ? (les versions sont conservées)")) return;
    try {
      await http.delete(`/projects/${project.id}/messages`);
      setMessages([]);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  return (
    <aside className="chat" data-testid="chat-panel">
      <div className="chat-head">
        <div className="chat-title">
          <Sparkles size={16} className="accent" /> Assistant IA
        </div>
        <div className="chat-head-actions">
          <select
            className="select"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            disabled={busy}
            data-testid="model-select"
          >
            {Object.entries(MODEL_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          {messages.length > 0 && (
            <button className="icon-btn" onClick={clearChat} title="Effacer la conversation" data-testid="clear-chat-btn">
              <Trash2 size={15} />
            </button>
          )}
        </div>
      </div>

      <div className="chat-scroll" ref={scrollRef} data-testid="chat-messages">
        {messages.length === 0 && !live && (
          <div className="chat-empty">
            <p className="chat-empty-title">Décrivez la modification souhaitée</p>
            <p>
              Exemple : <em>« Remplace l'espace d'écran horizontal par un emplacement pour un écran OLED SSD1306 0.96" »</em>
            </p>
            <p className="muted">
              Astuce : activez <b>Désigner un point</b> puis cliquez sur la pièce pour indiquer à l'IA l'endroit exact (ex : le bord de l'ouverture actuelle).
            </p>
          </div>
        )}
        {messages.map((m) => (
          <Message key={m.id} m={m} onShowVersion={onShowVersion} />
        ))}
        {live && (
          <div className="msg assistant" data-testid="live-message">
            <div className="msg-meta">{MODEL_LABELS[model]}</div>
            {live.text ? <Markdown text={live.text} streaming /> : null}
            {live.errors.map((er, i) => (
              <div key={i} className="exec-error"><AlertTriangle size={13} /> {er}</div>
            ))}
            <div className="live-status" data-testid="live-status">
              <Loader2 size={14} className="spin" /> {live.status}
            </div>
          </div>
        )}
      </div>

      <div className="chat-compose">
        {points.length > 0 && (
          <div className="points" data-testid="points-list">
            {points.map((p, i) => (
              <div className="point-chip" key={i} data-testid={`point-chip-${i + 1}`}>
                <span className="point-tag">P{i + 1}</span>
                <span className="point-coords">
                  {p.point.map((v) => v.toFixed(1)).join(", ")}
                  {p.thickness ? ` · paroi ${p.thickness.toFixed(1)} mm` : ""}
                </span>
                <input
                  className="point-note"
                  placeholder="note (ex : bord gauche)"
                  value={p.note || ""}
                  onChange={(e) => setPoints(points.map((q, j) => (j === i ? { ...q, note: e.target.value } : q)))}
                  data-testid={`point-note-${i + 1}`}
                />
                <button className="icon-btn tiny" onClick={() => setPoints(points.filter((_, j) => j !== i))} data-testid={`remove-point-${i + 1}`}>
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
        {!busy && messages.length < 2 && (
          <div className="quick">
            {quick.map((q) => (
              <button key={q.label} className="quick-chip" onClick={() => setText(q.prompt)} data-testid="quick-prompt">
                {q.label}
              </button>
            ))}
          </div>
        )}
        <div className="compose-box">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder={busy ? "L'IA travaille..." : "Que voulez-vous modifier ? (Entrée pour envoyer)"}
            rows={3}
            disabled={busy}
            data-testid="chat-input"
          />
          <div className="compose-actions">
            <button
              className={`btn ghost sm ${pickMode ? "active" : ""}`}
              onClick={() => setPickMode(!pickMode)}
              disabled={busy}
              data-testid="pick-mode-btn"
            >
              <MousePointerClick size={14} /> {pickMode ? "Cliquez sur la pièce..." : "Désigner un point"}
            </button>
            <span className="compose-base">sur v{baseVersion?.number ?? "-"}</span>
            {busy ? (
              <button className="btn danger sm" onClick={() => abortRef.current?.abort()} data-testid="stop-btn">
                <Square size={13} /> Stop
              </button>
            ) : (
              <button className="btn primary sm" onClick={() => send()} disabled={!text.trim()} data-testid="send-btn">
                <Send size={14} /> Envoyer
              </button>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}

function Message({ m, onShowVersion }) {
  if (m.role === "user") {
    return (
      <div className="msg user" data-testid="user-message">
        <div className="msg-text">{m.content}</div>
        {m.points?.length > 0 && (
          <div className="msg-points">
            {m.points.map((_, i) => <span key={i} className="point-tag sm">P{i + 1}</span>)}
          </div>
        )}
      </div>
    );
  }
  return (
    <div className="msg assistant" data-testid="assistant-message">
      <div className="msg-meta">{MODEL_LABELS[m.model] || m.model}</div>
      <Markdown text={m.content} />
      {m.status === "ok" && m.version_id && (
        <button className="version-pill ok" onClick={() => onShowVersion(m.version_id)} data-testid="show-version-btn">
          <CheckCircle2 size={14} /> Version v{m.version_number} créée <Eye size={13} />
        </button>
      )}
      {m.status === "error" && (
        <div className="version-pill err" data-testid="error-pill">
          <AlertTriangle size={14} /> Échec de la modification{m.error ? ` : ${m.error.slice(0, 160)}` : ""}
        </div>
      )}
    </div>
  );
}
