import { useState, type FormEvent } from "react";
import { useAuth } from "../lib/auth";
import { useApi, useData } from "../lib/data";

export function Privacy() {
  const api = useApi();
  const { signOut } = useAuth();
  const { boot, setConsent } = useData();
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const training = boot.consent.training_opt_in;

  async function toggleTraining() {
    setError(null);
    try {
      await api.setTrainingOptIn(!training);
      setConsent({ ...boot.consent, training_opt_in: !training });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save that choice.");
    }
  }

  async function onDelete(event: FormEvent) {
    event.preventDefault();
    if (confirm.trim() !== "DELETE") {
      setError("Type DELETE (in capitals) to confirm.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.deleteMyData();
      sessionStorage.setItem("compass-notice", "Your conversations, documents and profile have been deleted. Your sign-in email still exists; ask us if you'd like that removed too.");
      await signOut();
    } catch (e) {
      setError(`Couldn't delete your data: ${e instanceof Error ? e.message : "please try again."} Nothing was changed.`);
      setBusy(false);
    }
  }

  return (
    <section className="page">
      <h1>Privacy</h1>
      <p className="muted">You agreed to how Compass uses your information. Your messages, profile and documents are sent to an AI model provider each time you chat.</p>

      <h2>Improving Compass</h2>
      <div className="setting">
        <button role="switch" aria-checked={training} aria-label="Allow my chats to be used for improving Compass"
          className={`switch ${training ? "on" : ""}`} onClick={() => void toggleTraining()}><span /></button>
        <span>Allow my chats to be used, with names, emails and company names removed, to improve and train Compass.</span>
      </div>

      <h2>Delete my data</h2>
      <p>This permanently removes all of your conversations, session summaries, documents, profile and consent record. It can't be undone. You will be signed out.</p>
      <form onSubmit={onDelete} className="stack danger-zone">
        <label htmlFor="confirm">Type DELETE to confirm</label>
        <input id="confirm" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn danger" disabled={busy}>{busy ? "Deleting…" : "Delete everything"}</button>
      </form>
    </section>
  );
}
