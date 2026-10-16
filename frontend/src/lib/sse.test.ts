import { readSSE, SSEParser } from "./sse";

describe("SSEParser", () => {
  it("parses complete frames and ignores comments and keep-alives", () => {
    const frames = new SSEParser().feed(': ping\n\nevent: delta\ndata: {"text":"Hi"}\n\nevent: done\ndata: {"message_id":3}\n\n');
    expect(frames).toEqual([
      { event: "delta", data: '{"text":"Hi"}' },
      { event: "done", data: '{"message_id":3}' },
    ]);
  });

  it("waits for a frame to finish across chunk boundaries", () => {
    const parser = new SSEParser();
    expect(parser.feed('event: delta\nda')).toEqual([]);
    expect(parser.feed('ta: {"text":"x"}\n')).toEqual([]);
    expect(parser.feed("\n")).toEqual([{ event: "delta", data: '{"text":"x"}' }]);
  });

  it("handles CRLF line endings and defaults the event name", () => {
    expect(new SSEParser().feed("data: hello\r\n\r\n")).toEqual([{ event: "message", data: "hello" }]);
  });
});

describe("readSSE", () => {
  it("keeps multi-byte characters intact when a chunk splits them", async () => {
    const bytes = new TextEncoder().encode('event: delta\ndata: {"text":"Café 👍"}\n\n');
    const split = bytes.indexOf(0xf0) + 2; // in the middle of the emoji
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, split));
        controller.enqueue(bytes.slice(split));
        controller.close();
      },
    });
    const frames = [];
    for await (const frame of readSSE(body)) frames.push(frame);
    expect(JSON.parse(frames[0].data).text).toBe("Café 👍");
  });
});
