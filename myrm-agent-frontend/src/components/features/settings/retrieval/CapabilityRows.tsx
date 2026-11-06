'use client';

import { memo, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { Sorting01Icon } from 'hugeicons-react';
import { IconLoader, IconSearch } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Switch } from '@/components/primitives/switch';
import type { ApplyStatus } from '@/store/useRetrievalStore';
import ApplyOutcome from './ApplyOutcome';

interface CapabilityRowProps {
  icon: ReactNode;
  /** Background class of the icon chip, e.g. `bg-blue-500/10`. */
  tint: string;
  title: string;
  description: string;
  /** Model that setting this capability up applies; omitted once it is set up. */
  presetModel?: string;
  status: ApplyStatus;
  message?: string;
  children: ReactNode;
}

function CapabilityRow({ icon, tint, title, description, presetModel, status, message, children }: CapabilityRowProps) {
  const t = useTranslations('settings.retrieval');

  return (
    <div className="space-y-3 rounded-xl border border-border/50 bg-background/50 p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <div className={`shrink-0 rounded-lg p-2 ${tint}`}>{icon}</div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-foreground">{title}</p>
            <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{description}</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-3">{children}</div>
      </div>
      {presetModel && (
        <p className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
          <span>{t('modelName')}</span>
          <span className="font-mono text-foreground/80">{presetModel}</span>
        </p>
      )}
      <ApplyOutcome status={status} message={message} />
    </div>
  );
}

interface EmbeddingRowProps {
  applied: boolean;
  status: ApplyStatus;
  message?: string;
  presetModel: string;
  onEnable: () => void;
}

/** Semantic search: the store cannot switch an applied embedding model off, so it offers "Enable" only. */
export const EmbeddingRow = memo<EmbeddingRowProps>(({ applied, status, message, presetModel, onEnable }) => {
  const t = useTranslations('settings.retrieval');
  const applying = status === 'applying';

  return (
    <CapabilityRow
      icon={<IconSearch className="h-4 w-4 text-blue-500" />}
      tint="bg-blue-500/10"
      title={t('embedding.title')}
      description={t('embedding.description')}
      presetModel={applied ? undefined : presetModel}
      status={status}
      message={message}
    >
      <span
        className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${
          applied ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'bg-muted text-muted-foreground'
        }`}
      >
        {applied ? t('embedding.enabled') : t('embedding.notEnabled')}
      </span>
      {!applied && (
        <Button type="button" size="sm" onClick={onEnable} disabled={applying}>
          {applying && <IconLoader className="mr-2 h-3 w-3 animate-spin" />}
          {t('embedding.enable')}
        </Button>
      )}
    </CapabilityRow>
  );
});

EmbeddingRow.displayName = 'EmbeddingRow';

interface RerankRowProps {
  /** The reranker is set up (switch-independent). */
  applied: boolean;
  checked: boolean;
  status: ApplyStatus;
  message?: string;
  presetModel: string;
  onChange: (checked: boolean) => void;
}

/** Reranking: the switch the chat request and the IM channels read; turning it on sets the reranker up first. */
export const RerankRow = memo<RerankRowProps>(({ applied, checked, status, message, presetModel, onChange }) => {
  const t = useTranslations('settings.retrieval');
  const applying = status === 'applying';

  return (
    <CapabilityRow
      icon={<Sorting01Icon size={16} className="text-purple-500" />}
      tint="bg-purple-500/10"
      title={t('rerank.title')}
      description={t('rerank.description')}
      presetModel={applied ? undefined : presetModel}
      status={status}
      message={message}
    >
      {applying && <IconLoader className="h-4 w-4 animate-spin text-muted-foreground" />}
      <Switch checked={checked} onCheckedChange={onChange} disabled={applying} aria-label={t('rerank.title')} />
    </CapabilityRow>
  );
});

RerankRow.displayName = 'RerankRow';
