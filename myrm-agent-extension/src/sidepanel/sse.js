/**
 * Minimal reader for the agent SSE stream (`data: <json>` lines, `[DONE]` terminator).
 *
 * [INPUT]
 * - Response body (ReadableStream) of POST /api/v1/agents/agent-stream
 *
 * [OUTPUT]
 * - readSSE: calls `onEvent` with each parsed event until the stream ends or `[DONE]` arrives
 *
 * [POS] Transport parsing of the Side Panel chat; event meaning lives in sidepanel.js.
 */

/**
 * A malformed line is skipped, and a throwing handler is logged: neither ends the stream.
 * @param {ReadableStream<Uint8Array>} body
 * @param {(event: { type: string }) => void} onEvent
 * @returns {Promise<void>}
 */
export async function readSSE(body, onEvent) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) return;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6).trim();
      if (data === "[DONE]") return;

      let event;
      try {
        event = JSON.parse(data);
      } catch {
        continue;
      }
      try {
        onEvent(event);
      } catch (err) {
        console.error("[SidePanel] SSE event handler failed:", err);
      }
    }
  }
}
