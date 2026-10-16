import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { useData } from "../lib/data";
import { Logo } from "./Logo";

export function Shell({ children }: { children: ReactNode }) {
  const { email, signOut } = useAuth();
  const { boot } = useData();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);

  useEffect(() => setOpen(false), [location.pathname]); // close the drawer after navigating on mobile

  return (
    <div className={`shell ${open ? "drawer-open" : ""}`}>
      <header className="topbar">
        <button className="icon-btn" aria-label="Open menu" aria-expanded={open} onClick={() => setOpen(!open)}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
        </button>
        <span className="brand"><Logo size={24} /> Compass</span>
      </header>

      <aside className="sidebar" aria-label="Main">
        <div className="brand"><Logo size={28} /> <span>Compass</span></div>
        <button className="btn primary block" onClick={() => navigate("/")}>New chat</button>
        <nav className="nav">
          <NavLink to="/" end className={({ isActive }) => (isActive || location.pathname.startsWith("/c/") ? "active" : "")}>Coach</NavLink>
          <NavLink to="/profile">Profile</NavLink>
          <NavLink to="/documents">Documents</NavLink>
          <NavLink to="/privacy">Privacy</NavLink>
        </nav>
        <div className="history">
          <h2>Recent conversations</h2>
          {(boot.conversations ?? []).length === 0 && <p className="hint">Nothing yet.</p>}
          <ul>
            {(boot.conversations ?? []).map((c) => (
              <li key={c.id}>
                <NavLink to={`/c/${c.id}`} title={c.title}>{c.title}</NavLink>
              </li>
            ))}
          </ul>
        </div>
        <div className="account">
          <div className="email" title={email ?? ""}>{email}</div>
          <button className="btn small" onClick={() => void signOut()}>Sign out</button>
        </div>
      </aside>
      {open && <div className="scrim" onClick={() => setOpen(false)} />}
      <main className="content">{children}</main>
    </div>
  );
}
