'use client';

/**
 * [INPUT]
 * @/services/ollamaChatModel::fetchOllamaChatModel (POS: the server's pick among the installed Ollama models)
 * @/store/config/enableProviderWithModel::enableProviderWithModel (POS: the shared enable-and-fill-the-default rule)
 * @/lib/deploy-mode::isLocalMode (POS: hosted workspaces have no Ollama of their own)
 *
 * [OUTPUT]
 * useOllamaQuickConnect: the Ollama model the user can connect with one click, and the action that connects it
 * OllamaQuickConnect: the shape the hook returns
 *
 * [POS]
 * Lets the chat banner offer an Ollama the user already runs. It asks once while the banner is showing, offers
 * nothing when the answer is empty or the request fails, and connecting writes the provider state exactly like a
 * subscription login does.
 */

import { useCallback, useEffect, useState } from 'react';
import { isLocalMode } from '@/lib/deploy-mode';
import { fetchOllamaChatModel, type OllamaChatModel } from '@/services/ollamaChatModel';
import { enableProviderWithModel } from '@/store/config/enableProviderWithModel';

const OLLAMA_PROVIDER_ID = 'ollama';

export interface OllamaQuickConnect {
  model: string;
  connect: () => void;
}

/** `active` is whether the banner is showing; the server is only asked then, and only in the local deploy modes. */
export function useOllamaQuickConnect(active: boolean): OllamaQuickConnect | null {
  const [found, setFound] = useState<OllamaChatModel | null>(null);

  useEffect(() => {
    if (!active || !isLocalMode()) {
      return;
    }
    let cancelled = false;
    void fetchOllamaChatModel().then((result) => {
      if (!cancelled) {
        setFound(result);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [active]);

  const connect = useCallback(() => {
    if (found) {
      enableProviderWithModel(OLLAMA_PROVIDER_ID, found.model, { apiUrl: found.baseUrl });
    }
  }, [found]);

  return active && found ? { model: found.model, connect } : null;
}
