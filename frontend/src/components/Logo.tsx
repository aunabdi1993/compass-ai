export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" role="img" aria-label="Compass logo">
      <rect width="32" height="32" rx="8" fill="var(--brand)" />
      <circle cx="16" cy="16" r="9" fill="none" stroke="#fff" strokeWidth="2" />
      <path d="M16 8l3.2 8-3.2 8-3.2-8z" fill="#fff" />
    </svg>
  );
}
