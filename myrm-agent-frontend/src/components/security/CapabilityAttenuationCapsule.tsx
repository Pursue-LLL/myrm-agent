// @orphan-ok Object-Capability (OCap) attenuation status capsule for subagent tasks
'use client';

import React, { useState } from 'react';
import { ShieldCheck, Shield, ChevronDown, ChevronUp, Clock, FileCode, Globe, Cpu } from 'lucide-react';

export interface AttenuatedCapabilityInfo {
  handleId: string;
  subjectId: string;
  actions: ('read' | 'write' | 'execute' | 'egress' | 'mcp')[];
  paths?: string[];
  domains?: string[];
  mcpTools?: string[];
  remainingTtlSeconds?: number;
}

interface CapabilityAttenuationCapsuleProps {
  capability: AttenuatedCapabilityInfo;
  className?: string;
}

export const CapabilityAttenuationCapsule: React.FC<CapabilityAttenuationCapsuleProps> = ({
  capability,
  className = '',
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const isReadOnly = capability.actions.length === 1 && capability.actions[0] === 'read';
  const hasPaths = capability.paths && capability.paths.length > 0;
  const hasDomains = capability.domains && capability.domains.length > 0;
  const hasMcp = capability.mcpTools && capability.mcpTools.length > 0;

  return (
    <div
      className={`inline-flex flex-col rounded-lg border border-emerald-500/30 bg-emerald-500/10 dark:bg-emerald-950/40 text-xs text-foreground transition-all duration-200 ${className}`}
      data-testid="capability-attenuation-capsule"
    >
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-1.5 px-2.5 py-1 text-emerald-700 dark:text-emerald-400 hover:text-emerald-800 dark:hover:text-emerald-300 font-medium focus:outline-none focus-visible:ring-1 focus-visible:ring-emerald-500 rounded-md"
        aria-expanded={isExpanded}
        aria-label="查看细粒度安全授权范围"
      >
        <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
        <span className="font-mono text-[11px]">{isReadOnly ? '只读受限沙箱' : '零信任 OCap 拘禁'}</span>
        {capability.remainingTtlSeconds !== undefined && (
          <span className="flex items-center gap-0.5 text-[10px] text-muted-foreground ml-1">
            <Clock className="h-3 w-3" />
            {Math.max(0, Math.round(capability.remainingTtlSeconds))}s
          </span>
        )}
        {isExpanded ? (
          <ChevronUp className="h-3 w-3 ml-0.5 opacity-70" />
        ) : (
          <ChevronDown className="h-3 w-3 ml-0.5 opacity-70" />
        )}
      </button>

      {isExpanded && (
        <div className="border-t border-emerald-500/20 px-3 py-2 space-y-1.5 bg-background/80 rounded-b-lg">
          <div className="flex items-center justify-between text-[11px] text-muted-foreground pb-1 border-b border-border/50">
            <span>句柄标识:</span>
            <span className="font-mono text-foreground font-semibold">{capability.handleId}</span>
          </div>

          <div className="flex items-start gap-1 text-[11px]">
            <Shield className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-0.5" />
            <span className="text-muted-foreground">允许动词:</span>
            <div className="flex flex-wrap gap-1 ml-1">
              {capability.actions.map((act) => (
                <span
                  key={act}
                  className="px-1.5 py-0.2 rounded bg-secondary text-secondary-foreground font-mono text-[10px]"
                >
                  {act.toUpperCase()}
                </span>
              ))}
            </div>
          </div>

          {hasPaths && (
            <div className="flex items-start gap-1 text-[11px]">
              <FileCode className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-0.5" />
              <span className="text-muted-foreground">路径约束:</span>
              <div className="flex flex-col gap-0.5 ml-1 font-mono text-[10px] text-foreground">
                {capability.paths?.map((p) => (
                  <span key={p} className="truncate max-w-[200px]" title={p}>
                    {p}
                  </span>
                ))}
              </div>
            </div>
          )}

          {hasDomains && (
            <div className="flex items-start gap-1 text-[11px]">
              <Globe className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-0.5" />
              <span className="text-muted-foreground">网络白名单:</span>
              <div className="flex flex-wrap gap-1 ml-1 font-mono text-[10px] text-foreground">
                {capability.domains?.map((d) => (
                  <span key={d} className="px-1 bg-secondary rounded">
                    {d}
                  </span>
                ))}
              </div>
            </div>
          )}

          {hasMcp && (
            <div className="flex items-start gap-1 text-[11px]">
              <Cpu className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-0.5" />
              <span className="text-muted-foreground">MCP 工具:</span>
              <div className="flex flex-wrap gap-1 ml-1 font-mono text-[10px] text-foreground">
                {capability.mcpTools?.map((m) => (
                  <span key={m} className="px-1 bg-secondary rounded">
                    {m}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
