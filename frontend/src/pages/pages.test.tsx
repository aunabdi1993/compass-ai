import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthContext } from "../lib/auth";
import { ApiError } from "../lib/api";
import type { Bootstrap } from "../lib/types";
import { BOOT, events, fakeApi, fakeAuth, renderPage } from "../test/utils";
import { render } from "@testing-library/react";
import { Chat } from "./Chat";
import { Consent } from "./Consent";
import { Documents, checkFile } from "./Documents";
import { Login } from "./Login";
import { Privacy } from "./Privacy";
import { Profile } from "./Profile";

describe("Login", () => {
  it("asks for the emailed code, then signs in", async () => {
    const auth = fakeAuth({ status: "signedOut" });
    render(<AuthContext.Provider value={auth}><Login /></AuthContext.Provider>);
    await userEvent.type(screen.getByLabelText("Email address"), "aun@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Email me a code" }));
    expect(auth.sendCode).toHaveBeenCalledWith("aun@example.com");
    expect(await screen.findByText(/We sent a code to/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Code from the email"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(auth.verifyCode).toHaveBeenCalledWith("aun@example.com", "123456");
  });

  it("shows a friendly error for a wrong code and lets the user keep trying", async () => {
    const auth = fakeAuth({ status: "signedOut", verifyCode: vi.fn(async () => { throw new Error("That code didn't work."); }) });
    render(<AuthContext.Provider value={auth}><Login /></AuthContext.Provider>);
    await userEvent.type(screen.getByLabelText("Email address"), "a@b.co");
    await userEvent.click(screen.getByRole("button", { name: "Email me a code" }));
    await userEvent.type(await screen.findByLabelText("Code from the email"), "000000");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("didn't work");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
  });

  it("shows the note left behind after deleting data", () => {
    sessionStorage.setItem("compass-notice", "Your data has been deleted.");
    render(<AuthContext.Provider value={fakeAuth({ status: "signedOut" })}><Login /></AuthContext.Provider>);
    expect(screen.getByRole("status")).toHaveTextContent("Your data has been deleted.");
    expect(sessionStorage.getItem("compass-notice")).toBeNull();
  });
});

describe("Consent", () => {
  const unconsented: Bootstrap = { ...BOOT, consent: { ...BOOT.consent, accepted: false } };

  it("won't continue until the first box is ticked", async () => {
    const api = fakeApi({ bootstrap: vi.fn(async () => unconsented) });
    renderPage(<Consent />, { api });
    await userEvent.click(await screen.findByRole("button", { name: "Continue" }));
    expect(screen.getByRole("alert")).toHaveTextContent("tick the first box");
    expect(api.acceptConsent).not.toHaveBeenCalled();
  });

  it("records the optional training choice separately, off by default", async () => {
    const api = fakeApi({ bootstrap: vi.fn(async () => unconsented) });
    renderPage(<Consent />, { api });
    const [agree, training] = await screen.findAllByRole("checkbox");
    expect(training).not.toBeChecked();
    await userEvent.click(agree);
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(api.acceptConsent).toHaveBeenCalledWith(false));
  });

  it("passes the training opt-in when the user ticks it", async () => {
    const api = fakeApi({ bootstrap: vi.fn(async () => unconsented) });
    renderPage(<Consent />, { api });
    const [agree, training] = await screen.findAllByRole("checkbox");
    await userEvent.click(agree);
    await userEvent.click(training);
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(api.acceptConsent).toHaveBeenCalledWith(true));
  });
});

