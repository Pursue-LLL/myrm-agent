import type { MCPServiceConfig } from '@/store/config/types';

const REMOTE_TRANSPORTS: ReadonlySet<MCPServiceConfig['type']> = new Set(['sse', 'streamable_http']);

const normalizeTransportToken = (transport: string): string => transport.trim().toLowerCase().replace(/-/g, '_');

export const canonicalizeMCPTransport = (
  transportLike: unknown,
  fallback?: {
    command?: unknown;
    url?: unknown;
  },
): MCPServiceConfig['type'] => {
  if (typeof transportLike === 'string' && transportLike.trim()) {
    const normalized = normalizeTransportToken(transportLike);
    if (normalized === 'streamable_http' || normalized === 'streamablehttp' || normalized === 'http') {
      return 'streamable_http';
    }
    if (normalized === 'sse') {
      return 'sse';
    }
    if (normalized === 'stdio') {
      return 'stdio';
    }
  }

  if (fallback?.command) {
    return 'stdio';
  }
  if (fallback?.url) {
    return 'sse';
  }
  return 'stdio';
};

export const normalizeMCPKeepaliveInterval = (
  type: MCPServiceConfig['type'],
  keepaliveInterval: unknown,
): number | null => {
  if (!REMOTE_TRANSPORTS.has(type)) {
    return null;
  }
  if (typeof keepaliveInterval !== 'number' || !Number.isFinite(keepaliveInterval) || keepaliveInterval < 5) {
    return null;
  }
  return keepaliveInterval;
};

export const normalizeMCPServiceConfig = (config: MCPServiceConfig): MCPServiceConfig => {
  const transportAlias = (config as MCPServiceConfig & { transport?: unknown }).transport;
  const type = canonicalizeMCPTransport(config.type ?? transportAlias, {
    command: config.command,
    url: config.url,
  });

  return {
    ...config,
    type,
    keepaliveInterval: normalizeMCPKeepaliveInterval(type, config.keepaliveInterval ?? null),
  };
};

export const normalizeMCPServiceConfigs = (configs: MCPServiceConfig[]): MCPServiceConfig[] =>
  configs.map((config) => normalizeMCPServiceConfig(config));
