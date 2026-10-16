import { useRef, useState, type DragEvent } from "react";
import { useApi, useData } from "../lib/data";
import type { UploadResult } from "../lib/types";

export const ALLOWED = ["pdf", "docx", "txt", "md"];
export const MAX_BYTES = 10 * 1024 * 1024;

export function checkFile(file: File): string | null {
  const ext = file.name.includes(".") ? file.name.split(".").pop()!.toLowerCase() : "";
  if (!ALLOWED.includes(ext)) return "Please upload a PDF, Word (.docx), text or Markdown file.";
  if (file.size > MAX_BYTES) return "That file is over 10 MB. Please upload a smaller one.";
  return null;
}

export function Documents() {
  const api = useApi();
  const { boot, setDocuments } = useData();
  const docs = boot.documents ?? { items: [], budget: { used: 0, limit: 80000, left_out: [], clipped: [] } };
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [results, setResults] = useState<UploadResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement | null>(null);

  async function upload(files: File[]) {
    if (!files.length) return;
    setError(null);
    const rejected: UploadResult[] = [];
    const accepted: File[] = [];
    for (const file of files) {
      const problem = checkFile(file);
      if (problem) rejected.push({ name: file.name, ok: false, error: problem });
      else accepted.push(file);
    }
    setResults(rejected);
    if (!accepted.length) return;
    setBusy(true);
    try {
      const response = await api.uploadDocuments(accepted);
      setDocuments({ items: response.items, budget: response.budget });
      setResults([...rejected, ...response.results]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't upload those files.");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  async function change(action: () => Promise<{ items: typeof docs.items; budget: typeof docs.budget }>) {
    setError(null);
    try {
      setDocuments(await action());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't update your documents.");
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    void upload(Array.from(event.dataTransfer.files));
  }

  const { budget } = docs;
  const percent = Math.min(100, Math.round((budget.used / budget.limit) * 100));
  return (
    <section className="page">
      <h1>Your documents</h1>
      <p className="muted">
        Add things Compass should know about: your CV, a job description, performance review notes, a development plan.
        Compass reads the documents that are switched on in every conversation and refers to them by name, so its advice
        stays relevant to you.
      </p>
      <p className="notice">Please don't upload confidential employer documents or other people's personal details. Only the text is kept, not the original file.</p>

      <div className={`dropzone ${dragging ? "dragging" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={onDrop}>
        <p>Drag files here, or</p>
        <button className="btn" disabled={busy} onClick={() => input.current?.click()}>{busy ? "Adding…" : "Choose files"}</button>
        <input ref={input} type="file" multiple hidden accept=".pdf,.docx,.txt,.md" aria-label="Choose files to upload"
          onChange={(e) => void upload(Array.from(e.target.files ?? []))} />
        <p className="hint">PDF, Word (.docx), text or Markdown. Up to 10 MB each, 10 documents.</p>
      </div>

      {error && <p className="error" role="alert">{error}</p>}
      {results.length > 0 && (
        <ul className="results" aria-label="Upload results">
          {results.map((r, i) => (
            <li key={`${r.name}-${i}`} className={r.ok ? "success" : "error"}>
              {r.ok ? `Added ${r.name}${r.truncated ? " (long, so only the first part was kept)" : ""}` : `${r.name}: ${r.error}`}
            </li>
          ))}
        </ul>
      )}

      {docs.items.length === 0 ? (
        <p className="muted">No documents yet.</p>
      ) : (
        <>
          <div className="budget">
            <div className="budget-label">Context in use: {budget.used.toLocaleString()} of {budget.limit.toLocaleString()} characters</div>
            <div className="bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} aria-label="Context in use">
              <div style={{ width: `${percent}%` }} />
            </div>
            {budget.left_out.length > 0 && (
              <p className="warning">These didn't fit, so Compass can't see them right now: {budget.left_out.join(", ")}. Switch off or remove other documents to make room.</p>
            )}
            {budget.left_out.length === 0 && budget.clipped.length > 0 && (
              <p className="warning">{budget.clipped.join(", ")} is partly cut to fit. Switch off or remove documents to make room.</p>
            )}
          </div>
          <ul className="doc-list">
            {docs.items.map((doc) => (
              <li key={doc.id} className="doc">
                <button role="switch" aria-checked={doc.enabled} aria-label={`Use ${doc.name} in conversations`}
                  className={`switch ${doc.enabled ? "on" : ""}`} onClick={() => void change(() => api.setDocumentEnabled(doc.id, !doc.enabled))}>
                  <span />
                </button>
                <div className="doc-info">
                  <div className="doc-name">{doc.name}</div>
                  <div className="hint">{doc.char_count.toLocaleString()} characters{doc.truncated ? " (cut short)" : ""}{doc.enabled ? "" : " · switched off"}</div>
                </div>
                <button className="btn small" aria-label={`Remove ${doc.name}`} onClick={() => void change(() => api.deleteDocument(doc.id))}>Remove</button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
