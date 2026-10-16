import { useState, type FormEvent } from "react";
import { Logo } from "../components/Logo";
import { useApi, useData } from "../lib/data";

export function Consent() {
  const api = useApi();
  const { boot, setConsent, reload } = useData();
  const [agreed, setAgreed] = useState(false);
  const [training, setTraining] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!agreed) {
      setError("Please tick the first box to continue.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.acceptConsent(training);
      setConsent({ ...boot.consent, accepted: true, training_opt_in: training });
      await reload(); // now that consent is recorded, load the profile, documents and history
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save your choice.");
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-card wide">
        <Logo size={40} />
        <h1>Welcome to Compass</h1>
        <p><strong>Before you start, here is how Compass works with your information.</strong></p>
        <ul className="consent-list">
          <li><strong>Compass is an AI coach, not a human.</strong> It can be wrong. It does not give legal, medical or
            financial advice. For a workplace dispute, speak to ACAS, a union rep or an employment lawyer. If you are
            struggling, speak to your GP, someone you trust, or Samaritans (116 123).</li>
          <li><strong>What we store:</strong> your conversations, the profile and documents you add, short summaries of
            past sessions, and your thumbs up/down ratings. They are tied to your sign-in email and used only to give
            you coaching that remembers you.</li>
          <li><strong>Who processes it:</strong> your messages, profile and documents are sent to an AI model provider
            (via OpenRouter) each time you chat, so the coach can reply.</li>
          <li><strong>Please don't share</strong> confidential employer information, or other people's personal details.</li>
          <li><strong>You are in control:</strong> you can switch documents off or remove them, and delete all of your
            data at any time from the Privacy page.</li>
        </ul>
        <form onSubmit={onSubmit}>
          <label className="check">
            <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
            <span>I understand how Compass uses my information, and I agree.</span>
          </label>
          <label className="check">
            <input type="checkbox" checked={training} onChange={(e) => setTraining(e.target.checked)} />
            <span>
              <strong>Optional:</strong> allow my chats to be used, after names, emails and company names are removed,
              to improve Compass and train future versions. This is separate from the box above, and leaving it
              unticked changes nothing for you. You can change your mind on the Privacy page.
            </span>
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="btn primary" disabled={busy}>{busy ? "Saving…" : "Continue"}</button>
        </form>
      </div>
    </main>
  );
}
