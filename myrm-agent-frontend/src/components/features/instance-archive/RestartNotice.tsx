'use client';

/**
 * [INPUT]
 * - @/lib/instance-archive/restart: planRestart, performRestart
 * - @/lib/api: ApiError (409 = the sandbox refuses while tasks are still running)
 * - next-intl::useTranslations('instanceArchive.restart')
 *
 * [OUTPUT]
 * - RestartNotice: "restart to finish" banner with a restart action where one exists
 *
 * [POS]
 * Shown whenever a restore / import / rollback is queued; the swap itself happens while the
 * backend boots.
 */

import { memo, useCallback, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { CircleNotch, Power } from '@phosphor-icons/react';
import { Button } from '@/components/primitives/button';
import { ApiError } from '@/lib/api';
import { performRestart, planRestart } from '@/lib/instance-archive/restart';
import type { RestartMode } from '@/services/instanceArchive';

const HTTP_CONFLICT = 409;

interface RestartNoticeProps {
  mode: RestartMode;
}

type RestartState = 'idle' | 'restarting' | 'busy' | 'failed';

export const RestartNotice = memo(function RestartNotice({ mode }: RestartNoticeProps) {
  const t = useTranslations('instanceArchive.restart');
  const plan = useMemo(() => planRestart(mode), [mode]);
  const [state, setState] = useState<RestartState>('idle');

  const restart = useCallback(async () => {
    if (plan === 'manual') {
      return;
    }
    setState('restarting');
    try {
      await performRestart(plan);
    } catch (error) {
      // 409: a restart now would kill tasks that are still running, so the sandbox refuses.
      setState(error instanceof ApiError && error.code === HTTP_CONFLICT ? 'busy' : 'failed');
    }
  }, [plan]);

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-primary/30 bg-primary/5 p-4 sm:flex-row sm:items-center sm:justify-between">
      <output className="flex items-start gap-3">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
          <Power className="h-4 w-4" weight="bold" />
        </span>
        <span className="block space-y-0.5">
          <span className="block text-sm font-semibold text-foreground">{t('title')}</span>
          <span className="block text-xs leading-relaxed text-muted-foreground">
            {state === 'busy' || state === 'failed' ? t(state) : t(plan)}
          </span>
        </span>
      </output>
      {plan !== 'manual' && (
        <Button size="sm" onClick={restart} disabled={state === 'restarting'} className="shrink-0 gap-1.5 rounded-xl">
          {state === 'restarting' && <CircleNotch className="h-3.5 w-3.5 animate-spin" />}
          {state === 'restarting' ? t('restarting') : t('now')}
        </Button>
      )}
    </div>
  );
});
