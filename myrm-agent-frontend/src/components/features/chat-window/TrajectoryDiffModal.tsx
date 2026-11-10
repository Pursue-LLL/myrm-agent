/**
 * [INPUT]
 * ./useTrajectoryDiff::useTrajectoryDiff (POS: trajectories, session choices and the divergence)
 * ./TrajectoryColumn::TrajectoryColumn (POS: one side of the comparison)
 *
 * [OUTPUT]
 * TrajectoryDiffModal: the current session's tool-call trajectory beside another session's, the first difference marked
 *
 * [POS]
 * Opened from ReplayAction.
 */

'use client';

import { AlertTriangle, GitCompare } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/primitives/dialog';

import { TrajectoryColumn } from './TrajectoryColumn';
import { useTrajectoryDiff } from './useTrajectoryDiff';

interface TrajectoryDiffModalProps {
  open: boolean;
  currentSessionId: string;
  onClose: () => void;
}

const shortId = (id: string) => id.slice(0, 8);

export default function TrajectoryDiffModal({ open, currentSessionId, onClose }: TrajectoryDiffModalProps) {
  const t = useTranslations('trajectoryDiff');
  const { current, compared, comparedSessionId, setComparedSessionId, sessions, divergenceIndex } = useTrajectoryDiff(
    open,
    currentSessionId,
  );

  const currentTitle = (current.status === 'ready' && current.data.title) || shortId(currentSessionId);
  const comparedTitle = comparedSessionId
    ? (compared.status === 'ready' && compared.data.title) || shortId(comparedSessionId)
    : t('none');

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent aria-describedby={undefined} className="max-w-6xl max-h-[85vh] flex flex-col p-6 overflow-hidden">
        <DialogHeader className="pb-4 border-b border-border">
          <DialogTitle className="flex items-center gap-2 text-base font-semibold">
            <GitCompare className="w-5 h-5 text-primary" />
            {t('title')}
          </DialogTitle>
        </DialogHeader>

        <div className="flex items-center justify-between gap-2 py-2 border-b border-border/60 text-xs">
          <div className="flex items-center gap-2">
            <label htmlFor="trajectory-compare-with" className="text-muted-foreground">
              {t('compareWith')}:
            </label>
            <select
              id="trajectory-compare-with"
              value={comparedSessionId}
              onChange={(e) => setComparedSessionId(e.target.value)}
              className="px-2 py-1 bg-background border border-border rounded text-xs outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="">{t('selectSessionPlaceholder')}</option>
              {sessions.status === 'ready' &&
                sessions.data.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title || shortId(item.id)} ({new Date(item.createdAt).toLocaleDateString()})
                  </option>
                ))}
            </select>
            {sessions.status === 'error' && (
              <span role="alert" className="text-destructive-text">
                {t('sessionListFailed')}
              </span>
            )}
          </div>

          {divergenceIndex !== null && (
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400 font-mono text-xs">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>{t('divergenceDetected', { step: divergenceIndex + 1 })}</span>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto grid grid-cols-1 md:grid-cols-2 gap-4 py-4">
          <TrajectoryColumn
            heading={t('sessionA', { title: currentTitle })}
            state={current}
            divergenceIndex={divergenceIndex}
            className="border-r border-border/50 pr-2"
          />
          <TrajectoryColumn
            heading={t('sessionB', { title: comparedTitle })}
            state={compared}
            divergenceIndex={divergenceIndex}
            placeholder={t('noSessionSelected')}
            className="pl-2"
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
