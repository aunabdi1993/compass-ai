import { useState, type FormEvent } from "react";
import { useApi, useData } from "../lib/data";
import type { Profile as ProfileData } from "../lib/types";

const EMPTY: ProfileData = { role: "", industry: "", goals: "", cv_text: "" };

export function Profile() {
  const api = useApi();
  const { boot, setProfile } = useData();
  const [form, setForm] = useState<ProfileData>({ ...EMPTY, ...boot.profile });
  const [status, setStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [error, setError] = useState<string | null>(null);

  const field = (name: keyof ProfileData) => ({
    value: form[name],
    onChange: (e: { target: { value: string } }) => {
      setForm({ ...form, [name]: e.target.value });
      setStatus("idle");
    },
  });

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setStatus("saving");
    setError(null);
    try {
      const saved = await api.saveProfile(form);
      setProfile(saved);
      setStatus("saved");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save your profile.");
      setStatus("idle");
    }
  }

  return (
    <section className="page">
      <h1>Your profile</h1>
      <p className="muted">Compass uses this in every conversation so you don't have to repeat yourself. Leave anything blank that you'd rather not share.</p>
      <form onSubmit={onSubmit} className="stack">
        <div>
          <label htmlFor="role">Current role</label>
          <input id="role" maxLength={200} {...field("role")} />
        </div>
        <div>
          <label htmlFor="industry">Industry</label>
          <input id="industry" maxLength={200} {...field("industry")} />
        </div>
        <div>
          <label htmlFor="goals">Career goals</label>
          <textarea id="goals" rows={4} maxLength={3000} {...field("goals")} />
          <p className="hint">For example: promoted to senior within 12 months, or move into product.</p>
        </div>
        <div>
          <label htmlFor="cv">CV (paste the text)</label>
          <textarea id="cv" rows={10} maxLength={20000} {...field("cv_text")} />
          <p className="hint">Or upload your CV as a file on the Documents page.</p>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="row">
          <button className="btn primary" disabled={status === "saving"}>{status === "saving" ? "Saving…" : "Save"}</button>
          {status === "saved" && <span className="success" role="status">Saved.</span>}
        </div>
      </form>
    </section>
  );
}
