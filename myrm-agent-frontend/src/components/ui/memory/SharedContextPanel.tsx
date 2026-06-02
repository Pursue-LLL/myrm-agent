'use client';

/**
 * [INPUT]
 * ./useSharedContextPanel::useSharedContextPanel (POS: Shared Context panel state and operation orchestration hook)
 * @/services/memorySharedContexts::SharedContextTargetType (POS: Frontend Shared Context API client)
 *
 * [OUTPUT]
 * SharedContextPanel: Memory Center Shared Context management panel.
 *
 * [POS]
 * Shared Context management UI. It lets users create contexts, manage bindings, review proposals,
 * promote history evidence, inspect archived read-only contexts, and configure governance policies
 * (correction auto-propagation and goal-completion auto-archive).
 */

import { memo } from 'react';
import { useTranslations } from 'next-intl';

import { cn } from '@/lib/utils/classnameUtils';
import {
  IconArrowRight,
  IconAuto,
  IconCheck,
  IconExplore,
  IconFolder,
  IconLoader,
  IconGlow,
  IconX,
} from '@/components/ui/icons/PremiumIcons';
import type { SharedContextMemoryType, SharedContextTargetType } from '@/services/memorySharedContexts';
import {
  formatSharedContextDate,
  SHARED_CONTEXT_MEMORY_TYPES,
  TARGET_TYPES,
  useSharedContextPanel,
} from './useSharedContextPanel';
import { SharedContextMemoryHealthBanner } from './SharedContextMemoryHealthBanner';

type PolicyToggleRowProps = {
  title: string;
  hint: string;
  enabled: boolean;
  disabled: boolean;
  onToggle: () => void;
};

function PolicyToggleRow({ title, hint, enabled, disabled, onToggle }: PolicyToggleRowProps) {
  return (
    <div className="mt-3 flex items-center justify-between gap-3 rounded-lg border border-border/40 bg-accent/20 px-4 py-3">
      <div className="min-w-0 flex-1">
        <span className="text-sm font-medium text-foreground">{title}</span>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>
      <button
        type="button"
        onClick={onToggle}
        disabled={disabled}
        aria-checked={enabled}
        role="switch"
        className={cn(
          'relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors disabled:cursor-not-allowed disabled:opacity-50',
          enabled ? 'bg-accent-warm' : 'bg-muted',
        )}
      >
        <span
          className={cn(
            'pointer-events-none block h-4 w-4 rounded-full bg-background shadow-lg ring-0 transition-transform',
            enabled ? 'translate-x-5' : 'translate-x-0.5',
          )}
        />
      </button>
    </div>
  );
}

