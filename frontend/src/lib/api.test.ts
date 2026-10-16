import { ApiError, createApi } from "./api";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function sseResponse(chunks: string[]) {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        chunks.forEach((c) => controller.enqueue(encoder.encode(c)));
        controller.close();
      },
    }),
    { status: 200, headers: { "Content-Type": "text/event-stream" } },
  );
}

describe("createApi", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  const onUnauthorized = vi.fn();
  const api = () => createApi(async () => "tok", onUnauthorized);

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    onUnauthorized.mockClear();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("sends the bearer token and JSON bodies", async () => {
    fetchMock.mockResolvedValue(json({ ok: true }));
    await api().acceptConsent(true);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/consent");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ Authorization: "Bearer tok", "Content-Type": "application/json" });
    expect(JSON.parse(init.body)).toEqual({ agree: true, training_opt_in: true });
  });

  it("sends uploads as multipart without forcing a content type", async () => {
    fetchMock.mockResolvedValue(json({ results: [], items: [], budget: {} }));
    await api().uploadDocuments([new File(["hi"], "a.txt")]);
    const init = fetchMock.mock.calls[0][1];
    expect(init.body).toBeInstanceOf(FormData);
    expect(init.headers["Content-Type"]).toBeUndefined();
  });

  it("surfaces the server's message and signs out on 401", async () => {
    fetchMock.mockResolvedValue(json({ detail: "Your session has expired. Please sign in again." }, 401));
    await expect(api().getProfile()).rejects.toMatchObject({ status: 401, message: expect.stringContaining("expired") });
    expect(onUnauthorized).toHaveBeenCalled();
  });

  it("falls back to a generic message when the error isn't JSON", async () => {
    fetchMock.mockResolvedValue(new Response("<html>bad gateway</html>", { status: 502 }));
    await expect(api().getProfile()).rejects.toMatchObject({ status: 502, message: expect.stringContaining("Something went wrong") });
  });

  it("turns network failures into a friendly error", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api().getProfile()).rejects.toBeInstanceOf(ApiError);
    await expect(api().getProfile()).rejects.toMatchObject({ status: 0, message: expect.stringContaining("connection") });
  });

  it("calls onUnauthorized without any request when there is no token", async () => {
    await expect(createApi(async () => null, onUnauthorized).bootstrap()).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(onUnauthorized).toHaveBeenCalled();
  });

  it("streams chat events split across chunks", async () => {
    fetchMock.mockResolvedValue(
      sseResponse([
        'event: meta\ndata: {"conversation_id":"c1","user_message_id":1}\n\nevent: del',
        'ta\ndata: {"text":"Hel"}\n\nevent: delta\ndata: {"text":"lo"}\n\n',
        'event: done\ndata: {"message_id":2}\n\n',
      ]),
    );
    const seen = [];
    for await (const event of api().chat("hi", null)) seen.push(event.event);
    expect(seen).toEqual(["meta", "delta", "delta", "done"]);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ message: "hi", conversation_id: null });
  });

  it("throws the server's reason when chat is refused before streaming (e.g. daily limit)", async () => {
    fetchMock.mockResolvedValue(json({ detail: "You've reached today's message limit. Come back tomorrow." }, 429));
    const run = async () => {
      for await (const _ of api().chat("hi", null)) void _;
    };
    await expect(run()).rejects.toMatchObject({ status: 429, message: expect.stringContaining("limit") });
  });

  it("encodes ids placed in URLs", async () => {
    fetchMock.mockResolvedValue(json({ items: [], budget: {} }));
    await api().deleteDocument("a/b c");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/documents/a%2Fb%20c");
  });
});
