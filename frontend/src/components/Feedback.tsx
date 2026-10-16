import type { Feedback as FeedbackValue } from "../lib/types";

function Thumb({ up }: { up: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={up ? undefined : { transform: "rotate(180deg)" }}>
      <path d="M7 10v11H3V10h4zm0 0l4-8a2 2 0 0 1 2 2v4h6.3a2 2 0 0 1 2 2.3l-1.4 8a2 2 0 0 1-2 1.7H7" />
    </svg>
  );
}

export function Feedback({ value, onChange }: { value: FeedbackValue | undefined; onChange: (next: FeedbackValue) => void }) {
  return (
    <div className="feedback" role="group" aria-label="Rate this reply">
      <button type="button" className="icon-btn" aria-label="Good reply" aria-pressed={value === 1}
        onClick={() => onChange(value === 1 ? null : 1)}><Thumb up /></button>
      <button type="button" className="icon-btn" aria-label="Bad reply" aria-pressed={value === -1}
        onClick={() => onChange(value === -1 ? null : -1)}><Thumb up={false} /></button>
    </div>
  );
}
