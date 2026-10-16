import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { fetchConfig } from "./api";

export type AuthStatus = "loading" | "signedOut" | "signedIn" | "error";

export interface AuthValue {
  status: AuthStatus;
  error?: string;
  email: string | null;
  sendCode(email: string): Promise<void>;
  verifyCode(email: string, code: string): Promise<void>;
  signOut(): Promise<void>;
  getToken(): Promise<string | null>;
}

export const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}

/** If an emailed link was expired or already used, Supabase sends the user back with the reason in the URL. */
export function linkErrorFromUrl(hash: string): string | null {
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  const description = params.get("error_description") ?? params.get("error");
  if (!description) return null;
  const code = params.get("error_code") ?? "";
  if (code.includes("expired") || description.toLowerCase().includes("expired") || description.toLowerCase().includes("invalid")) {
    return "That sign-in link has expired or was already used. Enter your email to get a new one.";
  }
  return "That sign-in link didn't work. Enter your email to get a new one.";
}

/** Turn Supabase's error text into something a user can act on. */
export function friendlyAuthError(message: string): string {
  const text = message.toLowerCase();
  if (text.includes("expired") || text.includes("invalid")) {
    return "That code didn't work. Check it and try again, or request a new one.";
  }
  if (text.includes("security purposes") || text.includes("rate limit")) {
    return "Please wait a minute before asking for another code.";
  }
  if (text.includes("email")) return "That email address doesn't look right.";
  return "Something went wrong. Please try again.";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useRef<SupabaseClient | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [error, setError] = useState<string>();
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    let unsubscribe: (() => void) | undefined;
    let cancelled = false;
    (async () => {
      try {
        const config = await fetchConfig();
        const supabase = createClient(config.supabase_url, config.supabase_publishable_key, {
          auth: { persistSession: true, autoRefreshToken: true }, // stays signed in across reloads
        });
        client.current = supabase;
        const { data } = await supabase.auth.getSession();
        if (cancelled) return;
        setEmail(data.session?.user.email ?? null);
        setStatus(data.session ? "signedIn" : "signedOut");
        const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
          setEmail(session?.user.email ?? null);
          setStatus(session ? "signedIn" : "signedOut");
        });
        unsubscribe = () => sub.subscription.unsubscribe();
      } catch {
        if (!cancelled) {
          setError("Couldn't start Compass. Please refresh the page.");
          setStatus("error");
        }
      }
    })();
    return () => {
      cancelled = true;
      unsubscribe?.();
    };
  }, []);

  const sendCode = useCallback(async (address: string) => {
    const { error: err } = await client.current!.auth.signInWithOtp({
      email: address,
      // Where the emailed link brings the user back to; supabase-js then signs them in from the URL.
      options: { shouldCreateUser: true, emailRedirectTo: window.location.origin },
    });
    if (err) throw new Error(friendlyAuthError(err.message));
  }, []);

  const verifyCode = useCallback(async (address: string, code: string) => {
    const { error: err } = await client.current!.auth.verifyOtp({ email: address, token: code.trim(), type: "email" });
    if (err) throw new Error(friendlyAuthError(err.message));
  }, []);

  const signOut = useCallback(async () => {
    await client.current?.auth.signOut();
  }, []);

  // getSession() refreshes the access token when it is about to expire.
  const getToken = useCallback(async () => {
    const { data } = (await client.current?.auth.getSession()) ?? { data: { session: null } };
    return data.session?.access_token ?? null;
  }, []);

  const value = useMemo<AuthValue>(
    () => ({ status, error, email, sendCode, verifyCode, signOut, getToken }),
    [status, error, email, sendCode, verifyCode, signOut, getToken],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
