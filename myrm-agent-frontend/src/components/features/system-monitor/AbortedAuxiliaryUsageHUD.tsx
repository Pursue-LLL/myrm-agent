/**
 * [INPUT]: AbortedUsageUnknownStatsItem, CanonicalUsageLedgerRowItem list, refresh and reset callbacks.
 * [OUTPUT]: High-density industrial AbortedAuxiliaryUsageHUD component guarding against pseudo-free zero-token representations.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/AbortedAuxiliaryUsageHUD.tsx
 */

import React, { useState } from 'react';
import {
  AbortedAuxiliaryUsageHUDProps,
  AuxiliaryCallKindType,
  CanonicalUsageLedgerRowItem,
  LedgerCallStatusType,
  UsageAvailabilityKindType,
} from './abortedUsageLedgerTypes';

export const AbortedAuxiliaryUsageHUD: React.FC<AbortedAuxiliaryUsageHUDProps> = ({
  stats,
  records,
  onRefresh,
  onReset,
  className = '',
}) => {
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [selectedAvailability, setSelectedAvailability] = useState<string>('all');

  const getCallKindBadge = (kind: AuxiliaryCallKindType) => {
    switch (kind) {
      case 'primary':
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30">
            PRIMARY
          </span>
        );
      case 'auxiliary_summary':
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">
            SUMMARY
          </span>
        );
      case 'auxiliary_audit':
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">
            AUDIT
          </span>
        );
      case 'auxiliary_compaction':
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
            COMPACT
          </span>
        );
      case 'auxiliary_router':
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
            ROUTER
          </span>
        );
      case 'auxiliary_other':
      default:
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] text-zinc-400 border border-zinc-700/60">
            OTHER
          </span>
        );
    }
  };

  const getStatusBadge = (status: LedgerCallStatusType) => {
    switch (status) {
      case 'completed':
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
            COMPLETED
          </span>
        );
      case 'aborted':
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
            ABORTED
          </span>
        );
      case 'failed':
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-600/20 text-red-400 border border-red-600/30">
            FAILED
          </span>
        );
      case 'cancelled':
      default:
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-zinc-700 text-zinc-300 border border-zinc-600">
            CANCELLED
          </span>
        );
    }
  };

  const getAvailabilityBadge = (avail: UsageAvailabilityKindType) => {
    switch (avail) {
      case 'exact':
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
            EXACT
          </span>
        );
      case 'usage-unknown':
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
            USAGE-UNKNOWN
          </span>
        );
      case 'estimated':
      default:
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
            ESTIMATED
          </span>
        );
    }
  };

  const filteredRecords = records.filter((r) => {
    const matchStatus = selectedStatus === 'all' || r.call_status === selectedStatus;
    const matchAvailability =
      selectedAvailability === 'all' || r.usage_availability === selectedAvailability;
    return matchStatus && matchAvailability;
  });

  return (
    <div
      data-testid="aborted-usage-hud"
      className={`w-full bg-zinc-950 text-zinc-100 border border-zinc-800 rounded-xl p-5 shadow-2xl space-y-5 font-mono ${className}`}
    >
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <h2 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
            <span>🛡️</span>
            <span>Auxiliary Usage Ledger &amp; Unknown-Usage Guard</span>
          </h2>
          <p className="text-xs text-zinc-400 mt-1">
            Canonical usage ledger preventing pseudo-free zero-token representations on aborted auxiliary calls.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {onRefresh && (
            <button
              data-testid="refresh-ledger-btn"
              onClick={onRefresh}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-zinc-800 text-zinc-300 border border-zinc-700 hover:bg-zinc-700 transition-all"
            >
              Refresh
            </button>
          )}
          {onReset && (
            <button
              data-testid="reset-ledger-btn"
              onClick={onReset}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/40 hover:bg-rose-500/30 transition-all"
            >
              Reset
            </button>
          )}
        </div>
      </div>

      {/* Financial Risk Banner */}
      {stats.unknown_risk_flag ? (
        <div
          data-testid="unknown-risk-banner"
          className="p-3 bg-amber-500/15 border border-amber-500/30 rounded-lg flex items-center justify-between gap-3 text-xs"
        >
          <div className="flex items-center gap-2 text-amber-300">
            <span className="text-base">⚠️</span>
            <span>
              Detected <strong>{stats.unknown_usage_calls}</strong> aborted auxiliary call(s) with unknown usage.
              Strictly prohibited from 0-token pseudo-free illusion.
            </span>
          </div>
          <span className="text-[11px] font-semibold text-amber-400 uppercase bg-amber-500/20 px-2 py-0.5 rounded border border-amber-500/30">
            Financial Audit Protected
          </span>
        </div>
      ) : (
        <div
          data-testid="clean-audit-banner"
          className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-lg flex items-center gap-2 text-xs text-emerald-300"
        >
          <span>✅</span>
          <span>All auxiliary model calls reconciled with exact token usage. Zero unaccounted calls.</span>
        </div>
      )}

      {/* Aggregate Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <span className="text-[11px] text-zinc-400 block">Total Invocations</span>
          <span data-testid="total-calls-val" className="text-2xl font-bold text-zinc-100">
            {stats.total_calls}
          </span>
        </div>

        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <span className="text-[11px] text-zinc-400 block">Exact Usage Calls</span>
          <div className="flex items-baseline gap-2">
            <span data-testid="known-calls-val" className="text-2xl font-bold text-emerald-400">
              {stats.known_usage_calls}
            </span>
            <span className="text-xs text-zinc-500">
              ({stats.total_known_tokens.toLocaleString()} tokens)
            </span>
          </div>
        </div>

        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <span className="text-[11px] text-zinc-400 block">Unknown-Usage Calls</span>
          <span
            data-testid="unknown-calls-val"
            className={`text-2xl font-bold ${
              stats.unknown_usage_calls > 0 ? 'text-amber-400' : 'text-zinc-500'
            }`}
          >
            {stats.unknown_usage_calls}
          </span>
        </div>

        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <span className="text-[11px] text-zinc-400 block">Reconciled Cost (USD)</span>
          <span data-testid="total-cost-val" className="text-2xl font-bold text-cyan-400">
            ${stats.total_known_cost_usd.toFixed(4)}
          </span>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs bg-zinc-900/50 p-2 rounded-lg border border-zinc-800/60">
        <div className="flex items-center gap-1">
          <span className="text-zinc-500 mr-2">Status:</span>
          {['all', 'completed', 'aborted', 'failed'].map((st) => (
            <button
              key={st}
              data-testid={`filter-status-${st}`}
              onClick={() => setSelectedStatus(st)}
              className={`px-2.5 py-1 rounded transition-colors ${
                selectedStatus === st
                  ? 'bg-zinc-700 text-zinc-100 font-bold'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              {st.toUpperCase()}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1">
          <span className="text-zinc-500 mr-2">Availability:</span>
          {['all', 'exact', 'usage-unknown'].map((av) => (
            <button
              key={av}
              data-testid={`filter-avail-${av}`}
              onClick={() => setSelectedAvailability(av)}
              className={`px-2.5 py-1 rounded transition-colors ${
                selectedAvailability === av
                  ? 'bg-zinc-700 text-zinc-100 font-bold'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              {av.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Ledger Table */}
      <div className="overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-900/40">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-zinc-800 bg-zinc-900/80 text-zinc-400 uppercase text-[10px]">
              <th className="py-2.5 px-3">Task ID / Call ID</th>
              <th className="py-2.5 px-3">Call Kind</th>
              <th className="py-2.5 px-3">Status</th>
              <th className="py-2.5 px-3">Availability</th>
              <th className="py-2.5 px-3 text-right">Tokens (Prompt + Compl)</th>
              <th className="py-2.5 px-3 text-right">Total Tokens</th>
              <th className="py-2.5 px-3 text-right">Cost (USD)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60">
            {filteredRecords.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-6 text-center text-zinc-500">
                  No canonical ledger invocations found.
                </td>
              </tr>
            ) : (
              filteredRecords.map((row) => (
                <tr
                  key={row.call_id}
                  data-testid={`ledger-row-${row.task_id}`}
                  className="hover:bg-zinc-800/40 transition-colors"
                >
                  <td className="py-2.5 px-3">
                    <span className="font-semibold text-zinc-200 block">{row.task_id}</span>
                    <span className="text-[10px] text-zinc-500 font-mono">{row.call_id}</span>
                  </td>
                  <td className="py-2.5 px-3 whitespace-nowrap">{getCallKindBadge(row.call_kind)}</td>
                  <td className="py-2.5 px-3 whitespace-nowrap">{getStatusBadge(row.call_status)}</td>
                  <td className="py-2.5 px-3 whitespace-nowrap">{getAvailabilityBadge(row.usage_availability)}</td>
                  <td className="py-2.5 px-3 text-right">
                    {row.usage_availability === 'usage-unknown' ? (
                      <span className="text-zinc-500 italic">Unknown</span>
                    ) : (
                      <span className="text-zinc-300">
                        {row.prompt_tokens ?? 0} + {row.completion_tokens ?? 0}
                      </span>
                    )}
                  </td>
                  <td className="py-2.5 px-3 text-right font-medium">
                    {row.usage_availability === 'usage-unknown' ? (
                      <span
                        data-testid={`token-unknown-${row.task_id}`}
                        className="text-amber-400 font-semibold italic text-[11px]"
                      >
                        Usage-Unknown (Not 0)
                      </span>
                    ) : (
                      <span className="text-zinc-100">{row.total_tokens?.toLocaleString()}</span>
                    )}
                  </td>
                  <td className="py-2.5 px-3 text-right font-medium">
                    {row.usage_availability === 'usage-unknown' ? (
                      <span
                        data-testid={`cost-unknown-${row.task_id}`}
                        className="text-amber-400/90 italic text-[11px]"
                      >
                        Unaccounted
                      </span>
                    ) : (
                      <span className="text-cyan-300">${(row.cost_usd ?? 0).toFixed(4)}</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
