import { afterEach, describe, expect, it, vi } from 'vitest';

import { connectionManager } from '@/services/ConnectionManager';
import {
  createMultiplexChunkBridge,
  createMultiplexReadableStream,
} from '../multiplexChunkBridge';

const handlerBuckets = new Map<string, Set<(chunk: string) => void>>();

function emitMultiplexChunk(messageId: string, chunk: string): void {
  for (const handler of handlerBuckets.get(messageId) ?? []) {
    handler(chunk);
  }
}

describe('multiplexChunkBridge', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    handlerBuckets.clear();
  });

  it('buffers chunks emitted before attachConsumer', () => {
    vi.spyOn(connectionManager, 'registerMultiplexHandler').mockImplementation(
      (messageId, handler) => {
        const bucket = handlerBuckets.get(messageId) ?? new Set();
        bucket.add(handler);
        handlerBuckets.set(messageId, bucket);
        return () => {
          bucket.delete(handler);
        };
      },
    );

    const controller = new AbortController();
    const bridge = createMultiplexChunkBridge('msg_early_gap', controller.signal);

    emitMultiplexChunk(
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

    emitMultiplexChunk('msg_early_gap', 'data: {"type":"message"}\n\n');
    expect(received).toHaveLength(1);

    bridge.dispose();
  });

  it('createMultiplexReadableStream replays buffered chunks in order', async () => {
    vi.spyOn(connectionManager, 'registerMultiplexHandler').mockImplementation(
      (messageId, handler) => {
        const bucket = handlerBuckets.get(messageId) ?? new Set();
        bucket.add(handler);
        handlerBuckets.set(messageId, bucket);
        return () => {
          bucket.delete(handler);
        };
      },
    );

    const controller = new AbortController();
    const stream = createMultiplexReadableStream('msg_stream_replay', controller.signal);

    emitMultiplexChunk(
      'msg_stream_replay',
      'data: {"type":"capability_gap","messageId":"m1"}\n\n',
    );

    const reader = stream.getReader();
    const decoder = new TextDecoder();

    const first = await reader.read();
    expect(decoder.decode(first.value)).toContain('capability_gap');

    emitMultiplexChunk(
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
