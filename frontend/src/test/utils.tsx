import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { Api } from "../lib/api";
import { AuthContext, type AuthValue } from "../lib/auth";
import { ApiContext, DataProvider } from "../lib/data";
import type { Bootstrap, ChatEvent } from "../lib/types";

export const BOOT: Bootstrap = {
  user: { id: "u1", email: "aun@example.com" },
  consent: { accepted: true, current_version: "v1", training_opt_in: false },
  profile: { role: "Analyst", industry: "", goals: "", cv_text: "" },
  documents: { items: [], budget: { used: 0, limit: 80000, left_out: [], clipped: [] } },
  conversations: [],
};

/** An Api where every method is a vi.fn(); override what a test cares about. */
export function fakeApi(overrides: Partial<Record<keyof Api, unknown>> = {}): Api {
  const api = {
    bootstrap: vi.fn(async () => BOOT),
    acceptConsent: vi.fn(async () => undefined),
    setTrainingOptIn: vi.fn(async () => undefined),
    getProfile: vi.fn(async () => BOOT.profile),
    saveProfile: vi.fn(async (p) => p),
    uploadDocuments: vi.fn(),
    setDocumentEnabled: vi.fn(),
    deleteDocument: vi.fn(),
    conversations: vi.fn(async () => []),
    conversation: vi.fn(async () => []),
    endConversation: vi.fn(async () => ({ summarised: true })),
    setFeedback: vi.fn(async () => undefined),
    chat: vi.fn(),
    deleteMyData: vi.fn(async () => undefined),
    ...overrides,
  };
  return api as unknown as Api;
}

export function fakeAuth(overrides: Partial<AuthValue> = {}): AuthValue {
  return {
    status: "signedIn",
    email: "aun@example.com",
    sendCode: vi.fn(async () => undefined),
    verifyCode: vi.fn(async () => undefined),
    signOut: vi.fn(async () => undefined),
    getToken: vi.fn(async () => "token"),
    ...overrides,
  };
}

export async function* events(...list: ChatEvent[]): AsyncGenerator<ChatEvent> {
  for (const event of list) yield event;
}

/** Render a page inside the real providers, with fake network. Child pages read data via useData(). */
export function renderPage(ui: ReactElement, opts: { api?: Api; auth?: AuthValue; route?: string; path?: string; paths?: string[] } = {}) {
  const api = opts.api ?? fakeApi();
  const auth = opts.auth ?? fakeAuth();
  return {
    api,
    auth,
    ...render(
      <AuthContext.Provider value={auth}>
        <ApiContext.Provider value={api}>
          <DataProvider>
            <MemoryRouter initialEntries={[opts.route ?? "/"]}>
              <Routes>
                {(opts.paths ?? [opts.path ?? "*"]).map((path) => (
                  <Route key={path} path={path} element={ui} />
                ))}
              </Routes>
            </MemoryRouter>
          </DataProvider>
        </ApiContext.Provider>
      </AuthContext.Provider>,
    ),
  };
}
