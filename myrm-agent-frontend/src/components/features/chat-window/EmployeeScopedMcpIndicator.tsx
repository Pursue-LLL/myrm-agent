'use client';

/**
 * [INPUT]: agentId, EmployeeToolScopePolicy, 过滤后的白名单/阻断工具统计
 * [OUTPUT]: 渲染数字员工 MCP 工具作用域隔离指示器胶囊条，展示授权服务器、白名单工具与物理裁剪拦截详情
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/EmployeeScopedMcpIndicator.tsx
 */

import React, { useState } from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  Server,
  Wrench,
  ChevronDown,
  ChevronUp,
  Lock,
  EyeOff,
} from 'lucide-react';

export interface McpScopingToolItem {
  serverName: string;
  toolName: string;
  isAllowed: boolean;
  reason: string;
  description?: string;
}

export interface EmployeeScopedMcpIndicatorProps {
  agentId: string;
  allowedServers: string[];
  allowedToolsCount: number;
  blockedToolsCount?: number;
  strictMode?: boolean;
  blockedToolsList?: McpScopingToolItem[];
  allowedToolsList?: McpScopingToolItem[];
  className?: string;
}

export function EmployeeScopedMcpIndicator({
  agentId,
  allowedServers,
  allowedToolsCount,
  blockedToolsCount = 0,
  strictMode = true,
  blockedToolsList = [],
  allowedToolsList = [],
  className = '',
}: EmployeeScopedMcpIndicatorProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div
      data-testid="employee-scoped-mcp-indicator"
      className={`rounded-md border border-zinc-200 dark:border-zinc-800 bg-white/60 dark:bg-zinc-900/60 p-2 text-xs transition-all shadow-2xs ${className}`}
    >
      {/* Capsule Header */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="flex items-center gap-1 font-medium text-zinc-800 dark:text-zinc-200">
            {strictMode ? (
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
            ) : (
              <ShieldAlert className="w-3.5 h-3.5 text-amber-500" />
            )}
            <span className="font-semibold">MCP 员工作用域</span>
          </span>

          <span
            data-testid="agent-id-badge"
            className="font-mono text-[11px] px-1.5 py-0.2 rounded bg-black/5 dark:bg-white/10 text-zinc-600 dark:text-zinc-300"
          >
            @{agentId}
          </span>

          {strictMode && (
            <span
              data-testid="strict-mode-badge"
              className="flex items-center gap-0.5 text-[10px] px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-medium"
            >
              <Lock className="w-2.5 h-2.5" />
              严格物理隔离
            </span>
          )}

          <span className="flex items-center gap-1 text-[11px] text-zinc-500 dark:text-zinc-400">
            <Server className="w-3 h-3" />
            <span>{allowedServers.length} 个服务</span>
          </span>

          <span className="flex items-center gap-1 text-[11px] text-zinc-500 dark:text-zinc-400">
            <Wrench className="w-3 h-3" />
            <span>{allowedToolsCount} 个工具可用</span>
          </span>

          {blockedToolsCount > 0 && (
            <span
              data-testid="blocked-tools-badge"
              className="flex items-center gap-0.5 text-[10px] px-1.5 py-0.2 rounded bg-rose-500/10 text-rose-600 dark:text-rose-400 font-medium"
            >
              <EyeOff className="w-2.5 h-2.5" />
              已裁剪 {blockedToolsCount} 个越权工具
            </span>
          )}
        </div>

        <button
          type="button"
          data-testid="toggle-scope-details-btn"
          onClick={() => setIsExpanded((prev) => !prev)}
          className="flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 cursor-pointer p-0.5 rounded transition-colors"
          title={isExpanded ? '收起作用域详情' : '展开作用域详情'}
        >
          <span>{isExpanded ? '收起详情' : '查看作用域清单'}</span>
          {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </button>
      </div>

      {/* Expanded Scope Breakdown */}
      {isExpanded && (
        <div
          data-testid="scope-details-section"
          className="mt-2 pt-2 border-t border-zinc-100 dark:border-zinc-800 text-[11px] space-y-2"
        >
          {/* Allowed Servers Chips */}
          <div>
            <span className="text-zinc-500 dark:text-zinc-400 font-medium">授权 MCP 服务：</span>
            <div className="flex items-center gap-1.5 mt-1 flex-wrap">
              {allowedServers.length === 0 ? (
                <span className="text-zinc-400 italic text-[10px]">未绑定任何 MCP 服务</span>
              ) : (
                allowedServers.map((srv) => (
                  <span
                    key={srv}
                    data-testid={`allowed-server-${srv}`}
                    className="px-2 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 font-mono text-[10px]"
                  >
                    {srv}
                  </span>
                ))
              )}
            </div>
          </div>

          {/* Blocked Scoped Tools List */}
          {blockedToolsList.length > 0 && (
            <div data-testid="blocked-tools-section" className="space-y-1">
              <span className="text-rose-600 dark:text-rose-400 font-medium flex items-center gap-1">
                <EyeOff className="w-3 h-3" />
                物理裁剪遮蔽的越权工具 ({blockedToolsList.length})：
              </span>
              <div className="max-h-28 overflow-y-auto space-y-1 pr-1">
                {blockedToolsList.map((t) => (
                  <div
                    key={`${t.serverName}-${t.toolName}`}
                    className="flex items-center justify-between gap-2 p-1.5 rounded bg-rose-50/60 dark:bg-rose-950/30 border border-rose-200/50 dark:border-rose-900/40 text-[10px]"
                  >
                    <span className="font-mono text-zinc-700 dark:text-zinc-300 truncate">
                      {t.serverName}/{t.toolName}
                    </span>
                    <span className="text-rose-600 dark:text-rose-400 shrink-0 truncate max-w-[200px]">
                      {t.reason}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Allowed Tools Sample List */}
          {allowedToolsList.length > 0 && (
            <div data-testid="allowed-tools-section" className="space-y-1">
              <span className="text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-1">
                <Wrench className="w-3 h-3" />
                已授权可用工具清单 ({allowedToolsList.length})：
              </span>
              <div className="flex items-center gap-1 flex-wrap">
                {allowedToolsList.map((t) => (
                  <span
                    key={`${t.serverName}-${t.toolName}`}
                    className="font-mono px-1.5 py-0.2 rounded bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 text-[10px] border border-emerald-200/40 dark:border-emerald-900/30"
                  >
                    {t.serverName}/{t.toolName}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default EmployeeScopedMcpIndicator;
