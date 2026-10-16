import { useMemo } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { createApi } from "./lib/api";
import { useAuth } from "./lib/auth";
import { ApiContext, DataProvider, useData } from "./lib/data";
import { Chat } from "./pages/Chat";
import { Consent } from "./pages/Consent";
import { Documents } from "./pages/Documents";
import { Login } from "./pages/Login";
import { Privacy } from "./pages/Privacy";
import { Profile } from "./pages/Profile";

function Gate() {
  const { boot } = useData();
  // Nothing else is loaded or shown until the user has agreed to the privacy notice.
  if (!boot.consent.accepted) return <Consent />;
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Chat />} />
        <Route path="/c/:conversationId" element={<Chat />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/documents" element={<Documents />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  );
}

function Authenticated() {
  const { getToken, signOut } = useAuth();
  const api = useMemo(() => createApi(getToken, () => void signOut()), [getToken, signOut]);
  return (
    <ApiContext.Provider value={api}>
      <DataProvider>
        <Gate />
      </DataProvider>
    </ApiContext.Provider>
  );
}

export function App() {
  const { status, error } = useAuth();
  if (status === "loading") return <div className="splash" role="status">Loading…</div>;
  if (status === "error") return <div className="splash"><p>{error}</p></div>;
  if (status === "signedOut") return <Login />;
  return <Authenticated />;
}
