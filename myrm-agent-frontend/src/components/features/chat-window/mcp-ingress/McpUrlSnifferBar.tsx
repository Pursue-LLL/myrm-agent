/**
 * [INPUT]
 * - ./mcpIngressTypes::McpProbeResult
 * - ./useMcpIngressStore::useMcpIngressStore
 * - lucide-react::PlugZap, Sparkles, X, RefreshCw
 *
 * [OUTPUT]
 * - McpUrlSnifferBar: 输入框上方 MCP 链接实时智能嗅探浮条组件
 *
 * [POS]
 * 在输入框感知到用户贴入 MCP/Skill URL 时就地弹出轻量提示，引导快速握手预检。
 */

'use client';

import React, { useCallback } from 'react';
import { PlugZap, Sparkles, X, RefreshCw } from 'lucide-react';
import type { McpProbeResult } from './mcpIngressTypes';
import { useMcpIngressStore } from './useMcpIngressStore';

export interface McpUrlSnifferBarProps {
  onProbeComplete?: (probe: McpProbeResult) => void;
  className?: string;
}

export const McpUrlSnifferBar: React.FC<McpUrlSnifferBarProps> = ({
  onProbeComplete,
  className = '',
}) => {
  const detectedUrl = useMcpIngressStore((s) => s.detectedUrl);
  const dismissDetectedUrl = useMcpIngressStore((s) => s.dismissDetectedUrl);
  const probeUrl = useMcpIngressStore((s) => s.probeUrl);
  const mountStatus = useMcpIngressStore((s) => (detectedUrl ? s.mountStatuses[detectedUrl] : 'idle'));

  const isProbing = mountStatus === 'probing';

  const handleStartProbe = useCallback(async () => {
    if (!detectedUrl) {
      return;
    }
    const result = await probeUrl(detectedUrl);
    if (onProbeComplete) {
      onProbeComplete(result);
    }
  }, [detectedUrl, probeUrl, onProbeComplete]);

  if (!detectedUrl) {
    return null;
  }

  return (
    <aside
      aria-label="MCP 链接智能嗅探提示栏"
      className={`flex items-center justify-between gap-2 px-3 py-1.5 rounded-lg border border-primary/30 bg-primary/5 text-xs text-foreground shadow-xs animate-in fade-in slide-in-from-bottom-1 duration-150 ${className}`}
    >
      <div className="flex items-center gap-2 min-w-0">
        <PlugZap className="w-3.5 h-3.5 text-primary shrink-0" aria-hidden="true" />
        <span className="font-medium shrink-0">检测到服务链接：</span>
        <code className="text-[11px] text-primary font-mono truncate max-w-xs bg-primary/10 px-1 rounded">
          {detectedUrl}
        </code>
      </div>

      <div className="flex items-center gap-1.5 shrink-0">
        <button
          type="button"
          onClick={handleStartProbe}
          disabled={isProbing}
          className="flex items-center gap-1 px-2.5 py-1 rounded bg-primary text-primary-foreground text-[11px] font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors shadow-xs"
          aria-label="快速发起 MCP 握手预检"
        >
          {isProbing ? (
            <RefreshCw className="w-3 h-3 animate-spin" aria-hidden="true" />
          ) : (
            <Sparkles className="w-3 h-3" aria-hidden="true" />
          )}
          <span>{isProbing ? '正在探测...' : '即时预检'}</span>
        </button>

        <button
          type="button"
          onClick={dismissDetectedUrl}
          className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          aria-label="忽略嗅探提示"
        >
          <X className="w-3.5 h-3.5" aria-hidden="true" />
        </button>
      </div>
    </aside>
  );
};
