/**
 * [INPUT]
 * @/services/memory/transcriptProjection::bootstrapSessionProjection, getSessionProjectedMessages, DTOs
 * React::useState, useCallback
 *
 * [OUTPUT]
 * useTranscriptProjection: React hook managing cold-start projection bootstrapping and message loading.
 *
 * [POS]
 * Hook module for Item 150 SqliteTranscriptProjectionSuite.
 * Strict typing applied: 0 any types allowed.
 */

import { useCallback, useState } from 'react';
import {
  BootstrapSessionRequestDTO,
  BootstrapSessionResponseDTO,
  SessionMessageDTO,
  bootstrapSessionProjection,
  getSessionProjectedMessages,
} from '@/services/memory/transcriptProjection';

export interface UseTranscriptProjectionState {
  isBootstrapping: boolean;
  isLoadingMessages: boolean;
  lastResult: BootstrapSessionResponseDTO | null;
  messages: SessionMessageDTO[];
  error: string | null;
}

export interface UseTranscriptProjectionReturn extends UseTranscriptProjectionState {
  bootstrap: (request: BootstrapSessionRequestDTO) => Promise<BootstrapSessionResponseDTO | null>;
  loadMessages: (sessionId: string) => Promise<SessionMessageDTO[]>;
  reset: () => void;
}

export function useTranscriptProjection(): UseTranscriptProjectionReturn {
  const [isBootstrapping, setIsBootstrapping] = useState<boolean>(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState<boolean>(false);
  const [lastResult, setLastResult] = useState<BootstrapSessionResponseDTO | null>(null);
  const [messages, setMessages] = useState<SessionMessageDTO[]>([]);
  const [error, setError] = useState<string | null>(null);

  const bootstrap = useCallback(
    async (
      request: BootstrapSessionRequestDTO
    ): Promise<BootstrapSessionResponseDTO | null> => {
      setIsBootstrapping(true);
      setError(null);
      try {
        const result = await bootstrapSessionProjection(request);
        setLastResult(result);
        // Automatically refresh projected messages on success
        const loaded = await getSessionProjectedMessages(request.session_id);
        setMessages(loaded);
        return result;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to bootstrap transcript projection';
        setError(msg);
        return null;
      } finally {
        setIsBootstrapping(false);
      }
    },
    []
  );

  const loadMessages = useCallback(async (sessionId: string): Promise<SessionMessageDTO[]> => {
    setIsLoadingMessages(true);
    setError(null);
    try {
      const loaded = await getSessionProjectedMessages(sessionId);
      setMessages(loaded);
      return loaded;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load projected messages';
      setError(msg);
      return [];
    } finally {
      setIsLoadingMessages(false);
    }
  }, []);

  const reset = useCallback(() => {
    setIsBootstrapping(false);
    setIsLoadingMessages(false);
    setLastResult(null);
    setMessages([]);
    setError(null);
  }, []);

  return {
    isBootstrapping,
    isLoadingMessages,
    lastResult,
    messages,
    error,
    bootstrap,
    loadMessages,
    reset,
  };
}
