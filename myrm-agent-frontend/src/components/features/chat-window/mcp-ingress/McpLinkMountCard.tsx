/**
 * [INPUT]
 * - ./mcpIngressTypes::McpProbeResult, McpMountMode, McpMountPayload, McpProtocolType
 * - ./useMcpIngressStore::useMcpIngressStore
 * - lucide-react::Plug, Check, ShieldCheck, AlertTriangle, ExternalLink, RefreshCw, Sparkles, UserPlus
 *
 * [OUTPUT]
 * - McpLinkMountCard: 会话流零摩擦 MCP/技能即时装配卡片组件
 *
 * [POS]
 * 在会话流中就地渲染探测到的第三方 MCP/Skill 工具能力，支持三级一键热挂载生效。
 */

'use client';

import React, { useState, useCallback } from 'react';
import {
  Plug,
  Check,
  ShieldCheck,
  AlertTriangle,
  ExternalLink,
  RefreshCw,
  Sparkles,
  UserPlus,
} from 'lucide-react';
import type { McpProbeResult, McpMountMode } from './mcpIngressTypes';
import { useMcpIngressStore } from './useMcpIngressStore';

export interface McpLinkMountCardProps {
  probe: McpProbeResult;
  sessionId: string;
  onMounted?: (mode: McpMountMode) => void;
  className?: string;
}

function getProtocolBadge(protocol: string): { label: string; className: string } {
  switch (protocol) {
    case 'mcp-sse':
      return { label: 'MCP (SSE)', className: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20' };
    case 'github-skill':
      return { label: 'GitHub Skill', className: 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20' };
    case 'openapi':
      return { label: 'OpenAPI Spec', className: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20' };
    case 'mcp-streamable':
    default:
      return { label: 'MCP (Streamable)', className: 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20' };
  }
}

export const McpLinkMountCard: React.FC<McpLinkMountCardProps> = ({
  probe,
  sessionId,
  onMounted,
  className = '',
}) => {
  const mountService = useMcpIngressStore((s) => s.mountService);
  const mountStatus = useMcpIngressStore((s) => s.mountStatuses[probe.url] || 'probed');
  const [selectedMode, setSelectedMode] = useState<McpMountMode>('session_ephemeral');

  const badge = getProtocolBadge(probe.protocol);
  const isMounted = mountStatus === 'mounted';
  const isMounting = mountStatus === 'mounting';

  const handleMount = useCallback(
    async (mode: McpMountMode) => {
      setSelectedMode(mode);
      const success = await mountService({
        url: probe.url,
        probe,
        mountMode: mode,
        sessionId,
      });
      if (success && onMounted) {
        onMounted(mode);
      }
    },
    [mountService, probe, sessionId, onMounted]
  );

  return (
    <article
      aria-label={`MCP 链接即时装配卡片 - ${probe.serviceName}`}
      className={`rounded-xl border p-4 text-xs transition-all shadow-xs ${
        isMounted
          ? 'bg-emerald-500/5 border-emerald-500/30'
          : 'bg-card/85 border-border/80 hover:border-primary/40'
      } ${className}`}
    >
      <header className="flex items-start justify-between gap-2.5 pb-2.5 border-b border-border/50">
        <div className="flex items-center gap-2 min-w-0">
          <div className="p-1.5 rounded-lg bg-primary/10 text-primary shrink-0">
            <Plug className="w-4 h-4" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h4 className="text-sm font-semibold text-foreground truncate">
                {probe.serviceName}
              </h4>
              <span className={`px-1.5 py-0.2 rounded border text-[10px] font-mono ${badge.className}`}>
                {badge.label}
              </span>
              <span className="flex items-center gap-0.5 px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-[10px] font-mono border border-emerald-500/20">
                <ShieldCheck className="w-2.5 h-2.5" aria-hidden="true" />
                <span>安全沙箱合格</span>
              </span>
            </div>
            <a
              href={probe.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[11px] text-muted-foreground hover:text-primary flex items-center gap-1 truncate mt-0.5"
            >
              <span className="truncate">{probe.url}</span>
              <ExternalLink className="w-2.5 h-2.5 shrink-0 opacity-70" aria-hidden="true" />
            </a>
          </div>
        </div>

        <span className="text-[10px] text-muted-foreground font-mono shrink-0 bg-muted px-1.5 py-0.5 rounded">
          {probe.probeDurationMs}ms 握手探针
        </span>
      </header>

      <div className="py-2.5 space-y-1.5">
        <div className="text-[11px] text-muted-foreground font-medium flex items-center justify-between">
          <span>嗅探到声明工具 ({probe.tools.length})：</span>
          <span className="text-[10px]">就地装配后当前会话立即生效</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
          {probe.tools.map((tool) => (
            <div
              key={tool.name}
              className="p-2 rounded-lg bg-muted/40 border border-border/40 text-[11px]"
            >
              <code className="text-primary font-mono font-medium block truncate">
                {tool.name}
              </code>
              <p className="text-muted-foreground text-[10px] truncate mt-0.5">
                {tool.description}
              </p>
            </div>
          ))}
        </div>
      </div>

      <footer className="flex items-center justify-between gap-2 pt-2.5 border-t border-border/50">
        <span className="text-[11px] text-muted-foreground">
          {isMounted
            ? selectedMode === 'session_ephemeral'
              ? '已临时装配至本会话'
              : selectedMode === 'agent_persistent'
              ? '已持久绑定至当前智能体'
              : '已成功衍生专属新智能体'
            : '无需跳出聊天，一键就地启用'}
        </span>

        <div className="flex items-center gap-1.5 ml-auto">
          {isMounted ? (
            <span className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-medium text-xs border border-emerald-500/20">
              <Check className="w-3.5 h-3.5" aria-hidden="true" />
              <span>已成功热挂载</span>
            </span>
          ) : (
            <>
              <button
                type="button"
                onClick={() => {
                  void handleMount('session_ephemeral');
                }}
                disabled={isMounting}
                className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors shadow-xs"
                aria-label="一键挂载至本会话"
              >
                {isMounting && selectedMode === 'session_ephemeral' ? (
                  <RefreshCw className="w-3 h-3 animate-spin" aria-hidden="true" />
                ) : (
                  <Sparkles className="w-3 h-3" aria-hidden="true" />
                )}
                <span>挂载至本会话</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  void handleMount('agent_persistent');
                }}
                disabled={isMounting}
                className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-secondary text-secondary-foreground text-xs font-medium hover:bg-secondary/80 disabled:opacity-50 transition-colors"
                aria-label="持久绑定至当前智能体"
              >
                {isMounting && selectedMode === 'agent_persistent' ? (
                  <RefreshCw className="w-3 h-3 animate-spin" aria-hidden="true" />
                ) : (
                  <Plug className="w-3 h-3" aria-hidden="true" />
                )}
                <span>持久绑定</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  void handleMount('clone_new_agent');
                }}
                disabled={isMounting}
                className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-muted-foreground hover:bg-muted text-xs transition-colors"
                aria-label="基于该 MCP 衍生新专业智能体"
                title="基于该 MCP 衍生新专业智能体"
              >
                <UserPlus className="w-3 h-3" aria-hidden="true" />
                <span>克隆衍生</span>
              </button>
            </>
          )}
        </div>
      </footer>
    </article>
  );
};
