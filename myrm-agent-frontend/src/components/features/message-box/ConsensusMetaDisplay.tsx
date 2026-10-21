'use client';

import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';

interface ConsensusMeta {
  models_used: number;
  models_succeeded: number;
  aggregator_model: string;
  elapsed_seconds: number;
}

interface ConsensusMetaDisplayProps {
  meta: ConsensusMeta;
}

const NetworkIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <circle cx="12" cy="5" r="2" />
    <circle cx="5" cy="19" r="2" />
    <circle cx="19" cy="19" r="2" />
    <path d="M12 7v4" />
    <path d="M7 17l3.5-5" />
    <path d="M17 17l-3.5-5" />
    <circle cx="12" cy="12" r="1" />
  </svg>
);

export default function ConsensusMetaDisplay({ meta }: ConsensusMetaDisplayProps) {
  const t = useTranslations('messageBox');
  const elapsed = meta.elapsed_seconds.toFixed(1);
  const shortModel = meta.aggregator_model.includes('/')
    ? meta.aggregator_model.split('/').pop()
    : meta.aggregator_model;

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[11px] text-muted-foreground hover:text-foreground transition-colors duration-200 rounded-md hover:bg-light-secondary dark:hover:bg-dark-secondary cursor-default tabular-nums"
          >
            <NetworkIcon className="w-3 h-3" />
            <span>
              {meta.models_succeeded}/{meta.models_used}
            </span>
            <span className="opacity-40">·</span>
            <span>{shortModel}</span>
            <span className="opacity-40">·</span>
            <span>{elapsed}s</span>
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs text-xs space-y-1">
          <p className="font-medium">{t('consensusMetaTitle')}</p>
          <p>
            {t('consensusMetaModels', {
              succeeded: meta.models_succeeded,
              total: meta.models_used,
            })}
          </p>
          <p>{t('consensusMetaAggregator', { model: meta.aggregator_model })}</p>
          <p>{t('consensusMetaElapsed', { seconds: elapsed })}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
