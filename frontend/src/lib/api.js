import axios from "axios";

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const http = axios.create({ baseURL: API });

export const stlUrl = (vid) => `${API}/versions/${vid}/stl`;
export const downloadUrl = (vid) => `${API}/versions/${vid}/stl?download=1`;
export const renderUrl = (vid) => `${API}/versions/${vid}/render`;

export const errMsg = (e) =>
  e?.response?.data?.detail || e?.message || "Erreur inconnue";

/** Lance le chat IA en streaming (SSE via fetch POST). */
export async function streamChat(projectId, body, onEvent, signal) {
  const res = await fetch(`${API}/projects/${projectId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    let detail = `Erreur ${res.status}`;
    try {
      const j = await res.json();
      detail = j.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const line = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (line) {
        try {
          onEvent(JSON.parse(line.slice(6)));
        } catch (_) {}
      }
    }
  }
}
