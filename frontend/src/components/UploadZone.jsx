import React, { useRef, useState } from "react";
import { UploadCloud, Loader2 } from "lucide-react";

export default function UploadZone({ onFile, uploading, compact, testId = "upload-zone" }) {
  const inputRef = useRef(null);
  const [over, setOver] = useState(false);
  const handle = (files) => {
    const f = files?.[0];
    if (f) onFile(f);
  };
  return (
    <div
      className={`upload ${compact ? "compact" : ""} ${over ? "over" : ""}`}
      onClick={() => !uploading && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        handle(e.dataTransfer.files);
      }}
      data-testid={testId}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".stl"
        hidden
        onChange={(e) => {
          handle(e.target.files);
          e.target.value = "";
        }}
        data-testid={`${testId}-input`}
      />
      {uploading ? <Loader2 className="spin" size={compact ? 16 : 34} /> : <UploadCloud size={compact ? 16 : 40} />}
      {compact ? (
        <span>{uploading ? "Import..." : "Importer un .stl"}</span>
      ) : (
        <>
          <div className="upload-title">{uploading ? "Analyse du fichier..." : "Déposez votre pièce .stl ici"}</div>
          <div className="upload-sub">ou cliquez pour choisir un fichier (max 60 Mo)</div>
        </>
      )}
    </div>
  );
}
