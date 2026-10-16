import { useState, type FormEvent } from "react";
import { Logo } from "../components/Logo";
import { useAuth } from "../lib/auth";

export function Login() {
  const { sendCode, verifyCode } = useAuth();
  const [email, setEmail] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice] = useState<string | null>(() => {
    try {
      const saved = sessionStorage.getItem("compass-notice"); // e.g. "your data has been deleted"
      sessionStorage.removeItem("compass-notice");
      return saved;
    } catch {
      return null;
    }
  });

  async function onSend(event: FormEvent) {
    event.preventDefault();
    const address = email.trim();
    if (!address) return;
    setBusy(true);
    setError(null);
    try {
      await sendCode(address);
      setSentTo(address);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send the email.");
    } finally {
      setBusy(false);
    }
  }

  async function onVerify(event: FormEvent) {
    event.preventDefault();
    if (!sentTo || !code.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await verifyCode(sentTo, code);
    } catch (e) {
      setError(e instanceof Error ? e.message : "That code didn't work.");
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-card">
        <Logo size={40} />
        <h1>Compass</h1>
        <p className="muted">Your AI career coach. Sign in with your email, no password needed.</p>
        {notice && <p className="notice" role="status">{notice}</p>}

        {sentTo === null ? (
          <form onSubmit={onSend}>
            <label htmlFor="email">Email address</label>
            <input id="email" type="email" autoComplete="email" autoFocus required value={email}
              onChange={(e) => setEmail(e.target.value)} />
            {error && <p className="error" role="alert">{error}</p>}
            <button className="btn primary block" disabled={busy || !email.trim()}>
              {busy ? "Sending…" : "Email me a code"}
            </button>
          </form>
        ) : (
          <form onSubmit={onVerify}>
            <p className="notice">We sent a code to <strong>{sentTo}</strong>. It can take a minute to arrive.</p>
            <label htmlFor="code">Code from the email</label>
            <input id="code" inputMode="numeric" autoComplete="one-time-code" autoFocus maxLength={10}
              value={code} onChange={(e) => setCode(e.target.value)} />
            {error && <p className="error" role="alert">{error}</p>}
            <button className="btn primary block" disabled={busy || !code.trim()}>
              {busy ? "Checking…" : "Sign in"}
            </button>
            <button type="button" className="link" onClick={() => { setSentTo(null); setCode(""); setError(null); }}>
              Use a different email
            </button>
          </form>
        )}
      </div>
    </main>
  );
}
