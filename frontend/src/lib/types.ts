export interface Consent {
  accepted: boolean;
  current_version: string;
  training_opt_in: boolean;
}

export interface Profile {
  role: string;
  industry: string;
  goals: string;
  cv_text: string;
}

export interface DocItem {
  id: string;
  name: string;
  char_count: number;
  truncated: boolean;
  enabled: boolean;
  created_at: string;
}

export interface Budget {
  used: number;
  limit: number;
  left_out: string[];
  clipped: string[];
}

export interface DocumentsState {
  items: DocItem[];
  budget: Budget;
}

export interface UploadResult {
  name: string;
  ok: boolean;
  error?: string;
  truncated?: boolean;
}

export interface ConversationSummary {
  id: string;
  created_at: string;
  title: string;
  ended: boolean;
}

export type Feedback = 1 | -1 | null;

export interface ChatMessage {
  id: number | string;
  role: "user" | "assistant";
  content: string;
  feedback?: Feedback;
  streaming?: boolean;
}

export interface Bootstrap {
  user: { id: string; email: string };
  consent: Consent;
  profile?: Profile;
  documents?: DocumentsState;
  conversations?: ConversationSummary[];
}

export type ChatEvent =
  | { event: "meta"; data: { conversation_id: string; user_message_id: number } }
  | { event: "delta"; data: { text: string } }
  | { event: "done"; data: { message_id: number } }
  | { event: "error"; data: { message: string } };

export interface PublicConfig {
  supabase_url: string;
  supabase_publishable_key: string;
}
