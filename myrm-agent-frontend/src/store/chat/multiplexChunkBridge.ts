/**
 * [INPUT]
 * @/services/ConnectionManager::connectionManager (POS: workspace multiplex fan-out + pending buffer)
 * window CustomEvent multiplex_chunk_{messageId} (legacy fan-out)
 *
 * [OUTPUT]
 * createMultiplexChunkBridge: buffers early multiplex chunks until consumer attaches
 *
 * [POS]
 * Multiplexed agent-stream returns JSON before the pump may emit preflight SSE (e.g.
 * capability_gap). Register the listener before POST so early chunks are not dropped.
 */

import { connectionManager } from '@/services/ConnectionManager';

export type MultiplexChunkHandler = (chunk: string) => void;

export interface MultiplexChunkBridge {
  attachConsumer: (onChunk: MultiplexChunkHandler) => string[];
  dispose: () => void;
}

function isStreamTerminalChunk(chunk: string): boolean {
  return chunk.includes('"type":"message_end"') || chunk.includes('"type": "message_end"');
}

export function createMultiplexChunkBridge(
  requestMessageId: string,
  abortSignal: AbortSignal,
): MultiplexChunkBridge {
  const eventName = `multiplex_chunk_${requestMessageId}`;
  const pendingChunks: string[] = [];
  let onChunk: MultiplexChunkHandler | null = null;
  let unregisterManager: (() => void) | null = null;

  const deliver = (chunk: string) => {
    if (onChunk) {
      onChunk(chunk);
      return;
    }
    pendingChunks.push(chunk);
  };

  const listener = (event: Event) => {
    const chunk = (event as CustomEvent<string>).detail;
    if (!chunk) {
      return;
    }
    deliver(chunk);
  };

  const onAbort = () => {
    dispose();
  };

  const dispose = () => {
    window.removeEventListener(eventName, listener);
    abortSignal.removeEventListener('abort', onAbort);
    unregisterManager?.();
    unregisterManager = null;
    onChunk = null;
    pendingChunks.length = 0;
  };

  window.addEventListener(eventName, listener);
  unregisterManager = connectionManager.registerMultiplexHandler(requestMessageId, deliver);
  abortSignal.addEventListener('abort', onAbort);

  return {
    attachConsumer(handler: MultiplexChunkHandler) {
      onChunk = handler;
      return pendingChunks.splice(0);
    },
    dispose,
  };
}

export function createMultiplexReadableStream(
  requestMessageId: string,
  abortSignal: AbortSignal,
): ReadableStream<Uint8Array> {
  const bridge = createMultiplexChunkBridge(requestMessageId, abortSignal);
  const encoder = new TextEncoder();

  return new ReadableStream<Uint8Array>({
    start(controller) {
      const handleChunk = (chunk: string) => {
        controller.enqueue(encoder.encode(chunk));
        if (isStreamTerminalChunk(chunk)) {
          setTimeout(() => {
            bridge.dispose();
            try {
              controller.close();
            } catch {
              // already closed
            }
          }, 50);
        }
      };

      const buffered = bridge.attachConsumer(handleChunk);
      for (const chunk of buffered) {
        handleChunk(chunk);
      }
    },
    cancel() {
      bridge.dispose();
    },
  });
}
