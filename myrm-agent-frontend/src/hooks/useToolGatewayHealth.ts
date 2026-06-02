import { useState, useCallback, useRef, useEffect } from 'react';
import useConfigStore from '@/store/useConfigStore';
import { apiRequest } from '@/lib/api';

export interface ProviderHealth {
  provider: string;
  healthy: boolean;
}

export interface GatewayHealthResponse {
  status?: string;
  message?: string;
  wu_balance?: number;
  providers?: Record<string, ProviderHealth>;
  overall_healthy?: boolean;
}

export function useToolGatewayHealth() {
  const { gateway_token } = useConfigStore();
  const [data, setData] = useState<GatewayHealthResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const checkHealth = useCallback(async () => {
    if (!gateway_token) {
      setData({ status: 'error', message: 'No Gateway PAT configured' });
      return;
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const timeoutId = setTimeout(() => {
      abortController.abort();
    }, 8000);

    setIsLoading(true);
    setError(null);
    try {
      // Calls Server proxy endpoint securely via POST
      const response = await apiRequest<GatewayHealthResponse>('/system/gateway/health', {
        method: 'POST',
        body: JSON.stringify({ gateway_token }),
        signal: abortController.signal,
        silent: true, // We handle errors manually in the UI
      });
      setData(response);
    } catch (err: any) {
      if (err.name === 'AbortError') {
        setData({ status: 'error', message: 'Gateway connection timed out (8s)' });
      } else {
        setData({ status: 'error', message: err.message || 'Failed to check gateway health' });
      }
    } finally {
      clearTimeout(timeoutId);
      setIsLoading(false);
    }
  }, [gateway_token]);

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  return {
    data,
    isLoading,
    error,
    checkHealth,
  };
}
