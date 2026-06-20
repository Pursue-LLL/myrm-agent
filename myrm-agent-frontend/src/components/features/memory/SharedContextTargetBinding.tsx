'use client';

/**
 * [INPUT]
 * @/services/memorySharedContexts (POS: Frontend Shared Context API client)
 *
 * [OUTPUT]
 * SharedContextTargetBinding: Reusable runtime-target Shared Context binding UI.
 *
 * [POS]
 * Shared Context runtime binding component. It lets settings pages inspect, bind, and unbind
 * inherited Shared Contexts for a single agent, channel, cron job, conversation, or task target.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';

import { toast } from '@/hooks/useToast';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { IconArrowRight, IconAuto, IconBrain, IconLoader, IconX } from '@/components/features/icons/PremiumIcons';
import {
  createSharedContextBinding,
  deleteSharedContextBinding,
  listSharedContextBindingsForTarget,
  listSharedContexts,
  type SharedContext,
  type SharedContextBinding,
  type SharedContextTargetType,
} from '@/services/memorySharedContexts';

interface SharedContextTargetBindingProps {
  targetType: SharedContextTargetType;
  targetId: string | null;
  targetLabel?: string;
  disabled?: boolean;
  disabledMessage?: string;
  compact?: boolean;
  className?: string;
}

interface BoundContextView {
  binding: SharedContextBinding;
  context: SharedContext | null;
}

export function SharedContextTargetBinding({
  targetType,
  targetId,
  targetLabel,
  disabled = false,
  disabledMessage,
  compact = false,
  className,
}: SharedContextTargetBindingProps) {
  const t = useTranslations('sharedContextTargetBinding');
  const resolvedTargetLabel = targetLabel ?? t(`targets.${targetType}`);
  const [contexts, setContexts] = useState<SharedContext[]>([]);
  const [bindings, setBindings] = useState<SharedContextBinding[]>([]);
  const [selectedContextId, setSelectedContextId] = useState('');
  const [loading, setLoading] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);

  const unavailable = disabled || !targetId;
  const unavailableMessage = disabledMessage ?? t('noTarget', { target: resolvedTargetLabel });

  const contextById = useMemo(() => new Map(contexts.map((context) => [context.id, context])), [contexts]);
  const boundContextIds = useMemo(() => new Set(bindings.map((binding) => binding.context_id)), [bindings]);
  const availableContexts = useMemo(
    () => contexts.filter((context) => context.status === 'active' && !boundContextIds.has(context.id)),
    [boundContextIds, contexts],
  );
  const boundContexts = useMemo<BoundContextView[]>(
    () =>
      bindings.map((binding) => ({
        binding,
        context: contextById.get(binding.context_id) ?? null,
      })),
    [bindings, contextById],
  );

  const loadBindings = useCallback(async () => {
    if (!targetId || disabled) {
      setContexts([]);
      setBindings([]);
      setSelectedContextId('');
      return;
    }

    setLoading(true);
    try {
      const [contextResponse, bindingResponse] = await Promise.all([
        listSharedContexts(),
        listSharedContextBindingsForTarget(targetType, targetId),
      ]);
      setContexts(contextResponse.items);
      setBindings(bindingResponse.items);
    } catch (error) {
      toast({
        title: t('errors.load'),
        description: error instanceof Error ? error.message : undefined,
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }, [disabled, targetId, targetType, t]);

  useEffect(() => {
    void loadBindings();
  }, [loadBindings]);

  useEffect(() => {
    if (selectedContextId && availableContexts.some((context) => context.id === selectedContextId)) {
      return;
    }
    setSelectedContextId(availableContexts[0]?.id ?? '');
  }, [availableContexts, selectedContextId]);

  const handleBind = useCallback(async () => {
    if (!targetId || !selectedContextId || disabled) return;

    setActionId('bind');
    try {
      const binding = await createSharedContextBinding(selectedContextId, {
        target_type: targetType,
        target_id: targetId,
      });
      setBindings((items) => [binding, ...items.filter((item) => item.id !== binding.id)]);
      toast({ title: t('toasts.bound') });
    } catch (error) {
      toast({
        title: t('errors.bind'),
        description: error instanceof Error ? error.message : undefined,
        variant: 'destructive',
      });
    } finally {
      setActionId(null);
    }
  }, [disabled, selectedContextId, targetId, targetType, t]);

  const handleUnbind = useCallback(
    async (binding: SharedContextBinding) => {
      setActionId(binding.id);
      try {
        await deleteSharedContextBinding(binding.context_id, binding.id);
        setBindings((items) => items.filter((item) => item.id !== binding.id));
        toast({ title: t('toasts.unbound') });
      } catch (error) {
        toast({
          title: t('errors.unbind'),
          description: error instanceof Error ? error.message : undefined,
          variant: 'destructive',
        });
      } finally {
        setActionId(null);
      }
    },
    [t],
  );

  return (
    <section
      className={cn(
        'rounded-xl border border-border bg-card p-4',
        compact && 'rounded-lg border-border/60 bg-muted/20 p-3',
        className,
      )}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex gap-3">
          <div className="mt-0.5 rounded-lg bg-primary/10 p-2 text-primary">
            <IconBrain className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-foreground">{t('title')}</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">{t('description', { target: resolvedTargetLabel })}</p>
          </div>
        </div>
        {!unavailable && (
          <button
            type="button"
            onClick={loadBindings}
            disabled={loading}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-border/70 px-3 py-2 text-xs text-muted-foreground transition hover:bg-accent disabled:opacity-50"
          >
            {loading ? <IconLoader className="h-3.5 w-3.5 animate-spin" /> : <IconAuto className="h-3.5 w-3.5" />}
            {t('refresh')}
          </button>
        )}
      </div>

      {unavailable ? (
        <div className="mt-4 rounded-lg border border-dashed border-border/70 px-3 py-3 text-sm text-muted-foreground">
          {unavailableMessage}
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
            <select
              value={selectedContextId}
              onChange={(event) => setSelectedContextId(event.target.value)}
              disabled={loading || availableContexts.length === 0}
              className="rounded-lg border border-border/60 bg-background px-3 py-2 text-sm"
            >
              {availableContexts.length === 0 ? (
                <option value="">{t('noAvailable')}</option>
              ) : (
                availableContexts.map((context) => (
                  <option key={context.id} value={context.id}>
                    {context.name}
                  </option>
                ))
              )}
            </select>
            <Button
              type="button"
              onClick={handleBind}
              disabled={!selectedContextId || actionId === 'bind'}
              className="gap-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90"
            >
              {actionId === 'bind' ? (
                <IconLoader className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <IconArrowRight className="h-3.5 w-3.5" />
              )}
              {t('bind')}
            </Button>
          </div>

          <div className="space-y-2">
            {boundContexts.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border/70 px-3 py-3 text-sm text-muted-foreground">
                {t('empty', { target: resolvedTargetLabel })}
              </p>
            ) : (
              boundContexts.map(({ binding, context }) => (
                <div
                  key={binding.id}
                  className="flex flex-col gap-2 rounded-lg border border-border/60 bg-background/60 px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-sm font-medium text-foreground">
                        {context?.name ?? binding.context_id}
                      </span>
                      <span
                        className={cn(
                          'rounded-full px-2 py-0.5 text-[11px] font-medium',
                          context?.status === 'active'
                            ? 'bg-emerald-500/10 text-emerald-600'
                            : 'bg-muted text-muted-foreground',
                        )}
                      >
                        {context?.status === 'active' ? t('active') : t('inactive')}
                      </span>
                    </div>
                    <p className="mt-1 truncate text-xs text-muted-foreground">
                      {context?.description || context?.namespace || t('missingContext')}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleUnbind(binding)}
                    disabled={actionId === binding.id}
                    className="inline-flex items-center justify-center gap-1.5 rounded-full px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
                  >
                    {actionId === binding.id ? (
                      <IconLoader className="h-3 w-3 animate-spin" />
                    ) : (
                      <IconX className="h-3 w-3" />
                    )}
                    {t('unbind')}
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </section>
  );
}
