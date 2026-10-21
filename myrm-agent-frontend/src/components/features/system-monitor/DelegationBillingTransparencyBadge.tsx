/**
 * [INPUT]: DelegationUsageBadgeData, compact flag, onOpenDetails callback.
 * [OUTPUT]: High-clarity dual-track billing transparency badge component for subscription vs API key delegations.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/DelegationBillingTransparencyBadge.tsx
 */

import React, { useState } from 'react';
import { DelegationBillingTransparencyBadgeProps } from './delegationBillingTypes';

export const DelegationBillingTransparencyBadge: React.FC<DelegationBillingTransparencyBadgeProps> = ({
  usage,
  compact = false,
  onOpenDetails,
  className = '',
}) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(false);

  const isSubscription = usage.billable === false || usage.auth_mode === 'subscription';
  const isApiKey = usage.billable === true || usage.auth_mode === 'api_key';
  const hasDelegationMeta = Boolean(usage.auth_mode || usage.source);

  // Fallback if not a delegation event
  if (!hasDelegationMeta && !usage.total_tokens) {
    return null;
  }

  const sourceName = usage.source ? usage.source.replace(/^delegate:|^invoke_acp:/, '') : 'direct';

  return (
    <div
      data-testid="delegation-billing-badge"
      className={`inline-flex flex-col text-xs font-mono transition-all ${className}`}
    >
      <div className="flex items-center gap-1.5 flex-wrap">
        {/* Main entitlement split capsule */}
        {isSubscription ? (
          <button
            type="button"
            onClick={() => {
              setIsExpanded(!isExpanded);
              onOpenDetails?.();
            }}
            aria-label="Subscription delegation badge"
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20 transition cursor-pointer"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="font-semibold">
              订阅额度 {usage.total_tokens.toLocaleString()} tokens
            </span>
            <span className="px-1.5 py-0.2 rounded bg-emerald-950/60 text-[10px] text-emerald-300 font-bold border border-emerald-800/60">
              不计费
            </span>
            {usage.estimated_savings_usd !== undefined && usage.estimated_savings_usd > 0 && (
              <span className="text-[10px] text-emerald-400/80">
                (已省 ${usage.estimated_savings_usd.toFixed(4)})
              </span>
            )}
          </button>
        ) : isApiKey ? (
          <button
            type="button"
            onClick={() => {
              setIsExpanded(!isExpanded);
              onOpenDetails?.();
            }}
            aria-label="API key delegation badge"
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400 hover:bg-amber-500/20 transition cursor-pointer"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
            <span className="font-semibold">API 计费</span>
            <span className="px-1.5 py-0.2 rounded bg-amber-950/60 text-[10px] text-amber-300 font-bold border border-amber-800/60">
              ${usage.cost_usd !== undefined ? usage.cost_usd.toFixed(4) : '0.00'}
            </span>
            <span className="text-[10px] text-amber-400/80">
              {usage.total_tokens.toLocaleString()} tokens
            </span>
          </button>
        ) : (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 text-xs">
            {usage.total_tokens.toLocaleString()} tokens
          </span>
        )}

        {/* Source backend label */}
        {usage.source && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-400">
            {sourceName}
          </span>
        )}
      </div>

      {/* Expanded detailed breakdown card */}
      {isExpanded && !compact && (
        <div className="mt-2 p-3 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-300 shadow-xl space-y-1.5 max-w-sm">
          <div className="flex justify-between items-center text-[11px] border-b border-zinc-800/80 pb-1">
            <span className="text-zinc-400 font-medium">计费口径判定</span>
            <span className={isSubscription ? 'text-emerald-400 font-bold' : 'text-amber-400 font-bold'}>
              {isSubscription ? '个人订阅专属额度 (无 API 账单)' : '团队 API 计费密钥 (扣减余额)'}
            </span>
          </div>
          <div className="flex justify-between text-[11px]">
            <span className="text-zinc-500">外部代理源:</span>
            <span className="text-white font-mono">{usage.source || '未知'}</span>
          </div>
          <div className="flex justify-between text-[11px]">
            <span className="text-zinc-500">Prompt / Completion:</span>
            <span className="text-zinc-300">
              {usage.prompt_tokens.toLocaleString()} / {usage.completion_tokens.toLocaleString()}
            </span>
          </div>
          {isSubscription && usage.estimated_savings_usd !== undefined && (
            <div className="flex justify-between text-[11px] text-emerald-400 pt-1 border-t border-zinc-800/60">
              <span>预估等效节省:</span>
              <span className="font-bold">${usage.estimated_savings_usd.toFixed(4)}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
