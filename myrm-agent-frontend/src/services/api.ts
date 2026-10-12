/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: centralized frontend API client)
 *
 * [OUTPUT]
 * apiClient: Lightweight RESTful client facade wrapping apiRequest for memory services.
 *
 * [POS]
 * Client adapter providing ergonomic .get/.post/.put/.delete interfaces.
 * Strict typing: No `any` types allowed. Single file < 120 lines.
 */

import { apiRequest } from '@/lib/api';

export interface ApiRequestOptions {
  params?: Record<string, string | number | boolean | undefined | null>;
  silent?: boolean;
  timeout?: number;
}

function buildUrlWithParams(endpoint: string, params?: ApiRequestOptions['params']): string {
  if (!params) return endpoint;
  const searchParams = new URLSearchParams();
  for (const [key, val] of Object.entries(params)) {
    if (val !== undefined && val !== null) {
      searchParams.append(key, String(val));
    }
  }
  const query = searchParams.toString();
  if (!query) return endpoint;
  return endpoint.includes('?') ? `${endpoint}&${query}` : `${endpoint}?${query}`;
}

export const apiClient = {
  async get<T>(endpoint: string, options?: ApiRequestOptions): Promise<T> {
    const url = buildUrlWithParams(endpoint, options?.params);
    return apiRequest<T>(url, {
      method: 'GET',
      silent: options?.silent,
      timeout: options?.timeout,
    });
  },

  async post<T>(endpoint: string, body?: unknown, options?: ApiRequestOptions): Promise<T> {
    const url = buildUrlWithParams(endpoint, options?.params);
    return apiRequest<T>(url, {
      method: 'POST',
      body: body !== undefined ? JSON.stringify(body) : undefined,
      silent: options?.silent,
      timeout: options?.timeout,
    });
  },

  async put<T>(endpoint: string, body?: unknown, options?: ApiRequestOptions): Promise<T> {
    const url = buildUrlWithParams(endpoint, options?.params);
    return apiRequest<T>(url, {
      method: 'PUT',
      body: body !== undefined ? JSON.stringify(body) : undefined,
      silent: options?.silent,
      timeout: options?.timeout,
    });
  },

  async delete<T>(endpoint: string, options?: ApiRequestOptions): Promise<T> {
    const url = buildUrlWithParams(endpoint, options?.params);
    return apiRequest<T>(url, {
      method: 'DELETE',
      silent: options?.silent,
      timeout: options?.timeout,
    });
  },
};
