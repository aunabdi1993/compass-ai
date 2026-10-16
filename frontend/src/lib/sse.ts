/** Minimal server-sent-events parser for `event:` + single-line `data:` frames. */

export interface SSEFrame {
  event: string;
  data: string;
}

export class SSEParser {
  private buffer = "";

  /** Feed decoded text; returns every complete frame seen so far (frames end with a blank line). */
  feed(text: string): SSEFrame[] {
    this.buffer += text.replace(/\r\n/g, "\n");
    const frames: SSEFrame[] = [];
    let end: number;
    while ((end = this.buffer.indexOf("\n\n")) !== -1) {
      const block = this.buffer.slice(0, end);
      this.buffer = this.buffer.slice(end + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith(":")) continue; // comment / keep-alive
        const colon = line.indexOf(":");
        const field = colon === -1 ? line : line.slice(0, colon);
        const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
        if (field === "event") event = value;
        else if (field === "data") data.push(value);
      }
      if (data.length) frames.push({ event, data: data.join("\n") });
    }
    return frames;
  }
}

/** Read a streamed response body as frames. TextDecoder keeps multi-byte characters intact across chunks. */
export async function* readSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<SSEFrame> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  const parser = new SSEParser();
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      yield* parser.feed(decoder.decode(value, { stream: true }));
    }
    yield* parser.feed(decoder.decode());
  } finally {
    reader.releaseLock();
  }
}
