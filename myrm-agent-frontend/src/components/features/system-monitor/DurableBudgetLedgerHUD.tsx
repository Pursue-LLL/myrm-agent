/**
 * [INPUT]: DurableBudgetRecoverySummaryItem, SessionActualBilledStatementItem, callbacks.
 * [OUTPUT]: High-density industrial DurableBudgetLedgerHUD component recovering daily budget from durable ledger instead of fragile surviving messages.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/DurableBudgetLedgerHUD.tsx
 */

import React, { useState } from 'react';
import {
  DurableBudgetLedgerHUDProps,
  DurableSpendLedgerRecordItem,
  SpendCategoryType,
} from './durableBudgetLedgerTypes';

export const DurableBudgetLedgerHUD: React.FC<DurableBudgetLedgerHUDProps> = ({
  summary,
  statement,
  onRefresh,
  onReset,
  className = '',
}) => {
  const [activeTab, setActiveTab] = useState<'overview' | 'statement'>('overview');

  const getCategoryBadge = (category: SpendCategoryType) => {
    switch (category) {
      case 'chat':
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30">
            CHAT
          </span>
        );
      case 'auxiliary':
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">
            AUXILIARY
          </span>
        );
      case 'cache_warm':
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
            CACHE WARM
          </span>
        );
      case 'subagent':
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
            SUBAGENT
          </span>
        );
      case 'system':
      default:
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] text-zinc-400 border border-zinc-700/60">
            SYSTEM
          </span>
        );
    }
  };

  return (
    <div
      data-testid="durable-budget-hud"
      className={`w-full bg-zinc-950 text-zinc-100 border border-zinc-800 rounded-xl p-5 shadow-2xl space-y-5 font-mono ${className}`}
    >
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <h2 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
            <span>📊</span>
            <span>Durable Daily Budget Recovery &amp; Actual Billed HUD</span>
          </h2>
          <p className="text-xs text-zinc-400 mt-1">
            Recovering daily spend from persistent ledger records — preventing underestimation from deleted or rewound turns.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {onRefresh && (
            <button
              data-testid="refresh-budget-ledger-btn"
              onClick={onRefresh}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-zinc-800 text-zinc-300 border border-zinc-700 hover:bg-zinc-700 transition-all"
            >
              Refresh
            </button>
          )}

          {onReset && (
            <button
              data-testid="reset-budget-ledger-btn"
              onClick={onReset}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/40 hover:bg-rose-500/30 transition-all"
            >
              Reset
            </button>
          )}
        </div>
      </div>

      {/* Underestimation Warning Banner */}
      {summary.budget_underestimation_gap_usd > 0 ? (
        <div
          data-testid="underestimation-gap-banner"
          className="p-3 bg-amber-500/15 border border-amber-500/30 rounded-lg flex items-center justify-between gap-3 text-xs"
        >
          <div className="flex items-center gap-2 text-amber-300">
            <span className="text-base">⚠️</span>
            <span>
              Prevented <strong>${summary.budget_underestimation_gap_usd.toFixed(4)}</strong> budget underestimation!
              Fragile message-summing missed rewound/deleted turns (${summary.discarded_branch_cost_usd.toFixed(4)}).
            </span>
          </div>
          <span className="text-[11px] font-semibold text-amber-400 uppercase bg-amber-500/20 px-2 py-0.5 rounded border border-amber-500/30">
            Durable Ledger Reconciled
          </span>
        </div>
      ) : (
        <div
          data-testid="perfect-match-banner"
          className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-lg flex items-center gap-2 text-xs text-emerald-300"
        >
          <span>✅</span>
          <span>Surviving messages match durable ledger perfectly ($0.00 gap).</span>
        </div>
      )}

      {/* Aggregate Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <span className="text-[11px] text-zinc-400 block">Durable Recovered Spend</span>
          <span data-testid="total-durable-cost-val" className="text-2xl font-bold text-cyan-400">
            ${summary.total_durable_cost_usd.toFixed(4)}
          </span>
        </div>

        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <span className="text-[11px] text-zinc-400 block">Fragile Surviving Messages</span>
          <span data-testid="surviving-msg-cost-val" className="text-2xl font-bold text-zinc-300">
            ${summary.total_surviving_message_cost_usd.toFixed(4)}
          </span>
        </div>

        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <span className="text-[11px] text-zinc-400 block">Discarded / Rewound Spend</span>
          <span
            data-testid="discarded-branch-cost-val"
            className={`text-2xl font-bold ${
              summary.discarded_branch_cost_usd > 0 ? 'text-amber-400' : 'text-zinc-500'
            }`}
          >
            ${summary.discarded_branch_cost_usd.toFixed(4)}
          </span>
        </div>

        <div className="bg-zinc-900/80 border border-zinc-800/80 rounded-lg p-3">
          <span className="text-[11px] text-zinc-400 block">Budget Underestimate Gap</span>
          <span
            data-testid="underestimation-gap-val"
            className={`text-2xl font-bold ${
              summary.budget_underestimation_gap_usd > 0 ? 'text-rose-400' : 'text-emerald-400'
            }`}
          >
            ${summary.budget_underestimation_gap_usd.toFixed(4)}
          </span>
        </div>
      </div>

      {/* Tab Switcher if Statement is Provided */}
      {statement && (
        <div className="flex border-b border-zinc-800 text-xs">
          <button
            data-testid="tab-overview"
            onClick={() => setActiveTab('overview')}
            className={`pb-2 px-3 font-semibold border-b-2 transition-all ${
              activeTab === 'overview'
                ? 'border-cyan-400 text-cyan-400'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            Daily Spend Categories
          </button>
          <button
            data-testid="tab-statement"
            onClick={() => setActiveTab('statement')}
            className={`pb-2 px-3 font-semibold border-b-2 transition-all ${
              activeTab === 'statement'
                ? 'border-cyan-400 text-cyan-400'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            Session Actual Billed ({statement.session_id})
          </button>
        </div>
      )}

      {/* Categories Breakdown */}
      {activeTab === 'overview' && (
        <div className="space-y-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-zinc-300">
            Durable Spend by Invocation Category ({summary.date_utc})
          </span>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            {Object.entries(summary.category_breakdown).map(([cat, cost]) => (
              <div
                key={cat}
                data-testid={`cat-card-${cat}`}
                className="bg-zinc-900/60 border border-zinc-800/80 rounded p-2.5 flex justify-between items-center"
              >
                <span className="text-zinc-400 uppercase text-[11px]">{cat}</span>
                <span className="font-bold text-zinc-200">${cost.toFixed(4)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Session Actual Billed Statement Table */}
      {activeTab === 'statement' && statement && (
        <div className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs bg-zinc-900/60 p-3 rounded-lg border border-zinc-800">
            <div>
              <span className="text-zinc-500 block text-[10px]">Actual Billed Total</span>
              <span data-testid="actual-billed-total" className="text-base font-bold text-cyan-400">
                ${statement.actual_billed_cost_usd.toFixed(4)}
              </span>
            </div>
            <div>
              <span className="text-zinc-500 block text-[10px]">Visible Active Branch</span>
              <span data-testid="visible-branch-total" className="text-base font-bold text-zinc-200">
                ${statement.visible_branch_cost_usd.toFixed(4)}
              </span>
            </div>
            <div>
              <span className="text-zinc-500 block text-[10px]">Discarded Turns Diff</span>
              <span data-testid="discarded-diff-total" className="text-base font-bold text-amber-400">
                ${statement.discarded_diff_cost_usd.toFixed(4)}
              </span>
            </div>
          </div>

          <div className="overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-900/40">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-900/80 text-zinc-400 uppercase text-[10px]">
                  <th className="py-2 px-3">Record ID</th>
                  <th className="py-2 px-3">Message ID</th>
                  <th className="py-2 px-3">Category</th>
                  <th className="py-2 px-3">Branch State</th>
                  <th className="py-2 px-3 text-right">Cost (USD)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60">
                {statement.records.map((r: DurableSpendLedgerRecordItem) => (
                  <tr
                    key={r.record_id}
                    data-testid={`statement-row-${r.record_id}`}
                    className="hover:bg-zinc-800/40 transition-colors"
                  >
                    <td className="py-2 px-3 font-mono text-[11px] text-zinc-400">{r.record_id}</td>
                    <td className="py-2 px-3 text-zinc-300">{r.message_id || '—'}</td>
                    <td className="py-2 px-3">{getCategoryBadge(r.category)}</td>
                    <td className="py-2 px-3">
                      {r.is_active_branch ? (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                          ACTIVE BRANCH
                        </span>
                      ) : (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30">
                          DISCARDED (REWOUND)
                        </span>
                      )}
                    </td>
                    <td className="py-2 px-3 text-right font-medium text-cyan-300">
                      ${r.cost_usd.toFixed(4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
