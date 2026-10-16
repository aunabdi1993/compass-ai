import { readSSE } from "./sse";
import type {
  Bootstrap,
  ChatEvent,
  ConversationSummary,
  ChatMessage,
  DocumentsState,
  Feedback,
  Profile,
  PublicConfig,
  UploadResult,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export type TokenGetter = () => Promise<string | null>;

export interface Api {
  bootstrap(): Promise<Bootstrap>;
  acceptConsent(trainingOptIn: boolean): Promise<void>;
  setTrainingOptIn(optedIn: boolean): Promise<void>;
  getProfile(): Promise<Profile>;
  saveProfile(profile: Profile): Promise<Profile>;
  uploadDocuments(files: File[]): Promise<{ results: UploadResult[] } & DocumentsState>;
  setDocumentEnabled(id: string, enabled: boolean): Promise<DocumentsState>;
  deleteDocument(id: string): Promise<DocumentsState>;
  conversations(): Promise<ConversationSummary[]>;
  conversation(id: string): Promise<ChatMessage[]>;
  endConversation(id: string): Promise<{ summarised: boolean }>;
  setFeedback(messageId: number, value: Feedback): Promise<void>;
  chat(message: string, conversationId: string | null, signal?: AbortSignal): AsyncGenerator<ChatEvent>;
  deleteMyData(): Promise<void>;
}

/** Public config (no sign-in needed): where Supabase is, so the browser can sign users in. */
export async function fetchConfig(): Promise<PublicConfig> {
  const response = await fetch("/api/config");
  if (!response.ok) throw new ApiError(response.status, "Couldn't load the app configuration.");
  return response.json();
}

async function errorFrom(response: Response): Promise<ApiError> {
  let message = "Something went wrong. Please try again.";
  try {
    const body = await response.json();
    if (typeof body.detail === "string") message = body.detail;
  } catch {
    /* not JSON: keep the generic message */
  }
  return new ApiError(response.status, message);
}

export function createApi(getToken: TokenGetter, onUnauthorized: () => void): Api {
  async function send(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<Response> {
    const token = await getToken();
    if (!token) {
      onUnauthorized();
      throw new ApiError(401, "Please sign in.");
    }
    const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
    let payload: BodyInit | undefined;
    if (body instanceof FormData) {
      payload = body; // the browser sets the multipart boundary
    } else if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
    let response: Response;
    try {
      response = await fetch(path, { method, headers, body: payload, signal });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new ApiError(0, "Couldn't reach Compass. Check your connection and try again.");
    }
    if (response.status === 401) onUnauthorized();
    if (!response.ok) throw await errorFrom(response);
    return response;
  }

  const json = async <T>(method: string, path: string, body?: unknown): Promise<T> =>
    (await send(method, path, body)).json() as Promise<T>;

  return {
    bootstrap: () => json("GET", "/api/bootstrap"),
    acceptConsent: async (trainingOptIn) => {
      await json("POST", "/api/consent", { agree: true, training_opt_in: trainingOptIn });
    },
    setTrainingOptIn: async (optedIn) => {
      await json("PUT", "/api/consent/training", { opted_in: optedIn });
    },
    getProfile: () => json("GET", "/api/profile"),
    saveProfile: (profile) => json("PUT", "/api/profile", profile),
    uploadDocuments: (files) => {
      const form = new FormData();
      files.forEach((file) => form.append("files", file));
      return json("POST", "/api/documents", form);
    },
    setDocumentEnabled: (id, enabled) => json("PATCH", `/api/documents/${encodeURIComponent(id)}`, { enabled }),
    deleteDocument: (id) => json("DELETE", `/api/documents/${encodeURIComponent(id)}`),
    conversations: async () => (await json<{ items: ConversationSummary[] }>("GET", "/api/conversations")).items,
    conversation: async (id) =>
      (await json<{ messages: ChatMessage[] }>("GET", `/api/conversations/${encodeURIComponent(id)}`)).messages,
    endConversation: (id) => json("POST", `/api/conversations/${encodeURIComponent(id)}/end`),
    setFeedback: async (messageId, value) => {
      await json("POST", `/api/messages/${messageId}/feedback`, { value });
    },
    async *chat(message, conversationId, signal) {
      const response = await send("POST", "/api/chat", { message, conversation_id: conversationId }, signal);
      if (!response.body) throw new ApiError(0, "The reply didn't arrive. Please try again.");
      for await (const frame of readSSE(response.body)) {
        yield { event: frame.event, data: JSON.parse(frame.data) } as ChatEvent;
      }
    },
    deleteMyData: async () => {
      await json("DELETE", "/api/me/data", { confirm: "DELETE" });
    },
  };
}
