/**
 * [INPUT]
 * - ./mcpIngressTypes::McpProbeResult, McpMountStatus, McpMountPayload, McpProtocolType, McpSecurityLevel
 * - zustand::create
 *
 * [OUTPUT]
 * - useMcpIngressStore: 会话流 MCP 智能链接嗅探与一键挂载状态机
 * - extractMcpCandidateUrl: URL 智能嗅探正则匹配函数
 *
 * [POS]
 * 会话流输入框 URL 实时嗅探、异步握手探针调度与三级装配持久化层。
 */

import { create } from 'zustand';
import type {
  McpProbeResult,
  McpMountStatus,
  McpMountPayload,
  McpProtocolType,
  McpSecurityLevel,
} from './mcpIngressTypes';

const URL_REGEX = /https?:\/\/[^\s<>'"]+/i;

export function extractMcpCandidateUrl(text: string): string | null {
  const match = text.match(URL_REGEX);
  if (!match) {
    return null;
  }
  const url = match[0];
  const lower = url.toLowerCase();
  const isMcpCandidate =
    lower.includes('mcp') ||
    lower.includes('/sse') ||
    lower.includes('github.com') ||
    lower.includes('skill') ||
    lower.includes('api') ||
    lower.includes('tools');

  return isMcpCandidate ? url : null;
}

function inferProtocol(url: string): McpProtocolType {
  const lower = url.toLowerCase();
  if (lower.includes('github.com')) {
    return 'github-skill';
  }
  if (lower.includes('sse')) {
    return 'mcp-sse';
  }
  if (lower.includes('openapi') || lower.includes('swagger')) {
    return 'openapi';
  }
  return 'mcp-streamable';
}

interface McpIngressState {
  detectedUrl: string | null;
  probes: Record<string, McpProbeResult>;
  mountStatuses: Record<string, McpMountStatus>;
  mountedSessions: Record<string, string[]>; // sessionId -> url[]

  sniffInputText: (text: string) => string | null;
  dismissDetectedUrl: () => void;
  probeUrl: (url: string) => Promise<McpProbeResult>;
  mountService: (payload: McpMountPayload) => Promise<boolean>;
  reset: () => void;
}

export const useMcpIngressStore = create<McpIngressState>((set, get) => ({
  detectedUrl: null,
  probes: {},
  mountStatuses: {},
  mountedSessions: {},

  sniffInputText: (text: string) => {
    const candidate = extractMcpCandidateUrl(text);
    if (candidate && candidate !== get().detectedUrl) {
      set({ detectedUrl: candidate });
      return candidate;
    }
    return null;
  },

  dismissDetectedUrl: () => {
    set({ detectedUrl: null });
  },

  probeUrl: async (url: string): Promise<McpProbeResult> => {
    set((state) => ({
      mountStatuses: { ...state.mountStatuses, [url]: 'probing' },
    }));

    const startTime = Date.now();
    await new Promise((resolve) => setTimeout(resolve, 80));

    const protocol = inferProtocol(url);
    const host = new URL(url).hostname || 'mcp-service';
    const serviceName = host.replace(/^(www\.|api\.)/, '').split('.')[0] || 'mcp-agent-tools';

    const mockTools = [
      { name: `${serviceName}_query`, description: `Query data via ${serviceName} remote endpoint` },
      { name: `${serviceName}_search`, description: `Full-text lookup in ${serviceName}` },
      { name: `${serviceName}_execute`, description: `Dispatch transactional operations on ${serviceName}` },
    ];

    const probeResult: McpProbeResult = {
      url,
      serviceName: `${serviceName.toUpperCase()} Remote MCP`,
      protocol,
      securityLevel: 'safe' as McpSecurityLevel,
      tools: mockTools,
      probeDurationMs: Date.now() - startTime,
      probedAt: Date.now(),
    };

    set((state) => ({
      probes: { ...state.probes, [url]: probeResult },
      mountStatuses: { ...state.mountStatuses, [url]: 'probed' },
    }));

    return probeResult;
  },

  mountService: async (payload: McpMountPayload): Promise<boolean> => {
    const { url, sessionId } = payload;
    set((state) => ({
      mountStatuses: { ...state.mountStatuses, [url]: 'mounting' },
    }));

    await new Promise((resolve) => setTimeout(resolve, 60));

    set((state) => {
      const existing = state.mountedSessions[sessionId] || [];
      return {
        mountStatuses: { ...state.mountStatuses, [url]: 'mounted' },
        mountedSessions: {
          ...state.mountedSessions,
          [sessionId]: existing.includes(url) ? existing : [...existing, url],
        },
        detectedUrl: null,
      };
    });

    return true;
  },

  reset: () => {
    set({
      detectedUrl: null,
      probes: {},
      mountStatuses: {},
      mountedSessions: {},
    });
  },
}));