describe("Chat", () => {
  const send = async (text: string) => {
    await userEvent.type(await screen.findByLabelText("Message Compass"), text);
    await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  };

  it("streams the reply, renders markdown, and offers thumbs once it is saved", async () => {
    const api = fakeApi({
      chat: vi.fn(() => events(
        { event: "meta", data: { conversation_id: "c1", user_message_id: 1 } },
        { event: "delta", data: { text: "Two **questions**:\n\n" } },
        { event: "delta", data: { text: "1. What does strategic mean?" } },
        { event: "done", data: { message_id: 2 } },
      )),
    });
    renderPage(<Chat />, { api });
    await send("I need to be more strategic");
    expect(await screen.findByText("questions")).toContainHTML("strong");
    expect(screen.getByText("What does strategic mean?")).toBeInTheDocument();
    expect(screen.getByText("I need to be more strategic")).toBeInTheDocument();
    expect(api.chat).toHaveBeenCalledWith("I need to be more strategic", null, expect.any(AbortSignal));

    await userEvent.click(await screen.findByRole("button", { name: "Good reply" }));
    expect(api.setFeedback).toHaveBeenCalledWith(2, 1);
    expect(screen.getByRole("button", { name: "Good reply" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "Good reply" })); // click again clears it
    expect(api.setFeedback).toHaveBeenLastCalledWith(2, null);
  });

  it("sends on Enter but not on Shift+Enter, and never an empty message", async () => {
    const api = fakeApi({ chat: vi.fn(() => events({ event: "done", data: { message_id: 9 } })) });
    renderPage(<Chat />, { api });
    const box = await screen.findByLabelText("Message Compass");
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    await userEvent.type(box, "line one{Shift>}{Enter}{/Shift}line two");
    expect(api.chat).not.toHaveBeenCalled();
    expect(box).toHaveValue("line one\nline two");
    await userEvent.type(box, "{Enter}");
    expect(api.chat).toHaveBeenCalledWith("line one\nline two", null, expect.any(AbortSignal));
  });

  it("shows an error and keeps the user's message when the model fails", async () => {
    const api = fakeApi({
      chat: vi.fn(() => events(
        { event: "meta", data: { conversation_id: "c1", user_message_id: 1 } },
        { event: "error", data: { message: "Compass is busy right now. Please try again in a minute." } },
      )),
    });
    renderPage(<Chat />, { api });
    await send("hello");
    expect(await screen.findByRole("alert")).toHaveTextContent("busy right now");
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.queryByLabelText("Compass is typing")).not.toBeInTheDocument();
  });

  it("shows the daily-limit message from the server", async () => {
    const api = fakeApi({
      chat: vi.fn(() => { throw new ApiError(429, "You've reached today's message limit. Come back tomorrow."); }),
    });
    renderPage(<Chat />, { api });
    await send("hello");
    expect(await screen.findByRole("alert")).toHaveTextContent("message limit");
  });

  it("flags a reply that was cut off mid-stream", async () => {
    const api = fakeApi({
      chat: vi.fn(() => events({ event: "meta", data: { conversation_id: "c1", user_message_id: 1 } })),
    });
    renderPage(<Chat />, { api });
    await send("hello");
    expect(await screen.findByRole("alert")).toHaveTextContent("cut off");
  });

  it("opens a past conversation with its ratings and continues it", async () => {
    const api = fakeApi({
      conversation: vi.fn(async () => [
        { id: 1, role: "user", content: "Old question" },
        { id: 2, role: "assistant", content: "Old answer", feedback: -1 },
      ]),
      chat: vi.fn(() => events({ event: "meta", data: { conversation_id: "c7", user_message_id: 3 } }, { event: "done", data: { message_id: 4 } })),
    });
    renderPage(<Chat />, { api, route: "/c/c7", path: "/c/:conversationId" });
    expect(await screen.findByText("Old answer")).toBeInTheDocument();
    expect(api.conversation).toHaveBeenCalledWith("c7");
    expect(screen.getByRole("button", { name: "Bad reply" })).toHaveAttribute("aria-pressed", "true");
    await send("Follow-up");
    expect(api.chat).toHaveBeenCalledWith("Follow-up", "c7", expect.any(AbortSignal));
  });

  it("ends a session and tells the user a note was saved", async () => {
    const api = fakeApi({
      chat: vi.fn(() => events({ event: "meta", data: { conversation_id: "c1", user_message_id: 1 } }, { event: "done", data: { message_id: 2 } })),
    });
    // The app's real routes: "/" and "/c/:id". The URL changes mid-conversation, and the chat must survive that.
    renderPage(<Chat />, { api, route: "/", paths: ["/", "/c/:conversationId"] });
    expect(await screen.findByRole("button", { name: "End session" })).toBeDisabled(); // nothing to end yet
    await send("hello");
    await waitFor(() => expect(screen.getByRole("button", { name: "End session" })).toBeEnabled());
    expect(screen.getByText("hello")).toBeInTheDocument(); // still on screen after the URL became /c/c1
    expect(api.conversation).not.toHaveBeenCalled(); // and not reloaded from the server
    await userEvent.click(screen.getByRole("button", { name: "End session" }));
    expect(api.endConversation).toHaveBeenCalledWith("c1");
    expect(await screen.findByText(/Saved a note/)).toBeInTheDocument();
  });

  it("offers starter prompts that send straight away", async () => {
    const api = fakeApi({ chat: vi.fn(() => events({ event: "done", data: { message_id: 2 } })) });
    renderPage(<Chat />, { api });
    await userEvent.click(await screen.findByRole("button", { name: "Help me prepare for my annual review" }));
    expect(api.chat).toHaveBeenCalledWith("Help me prepare for my annual review", null, expect.any(AbortSignal));
  });
});

