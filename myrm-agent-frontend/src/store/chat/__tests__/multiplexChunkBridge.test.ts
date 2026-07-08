import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  createMultiplexChunkBridge,
  createMultiplexReadableStream,
} from '../multiplexChunkBridge';

function dispatchMultiplexChunk(messageId: string, chunk: string): void {
  window.dispatchEvent(
    new CustomEvent(`multiplex_chunk_${messageId}`, { detail: chunk }),
  );
}

describe('multiplexChunkBridge', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('buffers chunks emitted before attachConsumer', () => {
    const controller = new AbortController();
    const bridge = createMultiplexChunkBridge('msg_early_gap', controller.signal);

    dispatchMultiplexChunk(
      'msg_early_gap',
      'data: {"type":"capability_gap","data":{"tool_id":"render_ui"}}\n\n',
    );

    const received: string[] = [];
    const buffered = bridge.attachConsumer((chunk) => {
      received.push(chunk);
    });

    expect(buffered).toHaveLength(1);
    expect(buffered[0]).toContain('capability_gap');
    expect(received).toHaveLength(0);

    dispatchMultiplexChunk('msg_early_gap', 'data: {"type":"message"}\n\n');
    expect(received).toHaveLength(1);

    bridge.dispose();
  });

  it('createMultiplexReadableStream replays buffered chunks in order', async () => {
    const controller = new AbortController();
    const stream = createMultiplexReadableStream('msg_stream_replay', controller.signal);

    dispatchMultiplexChunk(
      'msg_stream_replay',
      'data: {"type":"capability_gap","messageId":"m1"}\n\n',
    );

    const reader = stream.getReader();
    const decoder = new TextDecoder();

    const first = await reader.read();
    expect(decoder.decode(first.value)).toContain('capability_gap');

    dispatchMultiplexChunk(
      'msg_stream_replay',
      'data: {"type":"message_end","messageId":"m1"}\n\n',
    );
    const second = await reader.read();
    expect(decoder.decode(second.value)).toContain('message_end');

    await new Promise((resolve) => setTimeout(resolve, 60));
    const closed = await reader.read();
    expect(closed.done).toBe(true);
  });
});
