/**
 * WebSocket Hook for Real-time Batch Optimization Progress
 *
 * Connects to the WebSocket endpoint and provides real-time updates for batch task progress.
 */

import { useEffect, useRef, useState } from 'react';
import { isRetryableWebSocketClose, FatalNetworkError } from '@/lib/utils/networkResilience';

export interface BatchProgressUpdate {
  batch_task_id: string;
  total: number;
  completed: number;
  failed: number;
  progress_percent: number;
  status?: string;
}

export interface UseBatchWebSocketOptions {
  batchId: string;
  onProgress?: (update: BatchProgressUpdate) => void;
  onComplete?: (update: BatchProgressUpdate) => void;
  onError?: (error: Error) => void;
}

export const useBatchWebSocket = (options: UseBatchWebSocketOptions) => {
  const { batchId, onProgress, onComplete, onError } = options;
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttempts = useRef(0);
  const shouldReconnectRef = useRef(true);

  useEffect(() => {
    if (!batchId) return;

    shouldReconnectRef.current = true;

    const connect = () => {
      try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/skill-optimization/batch/${batchId}`;

        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          setIsConnected(true);
          reconnectAttempts.current = 0;
          if (process.env.NODE_ENV === 'development') {
            console.debug(`[WebSocket] Connected to batch ${batchId}`);
          }
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);

            if (data.type === 'progress' && onProgress) {
              onProgress(data.data);
            } else if (data.type === 'completed' && onComplete) {
              onComplete(data.data);
              shouldReconnectRef.current = false;
              ws.close();
            }
          } catch (error) {
            if (process.env.NODE_ENV === 'development') {
              console.warn('[WebSocket] Failed to parse message:', error);
            }
            onError?.(error as Error);
          }
        };

        ws.onerror = (_error) => {
          if (process.env.NODE_ENV === 'development') {
            console.warn('[WebSocket] Connection failed (optional feature, backend may not be running)');
          }
          onError?.(new Error('WebSocket connection error'));
        };

        ws.onclose = (event) => {
          setIsConnected(false);
          if (process.env.NODE_ENV === 'development') {
            console.debug(`[WebSocket] Disconnected from batch ${batchId} with code ${event.code}`);
          }

          if (!isRetryableWebSocketClose(event.code)) {
            shouldReconnectRef.current = false;
            onError?.(new FatalNetworkError(`WebSocket closed with non-retryable code: ${event.code}`, event.code));
          }

          if (!shouldReconnectRef.current) {
            return;
          }

          if (reconnectAttempts.current < 5) {
            const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 10000);
            if (process.env.NODE_ENV === 'development') {
              console.debug(`[WebSocket] Reconnecting in ${delay}ms (attempt ${reconnectAttempts.current + 1}/5)`);
            }
            reconnectTimeoutRef.current = setTimeout(() => {
              reconnectAttempts.current++;
              connect();
            }, delay);
          }
        };
      } catch (error) {
        if (process.env.NODE_ENV === 'development') {
          console.warn('[WebSocket] Failed to create connection (backend may not be running)');
        }
        onError?.(error as Error);
      }
    };

    connect();

    return () => {
      shouldReconnectRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [batchId, onProgress, onComplete, onError]);

  return { isConnected };
};