describe("Documents", () => {
  const docsBoot = (items: Bootstrap["documents"]): Bootstrap => ({ ...BOOT, documents: items });
  const oneDoc = {
    items: [{ id: "d1", name: "cv.pdf", char_count: 1200, truncated: false, enabled: true, created_at: "2026-10-01" }],
    budget: { used: 1200, limit: 80000, left_out: [], clipped: [] },
  };

  it("validates file type and size in the browser before uploading", () => {
    expect(checkFile(new File(["x"], "notes.md"))).toBeNull();
    expect(checkFile(new File(["x"], "virus.exe"))).toMatch(/PDF, Word/);
    expect(checkFile(new File(["x"], "noext"))).toMatch(/PDF, Word/);
    const big = new File(["x"], "big.pdf");
    Object.defineProperty(big, "size", { value: 11 * 1024 * 1024 });
    expect(checkFile(big)).toMatch(/10 MB/);
  });

  it("uploads, reports per-file results, and updates the list and budget", async () => {
    const api = fakeApi({
      uploadDocuments: vi.fn(async () => ({
        results: [{ name: "cv.pdf", ok: true }, { name: "empty.txt", ok: false, error: "I couldn't find any text in that file." }],
        ...oneDoc,
      })),
    });
    renderPage(<Documents />, { api });
    const input = await screen.findByLabelText("Choose files to upload");
    await userEvent.upload(input, [new File(["a"], "cv.pdf"), new File(["b"], "empty.txt")]);
    const results = await screen.findByRole("list", { name: "Upload results" });
    expect(within(results).getByText("Added cv.pdf")).toBeInTheDocument();
    expect(within(results).getByText(/empty.txt: I couldn't find any text/)).toBeInTheDocument();
    expect(screen.getByText(/Context in use: 1,200 of 80,000/)).toBeInTheDocument();
    expect(screen.getByLabelText("Use cv.pdf in conversations")).toBeInTheDocument();
  });

  it("doesn't send files the browser can already see are invalid", async () => {
    const api = fakeApi();
    renderPage(<Documents />, { api });
    await userEvent.upload(await screen.findByLabelText("Choose files to upload"), new File(["x"], "virus.exe"), { applyAccept: false });
    expect(await screen.findByText(/virus.exe: Please upload a PDF/)).toBeInTheDocument();
    expect(api.uploadDocuments).not.toHaveBeenCalled();
  });

  it("switches a document off and removes it", async () => {
    const off = { ...oneDoc, items: [{ ...oneDoc.items[0], enabled: false }] };
    const api = fakeApi({
      bootstrap: vi.fn(async () => docsBoot(oneDoc)),
      setDocumentEnabled: vi.fn(async () => off),
      deleteDocument: vi.fn(async () => ({ items: [], budget: oneDoc.budget })),
    });
    renderPage(<Documents />, { api });
    const toggle = await screen.findByRole("switch", { name: "Use cv.pdf in conversations" });
    expect(toggle).toHaveAttribute("aria-checked", "true");
    await userEvent.click(toggle);
    expect(api.setDocumentEnabled).toHaveBeenCalledWith("d1", false);
    await waitFor(() => expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "false"));
    await userEvent.click(screen.getByRole("button", { name: "Remove cv.pdf" }));
    expect(api.deleteDocument).toHaveBeenCalledWith("d1");
    expect(await screen.findByText("No documents yet.")).toBeInTheDocument();
  });

  it("warns when documents don't fit in the context", async () => {
    const tight = { ...oneDoc, budget: { used: 80000, limit: 80000, left_out: ["old.docx"], clipped: [] } };
    renderPage(<Documents />, { api: fakeApi({ bootstrap: vi.fn(async () => docsBoot(tight)) }) });
    expect(await screen.findByText(/didn't fit.*old.docx/)).toBeInTheDocument();
  });
});

describe("Profile", () => {
  it("saves what the user typed", async () => {
    const api = fakeApi();
    renderPage(<Profile />, { api });
    const role = await screen.findByLabelText("Current role");
    expect(role).toHaveValue("Analyst");
    await userEvent.clear(role);
    await userEvent.type(role, "Senior analyst");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(api.saveProfile).toHaveBeenCalledWith(expect.objectContaining({ role: "Senior analyst" }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });
});

describe("Privacy", () => {
  it("changes the training opt-in", async () => {
    const api = fakeApi();
    renderPage(<Privacy />, { api });
    const toggle = await screen.findByRole("switch", { name: /improving Compass/ });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    await userEvent.click(toggle);
    expect(api.setTrainingOptIn).toHaveBeenCalledWith(true);
    await waitFor(() => expect(toggle).toHaveAttribute("aria-checked", "true"));
  });

  it("only deletes after typing DELETE, then signs out", async () => {
    const api = fakeApi();
    const { auth } = renderPage(<Privacy />, { api });
    const button = await screen.findByRole("button", { name: "Delete everything" });
    await userEvent.click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent("Type DELETE");
    await userEvent.type(screen.getByLabelText("Type DELETE to confirm"), "delete");
    await userEvent.click(button);
    expect(api.deleteMyData).not.toHaveBeenCalled();
    await userEvent.clear(screen.getByLabelText("Type DELETE to confirm"));
    await userEvent.type(screen.getByLabelText("Type DELETE to confirm"), "DELETE");
    await userEvent.click(button);
    await waitFor(() => expect(auth.signOut).toHaveBeenCalled());
    expect(api.deleteMyData).toHaveBeenCalled();
    expect(sessionStorage.getItem("compass-notice")).toMatch(/deleted/);
  });

  it("doesn't sign out when deletion fails", async () => {
    const api = fakeApi({ deleteMyData: vi.fn(async () => { throw new ApiError(500, "Something went wrong."); }) });
    const { auth } = renderPage(<Privacy />, { api });
    await userEvent.type(await screen.findByLabelText("Type DELETE to confirm"), "DELETE");
    await userEvent.click(screen.getByRole("button", { name: "Delete everything" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Nothing was changed");
    expect(auth.signOut).not.toHaveBeenCalled();
  });
});
