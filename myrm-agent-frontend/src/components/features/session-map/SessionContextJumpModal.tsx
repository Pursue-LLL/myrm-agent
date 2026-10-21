'use client';

/**
 * [INPUT]
 * - SessionNode, ProjectCluster from @/services/sessionMap
 * - Translation strings from 'sessionMap' namespace
 * - onJumpIn callback to transition UI into the target chat session
 *
 * [OUTPUT]
 * - SessionContextJumpModal: Instant context replay modal showing session status, task details, and jump-in action
 *
 * [POS]
 * Context inspection and instant jump-back modal for Project-Centric Session Map.
 * Strict typing: Zero `any`. File length < 260 lines. Accessible <dialog> structure.
 */

import { useId } from 'react';
import { useTranslations } from 'next-intl';
import { IconX, IconSparkles, IconFolder, IconActivity, IconCheck } from '@/components/features/icons/PremiumIcons';
import { parseServerTimestamp } from '@/lib/utils/timeUtils';
import type { SessionNode, ProjectCluster } from '@/services/sessionMap';

export interface SessionContextJumpModalProps {
  isOpen: boolean;
  onClose: () => void;
  session: SessionNode | null;
  project: ProjectCluster | null;
  onJumpIn: (sessionId: string) => void;
}

export function SessionContextJumpModal({ isOpen, onClose, session, project, onJumpIn }: SessionContextJumpModalProps) {
  const t = useTranslations('sessionMap');
  const titleId = useId();
  const descId = useId();

  if (!isOpen || !session) {
    return null;
  }

  const handleJumpIn = () => {
    onJumpIn(session.id);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <dialog
        open
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="w-full max-w-lg rounded-2xl bg-card border border-border shadow-2xl p-6 text-foreground flex flex-col gap-4 m-0"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border/60 pb-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center font-bold">
              <IconActivity className="w-4 h-4" />
            </div>
            <div>
              <h2 id={titleId} className="text-base font-semibold">
                {session.title}
              </h2>
              <p id={descId} className="text-xs text-muted-foreground">
                {t('sessionModalSubtitle')}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            aria-label={t('closeAriaLabel')}
          >
            <IconX className="w-5 h-5" />
          </button>
        </div>

        {/* Project & Working Directory Context Banner */}
        <div className="rounded-xl bg-muted/40 p-3 text-xs flex flex-col gap-2 border border-border/40 font-mono">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-foreground font-semibold">
              <IconFolder className="w-3.5 h-3.5 text-primary shrink-0" />
              <span>{project?.name || 'Default Project'}</span>
            </div>
            <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded bg-background border border-border/40">
              {session.state}
            </span>
          </div>

          {(session.workspace_dir || project?.workspace_path) && (
            <div
              className="truncate text-muted-foreground text-[11px]"
              title={session.workspace_dir || project?.workspace_path}
            >
              Path: {session.workspace_dir || project?.workspace_path}
            </div>
          )}

          <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-1 border-t border-border/30">
            <span>
              Agent: <strong className="text-foreground">{session.agent_name}</strong>
            </span>
            <span>
              Tokens: <strong className="text-foreground">{session.tokens_used.toLocaleString()}</strong>
            </span>
          </div>
        </div>

        {/* Active Task Objective */}
        {session.current_task && (
          <div className="flex flex-col gap-1 text-xs">
            <span className="font-semibold text-muted-foreground">{t('activeTaskLabel')}:</span>
            <div className="p-3 rounded-xl bg-background border border-border/80 text-foreground font-mono text-[11px] leading-relaxed">
              {session.current_task}
            </div>
          </div>
        )}

        {/* Tags */}
        {session.tags && session.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {session.tags.map((tag) => (
              <span
                key={tag}
                className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-muted text-muted-foreground border border-border/40"
              >
                #{tag}
              </span>
            ))}
          </div>
        )}

        {/* Last Active Timestamp */}
        <div className="text-[11px] text-muted-foreground">
          {t('lastActiveLabel')}: {parseServerTimestamp(session.last_active_at).toLocaleString()}
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/60">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg text-xs text-muted-foreground hover:bg-muted transition-colors"
          >
            {t('cancelAction')}
          </button>

          <button
            type="button"
            onClick={handleJumpIn}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors shadow-sm"
          >
            <IconCheck className="w-3.5 h-3.5" />
            <span>{t('jumpInAction')}</span>
          </button>
        </div>
      </dialog>
    </div>
  );
}
