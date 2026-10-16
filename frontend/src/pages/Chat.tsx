import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import Markdown from "react-markdown";
import { useNavigate, useParams } from "react-router-dom";
import { Feedback } from "../components/Feedback";
import { Logo } from "../components/Logo";
import { useApi, useData } from "../lib/data";
import type { ChatMessage, Feedback as FeedbackValue } from "../lib/types";

const STARTERS = [
  "Help me prepare for my annual review",
  "I want to build a case for a promotion",
  "Should I stay or look for a new job?",
];

export function Chat() {
  const { conversationId: routeId } = useParams();
  const navigate = useNavigate();
  const api = useApi();
  const { setConversations } = useData();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(routeId ?? null);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const abort = useRef<AbortController | null>(null);
  const createdHere = useRef<string | null>(null); // a conversation this component just started streaming into
  const endRef = useRef<HTMLDivElement | null>(null);

  const refreshList = useCallback(() => {
    api.conversations().then(setConversations).catch(() => undefined);
  }, [api, setConversations]);

  // Open the conversation named in the URL (or an empty chat at "/").
  useEffect(() => {
    if (routeId && routeId === createdHere.current) return; // we are already showing it
    abort.current?.abort();
    createdHere.current = null;
    setConversationId(routeId ?? null);
    setError(null);
    if (!routeId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    api
      .conversation(routeId)
      .then((loaded) => !cancelled && setMessages(loaded))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "Couldn't open that conversation."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [routeId, api]);

  useEffect(() => () => abort.current?.abort(), []);
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [messages]);

  async function send(text: string) {
    const content = text.trim();
    if (!content || sending) return;
    setError(null);
    setNotice(null);
    setSending(true);
    setDraft("");
    const stamp = Date.now();
    const userTemp = `u-${stamp}`;
    const assistantTemp = `a-${stamp}`;
    setMessages((m) => [
      ...m,
      { id: userTemp, role: "user", content },
      { id: assistantTemp, role: "assistant", content: "", streaming: true },
    ]);
    const controller = new AbortController();
    abort.current = controller;
    const patch = (id: string, change: Partial<ChatMessage>) =>
      setMessages((m) => m.map((x) => (x.id === id ? { ...x, ...change } : x)));
    const dropPlaceholder = () => setMessages((m) => m.filter((x) => !(x.id === assistantTemp && !x.content)));
    let finished = false;
    try {
      for await (const event of api.chat(content, conversationId, controller.signal)) {
        if (event.event === "meta") {
          patch(userTemp, { id: event.data.user_message_id });
          if (event.data.conversation_id !== conversationId) {
            createdHere.current = event.data.conversation_id;
            setConversationId(event.data.conversation_id);
            navigate(`/c/${event.data.conversation_id}`, { replace: true });
          }
        } else if (event.event === "delta") {
          setMessages((m) => m.map((x) => (x.id === assistantTemp ? { ...x, content: x.content + event.data.text } : x)));
        } else if (event.event === "done") {
          finished = true;
          patch(assistantTemp, { id: event.data.message_id, streaming: false });
        } else if (event.event === "error") {
          setError(event.data.message);
          dropPlaceholder();
          finished = true;
        }
      }
      if (!finished) {
        setError("The reply was cut off. Please try again.");
        patch(assistantTemp, { streaming: false });
        dropPlaceholder();
      }
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError")) {
        setError(e instanceof Error ? e.message : "Something went wrong. Please try again.");
        dropPlaceholder();
      }
    } finally {
      setSending(false);
      refreshList();
    }
  }

  async function rate(message: ChatMessage, value: FeedbackValue) {
    if (typeof message.id !== "number") return;
    const previous = message.feedback ?? null;
    setMessages((m) => m.map((x) => (x.id === message.id ? { ...x, feedback: value } : x)));
    try {
      await api.setFeedback(message.id, value);
    } catch {
      setMessages((m) => m.map((x) => (x.id === message.id ? { ...x, feedback: previous } : x)));
      setError("Couldn't save your rating.");
    }
  }

  async function endSession() {
    if (!conversationId) return;
    setError(null);
    try {
      const { summarised } = await api.endConversation(conversationId);
      refreshList();
      navigate("/");
      setNotice(summarised ? "Saved a note so Compass remembers this next time." : "Session ended.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't end the session.");
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send(draft);
    }
  }

  const empty = messages.length === 0 && !loading;
  return (
    <section className="chat">
      <header className="chat-header">
        <h1>Coach</h1>
        <div className="chat-actions">
          <button className="btn small" onClick={() => { setNotice(null); navigate("/"); }} disabled={sending}>New chat</button>
          <button className="btn small" onClick={() => void endSession()} disabled={!conversationId || sending}
            title="Compass writes itself a short note so it remembers this next time.">End session</button>
        </div>
      </header>

      <div className="messages" aria-live="polite">
        {loading && <p className="muted center">Loading…</p>}
        {empty && (
          <div className="greeting">
            <Logo size={48} />
            <h2>Hi, I'm Compass, an AI career coach.</h2>
            <p className="muted">
              Tell me about your current role and what you'd like to work on: a review, a skill, a promotion, or a
              move. Please don't share confidential employer information or colleagues' personal details.
            </p>
            {notice && <p className="notice">{notice}</p>}
            <div className="starters">
              {STARTERS.map((text) => (
                <button key={text} className="chip" onClick={() => void send(text)}>{text}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((message) => (
          <article key={message.id} className={`message ${message.role}`}>
            {message.role === "assistant" && <div className="avatar"><Logo size={28} /></div>}
            <div className="bubble">
              {message.role === "assistant" ? (
                message.content ? <Markdown>{message.content}</Markdown> : <span className="typing" aria-label="Compass is typing"><i /><i /><i /></span>
              ) : (
                <p>{message.content}</p>
              )}
              {message.role === "assistant" && !message.streaming && typeof message.id === "number" && (
                <Feedback value={message.feedback} onChange={(value) => void rate(message, value)} />
              )}
            </div>
          </article>
        ))}
        <div ref={endRef} />
      </div>

      {error && <p className="error banner" role="alert">{error}</p>}
      <form className="composer" onSubmit={(e) => { e.preventDefault(); void send(draft); }}>
        <textarea aria-label="Message Compass" placeholder="What's on your mind?" rows={Math.min(8, Math.max(1, draft.split("\n").length))}
          value={draft} maxLength={8000} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKeyDown} />
        <button className="send" aria-label="Send message" disabled={sending || !draft.trim()}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
        </button>
      </form>
      <p className="fineprint">Compass is an AI and can make mistakes. It isn't legal, medical or financial advice.</p>
    </section>
  );
}
