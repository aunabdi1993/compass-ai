import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Api } from "./api";
import type { Bootstrap, Consent, ConversationSummary, DocumentsState, Profile } from "./types";

export const ApiContext = createContext<Api | null>(null);

export function useApi(): Api {
  const api = useContext(ApiContext);
  if (!api) throw new Error("useApi must be used inside an <ApiContext.Provider>");
  return api;
}

export interface DataValue {
  boot: Bootstrap;
  setConsent(consent: Consent): void;
  setProfile(profile: Profile): void;
  setDocuments(documents: DocumentsState): void;
  setConversations(conversations: ConversationSummary[]): void;
  reload(): Promise<void>;
}

export const DataContext = createContext<DataValue | null>(null);

export function useData(): DataValue {
  const value = useContext(DataContext);
  if (!value) throw new Error("useData must be used inside <DataProvider>");
  return value;
}

type Phase = { name: "loading" } | { name: "error"; message: string } | { name: "ready"; boot: Bootstrap };

/** Loads everything the app needs once after sign-in, then keeps it in sync as pages change it. */
export function DataProvider({ children }: { children: ReactNode }) {
  const api = useApi();
  const [phase, setPhase] = useState<Phase>({ name: "loading" });

  const load = useCallback(async () => {
    try {
      setPhase({ name: "ready", boot: await api.bootstrap() });
    } catch (error) {
      setPhase({ name: "error", message: error instanceof Error ? error.message : "Couldn't load your data." });
    }
  }, [api]);

  useEffect(() => {
    void load();
  }, [load]);

  const update = useCallback((change: (boot: Bootstrap) => Bootstrap) => {
    setPhase((current) => (current.name === "ready" ? { name: "ready", boot: change(current.boot) } : current));
  }, []);

  const value = useMemo<DataValue | null>(() => {
    if (phase.name !== "ready") return null;
    return {
      boot: phase.boot,
      setConsent: (consent) => update((b) => ({ ...b, consent })),
      setProfile: (profile) => update((b) => ({ ...b, profile })),
      setDocuments: (documents) => update((b) => ({ ...b, documents })),
      setConversations: (conversations) => update((b) => ({ ...b, conversations })),
      reload: load,
    };
  }, [phase, update, load]);

  if (phase.name === "loading") return <div className="splash" role="status">Loading…</div>;
  if (phase.name === "error" || !value) {
    return (
      <div className="splash">
        <p>{phase.name === "error" ? phase.message : "Couldn't load your data."}</p>
        <button className="btn" onClick={() => void load()}>Try again</button>
      </div>
    );
  }
  return <DataContext.Provider value={value}>{children}</DataContext.Provider>;
}
