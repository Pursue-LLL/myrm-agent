/**
 * @vitest-environment node
 */
import { describe, expect, it, vi } from 'vitest';
import { readSSE } from '../../../../../myrm-agent-extension/src/sidepanel/sse.js';

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

describe('readSSE', () => {
  it('parses events split across chunk boundaries', async () => {
    const events: unknown[] = [];

    await readSSE(streamOf(['data: {"type":"mess', 'age","data":"hi"}\n', 'data: {"type":"message_end"}\n']), (e) =>
      events.push(e),
    );

    expect(events).toEqual([{ type: 'message', data: 'hi' }, { type: 'message_end' }]);
  });

  it('stops at [DONE] and ignores what follows', async () => {
    const events: unknown[] = [];

    await readSSE(streamOf(['data: {"type":"a"}\ndata: [DONE]\ndata: {"type":"b"}\n']), (e) => events.push(e));

    expect(events).toEqual([{ type: 'a' }]);
  });

  it('skips non-data lines and malformed json without ending the stream', async () => {
    const events: unknown[] = [];

    await readSSE(streamOf([': keep-alive\nevent: x\ndata: {oops\ndata: {"type":"ok"}\n']), (e) => events.push(e));

    expect(events).toEqual([{ type: 'ok' }]);
  });

  it('logs a throwing handler and keeps reading', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    const seen: string[] = [];

    await readSSE(streamOf(['data: {"type":"bad"}\ndata: {"type":"good"}\n']), (e) => {
      if (e.type === 'bad') {
        throw new Error('boom');
      }
      seen.push(e.type);
    });

    expect(seen).toEqual(['good']);
    expect(error).toHaveBeenCalledTimes(1);
    error.mockRestore();
  });
});
