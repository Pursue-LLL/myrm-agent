/**
 * Ollama chat-model client.
 *
 * [INPUT] lib/api::apiRequest (POS: authenticated HTTP client)
 * [OUTPUT] fetchOllamaChatModel, OllamaChatModel
 * [POS] Asks the server which model of the Ollama it can reach is able to chat and call tools, for the chat banner's one-click connect.
 */

import { apiRequest } from '@/lib/api';

export interface OllamaChatModel {
  model: string;
  /** The address the server found the model at; the provider must use the same one to reach it. */
  baseUrl: string;
}

interface OllamaChatModelResponse {
  model?: string | null;
  base_url?: string;
}

// The server may check a few models one after another, so the wait is longer than an ordinary request needs.
const REQUEST_TIMEOUT_MS = 15_000;

/**
 * Resolves to null when Ollama is not running, has no model able to chat and call tools, or the probe failed. It never
 * raises an error toast: the banner it serves is a convenience and must stay quiet when there is nothing to offer.
 */
export async function fetchOllamaChatModel(): Promise<OllamaChatModel | null> {
  try {
    const data = await apiRequest<OllamaChatModelResponse>('/integrations/hardware/ollama/chat-model', {
      method: 'GET',
      silent: true,
      timeout: REQUEST_TIMEOUT_MS,
    });
    return data.model && data.base_url ? { model: data.model, baseUrl: data.base_url } : null;
  } catch {
    return null;
  }
}
