import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import { ChevronDown, ChevronRight, Code2, Copy, Check } from "lucide-react";

function CodeBlock({ code, open: initialOpen = false }) {
  const [open, setOpen] = useState(initialOpen);
  const [copied, setCopied] = useState(false);
  return (
    <div className="codeblock">
      <button className="codeblock-head" onClick={() => setOpen(!open)} data-testid="toggle-script-btn">
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Code2 size={14} /> Script de modélisation
        <span className="codeblock-lines">{code.split("\n").length} lignes</span>
      </button>
      {open && (
        <div className="codeblock-body">
          <button
            className="codeblock-copy"
            onClick={() => {
              navigator.clipboard?.writeText(code);
              setCopied(true);
              setTimeout(() => setCopied(false), 1200);
            }}
          >
            {copied ? <Check size={13} /> : <Copy size={13} />}
          </button>
          <pre>{code}</pre>
        </div>
      )}
    </div>
  );
}

/** Affiche le texte de l'IA : markdown + blocs de code repliables. */
export default function Markdown({ text, streaming }) {
  const parts = [];
  const re = /```(?:python|py)?\s*\n([\s\S]*?)(```|$)/g;
  let last = 0;
  let m;
  while ((m = re.exec(text || ""))) {
    if (m.index > last) parts.push({ t: "md", v: text.slice(last, m.index) });
    parts.push({ t: "code", v: m[1].trimEnd(), closed: m[2] === "```" });
    last = re.lastIndex;
    if (!m[2]) break;
  }
  if (last < (text || "").length) parts.push({ t: "md", v: text.slice(last) });
  return (
    <div className="md">
      {parts.map((p, i) =>
        p.t === "md" ? (
          <ReactMarkdown key={i}>{p.v}</ReactMarkdown>
        ) : streaming && !p.closed ? (
          <div key={i} className="codeblock writing">
            <Code2 size={14} /> Écriture du script... <span className="codeblock-lines">{p.v.split("\n").length} lignes</span>
          </div>
        ) : (
          <CodeBlock key={i} code={p.v} />
        )
      )}
    </div>
  );
}