const SharedContextPanel = memo(() => {
  const t = useTranslations('memory.sharedContexts');
  const tMemory = useTranslations('memory');
  const panel = useSharedContextPanel();

  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-border/60 bg-gradient-to-br from-card via-card to-accent/20 p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
          <div className="flex-1">
            <h3 className="text-base font-semibold text-foreground">{t('title')}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{t('description')}</p>
          </div>
          <button
            onClick={panel.refreshSelected}
            disabled={panel.loading || panel.detailsLoading}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-border/60 px-3 py-2 text-sm text-muted-foreground transition hover:bg-accent disabled:opacity-50"
          >
            {(panel.loading || panel.detailsLoading) && <IconLoader className="h-3.5 w-3.5 animate-spin" />}
            {t('refresh')}
          </button>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-[1fr_1.3fr_auto]">
          <input
            value={panel.newName}
            onChange={(event) => panel.setNewName(event.target.value)}
            placeholder={t('create.namePlaceholder')}
            className="rounded-lg border border-border/60 bg-background px-3 py-2 text-sm outline-none focus:border-primary/50"
          />
          <input
            value={panel.newDescription}
            onChange={(event) => panel.setNewDescription(event.target.value)}
            placeholder={t('create.descriptionPlaceholder')}
            className="rounded-lg border border-border/60 bg-background px-3 py-2 text-sm outline-none focus:border-primary/50"
          />
          <button
            onClick={panel.handleCreateContext}
            disabled={!panel.newName.trim() || panel.actionId === 'create-context'}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
          >
            {panel.actionId === 'create-context' ? (
              <IconLoader className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <IconArrowRight className="h-3.5 w-3.5" />
            )}
            {t('create.submit')}
          </button>
        </div>
      </div>

      <SharedContextMemoryHealthBanner />

      <div className="grid gap-5 xl:grid-cols-[320px_1fr]">
        <div className="space-y-3">
          {panel.contexts.length === 0 && !panel.loading ? (
            <div className="rounded-xl border border-dashed border-border/70 p-6 text-center text-sm text-muted-foreground">
              {t('empty')}
            </div>
          ) : (
            panel.contexts.map((context) => (
              <button
                key={context.id}
                onClick={() => panel.setSelectedContextId(context.id)}
                className={cn(
                  'w-full rounded-xl border p-3 text-left transition',
                  panel.selectedContextId === context.id
                    ? 'border-primary/50 bg-primary/10'
                    : 'border-border/60 bg-card hover:bg-accent/40',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-foreground">{context.name}</span>
                  <span
                    className={cn(
                      'rounded-full px-2 py-0.5 text-[11px] font-medium',
                      context.status === 'active'
                        ? 'bg-emerald-500/10 text-emerald-600'
                        : 'bg-muted text-muted-foreground',
                    )}
                  >
                    {t(`status.${context.status}`)}
                  </span>
                </div>
                {context.description && (
                  <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{context.description}</p>
                )}
                <p className="mt-2 text-[11px] text-muted-foreground/70">{context.namespace}</p>
              </button>
            ))
          )}
        </div>

        {panel.selectedContext ? (
          <div className="space-y-5">
            <div className="flex flex-col gap-3 rounded-xl border border-border/60 bg-card p-4 md:flex-row md:items-start md:justify-between">
              <div>
                <h3 className="text-lg font-semibold">{panel.selectedContext.name}</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {panel.selectedContext.description || t('noDescription')}
                </p>
                <p className="mt-2 text-xs text-muted-foreground/70">{panel.selectedContext.namespace}</p>
              </div>
              {panel.selectedContext.status === 'active' && (
                <button
                  onClick={panel.handleArchiveContext}
                  disabled={panel.actionId === `archive-${panel.selectedContext.id}`}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-border/70 px-3 py-2 text-sm text-muted-foreground transition hover:bg-accent disabled:opacity-50"
                >
                  <IconFolder className="h-3.5 w-3.5" />
                  {t('archive')}
                </button>
              )}
            </div>

            {!panel.selectedContextIsActive && (
              <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
                {t('archivedNotice')}
              </div>
            )}

            <section className="rounded-xl border border-border/60 bg-card p-4">
              <h4 className="font-medium">{t('policy.title')}</h4>
              <p className="text-sm text-muted-foreground">{t('policy.description')}</p>
              <PolicyToggleRow
                title={t('policy.correctionAutoApprove')}
                hint={t('policy.correctionAutoApproveHint')}
                enabled={panel.correctionAutoApprove}
                disabled={!panel.selectedContextIsActive || panel.actionId === 'toggle-correction'}
                onToggle={panel.handleToggleCorrectionAutoApprove}
              />
              <PolicyToggleRow
                title={t('policy.goalCompletionAutoApprove')}
                hint={t('policy.goalCompletionAutoApproveHint')}
                enabled={panel.goalCompletionAutoApprove}
                disabled={!panel.selectedContextIsActive || panel.actionId === 'toggle-goal-completion'}
                onToggle={panel.handleToggleGoalCompletionAutoApprove}
              />
            </section>

            <section className="rounded-xl border border-border/60 bg-card p-4">
              <h4 className="font-medium">{t('bindings.title')}</h4>
              <p className="text-sm text-muted-foreground">{t('bindings.description')}</p>
              <div className="mt-3 grid gap-2 md:grid-cols-[160px_1fr_auto]">
                <select
                  value={panel.targetType}
                  disabled={!panel.selectedContextIsActive}
                  onChange={(event) => {
                    panel.setTargetType(event.target.value as SharedContextTargetType);
                    panel.setTargetId('');
                  }}
                  className="rounded-lg border border-border/60 bg-background px-3 py-2 text-sm"
                >
                  {TARGET_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {t(`targetTypes.${type}`)}
                    </option>
                  ))}
                </select>
                {panel.targetOptions.length > 0 ? (
                  <select
                    value={panel.targetId}
                    disabled={!panel.selectedContextIsActive}
                    onChange={(event) => panel.setTargetId(event.target.value)}
                    className="rounded-lg border border-border/60 bg-background px-3 py-2 text-sm"
                  >
                    <option value="">{t('bindings.selectTarget')}</option>
                    {panel.targetOptions.map((option) => (
                      <option key={`${option.type}:${option.id}`} value={option.id}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    value={panel.targetId}
                    disabled={!panel.selectedContextIsActive}
                    onChange={(event) => panel.setTargetId(event.target.value)}
                    placeholder={t('bindings.targetIdPlaceholder')}
                    className="rounded-lg border border-border/60 bg-background px-3 py-2 text-sm outline-none focus:border-primary/50"
                  />
                )}
                <button
                  onClick={panel.handleCreateBinding}
                  disabled={
                    !panel.selectedContextIsActive || !panel.targetId.trim() || panel.actionId === 'create-binding'
                  }
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
                >
                  <IconArrowRight className="h-3.5 w-3.5" />
                  {t('bindings.bind')}
                </button>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {panel.bindings.length === 0 ? (
                  <span className="text-sm text-muted-foreground">{t('bindings.empty')}</span>
                ) : (
                  panel.bindings.map((binding) => (
                    <span
                      key={binding.id}
                      className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-accent/40 px-3 py-1 text-xs"
                    >
                      <span>
                        {t(`targetTypes.${binding.target_type}`)} · {binding.target_id}
                      </span>
                      <button
                        aria-label={t('actions.removeBinding')}
                        onClick={() => panel.handleDeleteBinding(binding)}
                        disabled={panel.actionId === binding.id}
                        className="text-muted-foreground hover:text-destructive disabled:opacity-50"
                      >
                        <IconX className="h-3 w-3" />
                      </button>
                    </span>
                  ))
                )}
              </div>
            </section>

            <section className="rounded-xl border border-border/60 bg-card p-4">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-medium">{t('proposals.title')}</h4>
                  <p className="text-sm text-muted-foreground">
                    {t('proposals.description', { count: panel.pendingProposals.length })}
                  </p>
                </div>
                {panel.detailsLoading && <IconLoader className="h-4 w-4 animate-spin text-muted-foreground" />}
              </div>

              <div className="mt-3 grid gap-2 md:grid-cols-[150px_1fr_auto]">
                <select
                  value={panel.proposalType}
                  disabled={!panel.selectedContextIsActive}
                  onChange={(event) => panel.setProposalType(event.target.value as SharedContextMemoryType)}
                  className="rounded-lg border border-border/60 bg-background px-3 py-2 text-sm"
                >
                  {SHARED_CONTEXT_MEMORY_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {tMemory(`types.${type}`)}
                    </option>
                  ))}
                </select>
                <textarea
                  value={panel.proposalContent}
                  disabled={!panel.selectedContextIsActive}
                  onChange={(event) => panel.setProposalContent(event.target.value)}
                  placeholder={t('proposals.contentPlaceholder')}
                  rows={2}
                  className="rounded-lg border border-border/60 bg-background px-3 py-2 text-sm outline-none focus:border-primary/50"
                />
                <button
                  onClick={panel.handleCreateProposal}
                  disabled={
                    !panel.selectedContextIsActive ||
                    !panel.proposalContent.trim() ||
                    panel.actionId === 'create-proposal'
                  }
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-primary/30 bg-primary/10 px-4 py-2 text-sm font-medium text-primary transition hover:bg-primary/15 disabled:opacity-50"
                >
                  <IconGlow className="h-3.5 w-3.5" />
                  {t('proposals.create')}
                </button>
              </div>

              <div className="mt-4 space-y-3">
                {panel.proposals.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-border/70 p-5 text-center text-sm text-muted-foreground">
                    {t('proposals.empty')}
                  </div>
                ) : (
                  panel.proposals.map((proposal) => {
                    const isEditing = panel.editingProposalId === proposal.id;
                    return (
                      <div key={proposal.id} className="rounded-lg border border-border/60 p-3">
                        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                            <span className="rounded-full bg-accent px-2 py-0.5">
                              {tMemory(`types.${proposal.memory_type}`)}
                            </span>
                            {proposal.source_type === 'correction_propagation' && (
                              <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-amber-600 dark:text-amber-400">
                                {t('proposals.correctionTag')}
                              </span>
                            )}
                            {proposal.source_type === 'goal_completion' && (
                              <span className="rounded-full bg-sky-500/15 px-2 py-0.5 text-sky-600 dark:text-sky-400">
                                {t('proposals.goalCompletionTag')}
                              </span>
                            )}
                            <span>{t(`proposalStatus.${proposal.status}`)}</span>
                            <span>{formatSharedContextDate(proposal.created_at)}</span>
                          </div>
                          {proposal.status === 'pending' && (
                            <div className="flex items-center gap-1">
                              {panel.selectedContextIsActive &&
                                (isEditing ? (
                                  <button
                                    aria-label={t('actions.saveProposal')}
                                    onClick={() => panel.handleSaveProposal(proposal.id)}
                                    disabled={panel.actionId === proposal.id || !panel.editingContent.trim()}
                                    className="rounded-full p-1.5 text-primary hover:bg-primary/10 disabled:opacity-50"
                                  >
                                    <IconCheck className="h-3.5 w-3.5" />
                                  </button>
                                ) : (
                                  <button
                                    onClick={() => {
                                      panel.setEditingProposalId(proposal.id);
                                      panel.setEditingContent(proposal.content);
                                    }}
                                    className="rounded-full px-2 py-1 text-xs text-muted-foreground hover:bg-accent"
                                  >
                                    {tMemory('edit')}
                                  </button>
                                ))}
                              <button
                                aria-label={t('actions.rejectProposal')}
                                onClick={() => panel.handleRejectProposal(proposal.id)}
                                disabled={panel.actionId === proposal.id}
                                className="rounded-full p-1.5 text-destructive hover:bg-destructive/10 disabled:opacity-50"
                              >
                                <IconX className="h-3.5 w-3.5" />
                              </button>
                              <button
                                aria-label={t('actions.approveProposal')}
                                onClick={() => panel.handleApproveProposal(proposal.id)}
                                disabled={!panel.selectedContextIsActive || panel.actionId === proposal.id}
                                className="rounded-full p-1.5 text-emerald-600 hover:bg-emerald-500/10 disabled:opacity-50"
                              >
                                <IconCheck className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          )}
                        </div>
                        {isEditing && panel.selectedContextIsActive ? (
                          <textarea
                            value={panel.editingContent}
                            onChange={(event) => panel.setEditingContent(event.target.value)}
                            rows={3}
                            className="w-full rounded-lg border border-border/60 bg-background px-3 py-2 text-sm outline-none focus:border-primary/50"
                          />
                        ) : (
                          <p className="whitespace-pre-wrap text-sm leading-relaxed">{proposal.content}</p>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </section>

            <section className="rounded-xl border border-border/60 bg-card p-4">
              <h4 className="font-medium">{t('history.title')}</h4>
              <p className="text-sm text-muted-foreground">{t('history.description')}</p>
              <div className="mt-3 grid gap-2 md:grid-cols-[1fr_150px_auto]">
                <input
                  value={panel.historyQuery}
                  onChange={(event) => panel.setHistoryQuery(event.target.value)}
                  placeholder={t('history.searchPlaceholder')}
                  className="rounded-lg border border-border/60 bg-background px-3 py-2 text-sm outline-none focus:border-primary/50"
                />
                <select
                  value={panel.historyType}
                  onChange={(event) => panel.setHistoryType(event.target.value as SharedContextMemoryType)}
                  className="rounded-lg border border-border/60 bg-background px-3 py-2 text-sm"
                >
                  {SHARED_CONTEXT_MEMORY_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {tMemory(`types.${type}`)}
                    </option>
                  ))}
                </select>
                <button
                  onClick={panel.handleSearchHistory}
                  disabled={!panel.historyQuery.trim() || panel.actionId === 'history-search'}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-border/70 px-4 py-2 text-sm transition hover:bg-accent disabled:opacity-50"
                >
                  {panel.actionId === 'history-search' ? (
                    <IconLoader className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <IconExplore className="h-3.5 w-3.5" />
                  )}
                  {t('history.search')}
                </button>
              </div>
              <div className="mt-4 space-y-2">
                {panel.historyHits.map((hit) => (
                  <div key={hit.message_id} className="rounded-lg border border-border/60 p-3">
                    <div className="mb-1 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                      <span className="inline-flex items-center gap-1">
                        <IconAuto className="h-3 w-3" />
                        {hit.chat_title || hit.chat_id} · {hit.role}
                      </span>
                      <span>{formatSharedContextDate(hit.sent_at)}</span>
                    </div>
                    <p className="line-clamp-3 text-sm">{hit.content}</p>
                    <button
                      onClick={() => panel.handlePromoteHistory(hit)}
                      disabled={!panel.selectedContextIsActive || panel.actionId === hit.message_id}
                      className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-1.5 text-xs font-medium text-primary hover:bg-primary/15 disabled:opacity-50"
                    >
                      <IconArrowRight className="h-3 w-3" />
                      {t('history.promote')}
                    </button>
                  </div>
                ))}
              </div>
            </section>
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-border/70 p-8 text-center text-sm text-muted-foreground">
            {t('selectEmpty')}
          </div>
        )}
      </div>
    </div>
  );
});

SharedContextPanel.displayName = 'SharedContextPanel';

export default SharedContextPanel;
