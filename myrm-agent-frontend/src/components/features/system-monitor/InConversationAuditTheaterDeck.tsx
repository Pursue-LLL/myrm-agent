/**
 * [INPUT]: SessionDataAccessLedgerItem, refresh callback, and loading state.
 * [OUTPUT]: High-density industrial Lie-Immune InConversationAuditTheaterDeck component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/InConversationAuditTheaterDeck.tsx
 */

import React, { useState } from 'react';
import {
  InConversationAuditTheaterDeckProps,
  ResourceAccessEntryItem,
  ResourceAccessKindType,
  ResourceAccessModeType,
  TimelineAuditEventItem,
} from './auditTheaterTypes';

export const InConversationAuditTheaterDeck: React.FC<InConversationAuditTheaterDeckProps> = ({
  ledger,
  onRefresh,
  isLoading = false,
  className = '',
}) => {
  const [activeTab, setActiveTab] = useState<'timeline' | 'ledger'>('timeline');
  const [selectedKind, setSelectedKind] = useState<string>('all');

  const getModeBadge = (mode: ResourceAccessModeType) => {
    switch (mode) {
      case 'read':
        return <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-400 border border-blue-500/30">READ</span>;
      case 'write':
        return <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30">WRITE</span>;
      case 'execute':
      default:
        return <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-400 border border-purple-500/30">EXEC</span>;
    }
  };

  const getKindIcon = (kind: ResourceAccessKindType) => {
    switch (kind) {
      case 'file':
        return '📄';
      case 'memory':
        return '🧠';
      case 'connector_mcp':
        return '🔌';
      case 'web_network':
        return '🌐';
      default:
        return '📦';
    }
  };

  const filteredResources = selectedKind === 'all'
    ? ledger.resources
    : ledger.resources.filter((r) => r.kind === selectedKind);

  return (
    <div
      data-testid="audit-theater-deck"
      className={`w-full bg-zinc-950 text-zinc-100 border border-zinc-800 rounded-xl p-5 shadow-2xl space-y-5 font-mono ${className}`}
    >
      {/* Header bar with Lie-Immune Verification Badge */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xl font-bold tracking-tight text-white">
              🛡️ Authoritative Audit Theater
            </span>
            <span className="text-xs px-2.5 py-0.5 bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-full font-semibold flex items-center gap-1">
              <span>🔒</span> 撒谎免疫 (Lie-Immune)
            </span>
          </div>
          <p className="text-xs text-zinc-400 mt-1">
            Authoritative audit trail sourced 100% from backend execution hooks. Zero model self-narration hallucination.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="text-[11px] bg-zinc-900 border border-zinc-800 rounded px-2.5 py-1 text-zinc-400">
            <span className="text-zinc-500">SHA-256: </span>
            <span className="text-indigo-400 font-mono font-semibold" title={ledger.digest_sha256}>
              {ledger.digest_sha256.slice(0, 16)}...
            </span>
          </div>
          {onRefresh && (
            <button
              onClick={() => onRefresh()}
              disabled={isLoading}
              className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-xs text-zinc-200 rounded border border-zinc-700 transition disabled:opacity-50"
            >
              {isLoading ? 'Refreshing...' : '🔄 Refresh Audit'}
            </button>
          )}
        </div>
      </div>

      {/* Top Resource Metrics Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <div className="text-xs text-zinc-400">Files Read</div>
          <div className="text-xl font-bold text-blue-400 mt-0.5">{ledger.total_files_read}</div>
        </div>
        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <div className="text-xs text-zinc-400">Files Written</div>
          <div className="text-xl font-bold text-amber-400 mt-0.5">{ledger.total_files_written}</div>
        </div>
        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <div className="text-xs text-zinc-400">Memories Queried</div>
          <div className="text-xl font-bold text-purple-400 mt-0.5">{ledger.total_memories_queried}</div>
        </div>
        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <div className="text-xs text-zinc-400">Domains Visited</div>
          <div className="text-xl font-bold text-emerald-400 mt-0.5">{ledger.total_network_domains_visited}</div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex items-center justify-between border-b border-zinc-800/80 pb-2">
        <div className="flex gap-2">
          <button
            onClick={() => setActiveTab('timeline')}
            className={`px-3 py-1 rounded text-xs font-medium transition ${
              activeTab === 'timeline'
                ? 'bg-indigo-600 text-white'
                : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200'
            }`}
          >
            Action Timeline ({ledger.events.length})
          </button>
          <button
            onClick={() => setActiveTab('ledger')}
            className={`px-3 py-1 rounded text-xs font-medium transition ${
              activeTab === 'ledger'
                ? 'bg-indigo-600 text-white'
                : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200'
            }`}
          >
            Data Access Ledger ({ledger.resources.length})
          </button>
        </div>

        {activeTab === 'ledger' && (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-zinc-500">Resource Kind:</span>
            <select
              value={selectedKind}
              aria-label="Resource Kind"
              onChange={(e) => setSelectedKind(e.target.value)}
              className="bg-zinc-900 border border-zinc-700 text-zinc-200 rounded px-2 py-0.5"
            >
              <option value="all">All Resources</option>
              <option value="file">Files Only</option>
              <option value="memory">Memories Only</option>
              <option value="connector_mcp">MCP Connectors Only</option>
              <option value="web_network">Web &amp; Network Only</option>
            </select>
          </div>
        )}
      </div>

      {/* Main Tab Panels */}
      {activeTab === 'timeline' && (
        <div className="space-y-3">
          {ledger.events.length === 0 ? (
            <div className="text-center py-10 text-zinc-500 text-sm">
              No audit events recorded for this session.
            </div>
          ) : (
            <div className="space-y-2">
              {ledger.events.map((event) => (
                <div
                  key={event.event_id}
                  className={`p-3 rounded-lg border text-xs flex flex-col md:flex-row md:items-center justify-between gap-2 ${
                    event.is_plan
                      ? 'bg-indigo-950/20 border-indigo-800/40'
                      : 'bg-zinc-900/50 border-zinc-800/80 hover:bg-zinc-900/80'
                  }`}
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      {event.is_plan ? (
                        <span className="px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 font-semibold text-[10px]">
                          PLANNED INTENTION
                        </span>
                      ) : (
                        <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-semibold text-[10px]">
                          EXECUTED ACTION
                        </span>
                      )}
                      <span className="font-semibold text-white">{event.step_name}</span>
                    </div>
                    <div className="text-zinc-400 font-mono text-[11px] flex items-center gap-2">
                      <span>Tool: <span className="text-zinc-200">{event.tool_name}</span></span>
                      {event.inputs_summary && (
                        <span>• Input: <span className="text-zinc-400 truncate max-w-sm">{event.inputs_summary}</span></span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-3 text-right">
                    {!event.is_plan && (
                      <span className="text-zinc-400 text-[11px]">{event.duration_ms} ms</span>
                    )}
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        event.status === 'completed'
                          ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                          : event.status === 'failed'
                          ? 'bg-rose-950 text-rose-400 border border-rose-800'
                          : 'bg-amber-950 text-amber-400 border border-amber-800'
                      }`}
                    >
                      {event.status.toUpperCase()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'ledger' && (
        <div className="space-y-3">
          {filteredResources.length === 0 ? (
            <div className="text-center py-10 text-zinc-500 text-sm">
              No data resources matched the selected filter.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border border-zinc-800/80 rounded-lg">
                <thead className="bg-zinc-900/90 text-zinc-400 uppercase border-b border-zinc-800">
                  <tr>
                    <th className="py-2.5 px-3">Resource Target</th>
                    <th className="py-2.5 px-2">Type</th>
                    <th className="py-2.5 px-2">Mode</th>
                    <th className="py-2.5 px-2">Scope / Granularity</th>
                    <th className="py-2.5 px-2">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60 bg-zinc-950/40">
                  {filteredResources.map((res) => (
                    <tr key={res.entry_id} className="hover:bg-zinc-900/40">
                      <td className="py-2.5 px-3">
                        <div className="font-semibold text-white flex items-center gap-1.5">
                          <span>{getKindIcon(res.kind)}</span>
                          <span className="truncate max-w-md" title={res.resource_id}>
                            {res.resource_id}
                          </span>
                        </div>
                      </td>
                      <td className="py-2.5 px-2 text-zinc-400">{res.kind}</td>
                      <td className="py-2.5 px-2">{getModeBadge(res.mode)}</td>
                      <td className="py-2.5 px-2 text-zinc-300 font-mono text-[11px]">
                        {res.scope_detail || 'full_access'}
                      </td>
                      <td className="py-2.5 px-2">
                        {res.success ? (
                          <span className="text-emerald-400 font-bold">✓ SUCCESS</span>
                        ) : (
                          <span className="text-rose-400 font-bold">✗ FAILED</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
