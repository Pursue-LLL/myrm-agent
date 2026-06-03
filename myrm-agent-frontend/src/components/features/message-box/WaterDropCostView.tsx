'use client';

import React from 'react';
import { TokenUsage, TokenEconomicsSnapshot } from '@/store/chat/types';
import { useTranslations } from 'next-intl';
import { isLocalMode } from '@/lib/deploy-mode';
import useConfigStore from '@/store/useConfigStore';

const PremiumWaterDropIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" />
    <path d="M12 11.5a2.5 2.5 0 0 0-2.5 2.5" />
    <path
      d="M12 22a8 8 0 0 0 8-8c0-3.3-2.6-6-4.5-8l-3.5-3.5-3.5 3.5c-1.9 2-4.5 4.7-4.5 8a8 8 0 0 0 8 8z"
      fill="currentColor"
      fillOpacity="0.1"
    />
  </svg>
);

interface WaterDropCostViewProps {
  usage?: TokenUsage;
  tokenEconomics?: TokenEconomicsSnapshot;
  costUsd?: number;
  isStreaming?: boolean;
}

export default function WaterDropCostView({ usage, tokenEconomics, isStreaming }: WaterDropCostViewProps) {
  const t = useTranslations('chat.tokenUsage.waterDrop');
  const enableCostEstimation = useConfigStore((state) => state.enableCostEstimation);

  if (!isLocalMode() || !enableCostEstimation || !usage || !usage.cached_tokens || usage.prompt_tokens === 0) {
    return null;
  }

  const cacheSavingsPercent = Math.round((usage.cached_tokens / usage.prompt_tokens) * 100);

  // If savings are tiny, don't show the massive banner
  if (cacheSavingsPercent < 5) {
    return null;
  }

  const savedUsd = tokenEconomics?.total_cache_savings_usd || 0;
  const newTokens = usage.prompt_tokens - usage.cached_tokens;
  const callCount = tokenEconomics?.call_count || 1;

  return (
    <div
      className={`overflow-hidden mt-4 mb-2 rounded-2xl border border-blue-200/50 dark:border-blue-900/30 bg-gradient-to-br from-blue-50/80 to-indigo-50/50 dark:from-blue-950/30 dark:to-indigo-950/20 p-4 transition-all duration-700 ease-out origin-top ${isStreaming ? 'opacity-0 scale-y-95 pointer-events-none absolute w-full' : 'relative opacity-100 scale-y-100'}`}
    >
      {/* 动态水滴波浪背景 */}
      <div className="absolute top-0 right-0 w-48 h-48 opacity-[0.08] dark:opacity-[0.05] pointer-events-none transform translate-x-10 -translate-y-12">
        <svg
          viewBox="0 0 200 200"
          xmlns="http://www.w3.org/2000/svg"
          className="w-full h-full animate-[spin_8s_linear_infinite]"
        >
          <path
            fill="#3b82f6"
            d="M44.7,-76.4C58.8,-69.2,71.8,-59.1,79.6,-45.8C87.4,-32.6,90,-16.3,89.1,-0.5C88.1,15.3,83.5,30.6,74.2,43.2C64.9,55.8,50.9,65.6,35.9,72.7C20.8,79.8,4.7,84.1,-10.8,81.1C-26.2,78.2,-41,68,-53.4,55.5C-65.7,43,-75.8,28.2,-81.4,-22.6,-81.3,-37.7C-74.6,-52.8,-60.1,-65,-45,-71.9C-29.8,-78.8,-14.9,-80.4,0.3,-81C15.6,-81.6,30.7,-83.6,44.7,-76.4Z"
            transform="translate(100 100)"
          />
        </svg>
      </div>

      <div className="relative z-10 flex items-start gap-4">
        <div className="flex-shrink-0 flex items-center justify-center w-10 h-10 rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-500 dark:text-blue-400">
          <PremiumWaterDropIcon className="w-5 h-5" />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h4 className="text-sm font-semibold text-blue-800 dark:text-blue-300 flex items-center gap-2">
              {cacheSavingsPercent}% {t('cacheHit')}
            </h4>
            {callCount > 1 && (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-100/50 dark:bg-amber-900/30 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-400 border border-amber-200/50 dark:border-amber-800/30">
                <svg
                  width="10"
                  height="10"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                </svg>
                {callCount} {t('calls', { defaultMessage: 'Calls' })}
              </span>
            )}
          </div>
          <p className="text-xs text-blue-600/80 dark:text-blue-400/80 mt-1">
            {t('newTokens')} <span className="font-mono font-medium">{newTokens.toLocaleString()}</span>{' '}
            {t('newTokensSuffix')}
            {savedUsd > 0 && (
              <>
                {' '}
                {t('saved')}{' '}
                <span className="font-mono font-bold text-emerald-600 dark:text-emerald-400">
                  ${savedUsd.toFixed(4)}
                </span>{' '}
                {t('savedSuffix')}
              </>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}
