'use client';

/**
 * [INPUT]
 * - @/store/useChatStore (POS: chat session state)
 * - @/services/chat::revokeSessionAccessRoot (POS: revoke persisted directory grant)
 * - @/lib/directoryBrowseRecent::shortenHomePath (POS: display path shortening)
 *
 * [OUTPUT]
 * - SessionAccessRootsBar: chips for active session directory grants + revoke
 *
 * [POS]
 * Web Chat visibility layer for session_access_roots; shown only when grants exist.
 */

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { FolderOpen, X } from 'lucide-react';
import { toast } from 'sonner';

import { revokeSessionAccessRoot } from '@/services/chat';
import { shortenHomePath } from '@/lib/directoryBrowseRecent';
import useChatStore from '@/store/useChatStore';
import type { SessionAccessRoot } from '@/store/chat/types/sessionAccess';

function accessBadgeClass(writable: boolean): string {
  return writable
    ? 'border-amber-500/30 bg-amber-500/10 text-amber-800 dark:text-amber-200'
    : 'border-sky-500/30 bg-sky-500/10 text-sky-800 dark:text-sky-200';
}

export default function SessionAccessRootsBar() {
  const t = useTranslations('chat.sessionAccessRoots');
  const chatId = useChatStore((state) => state.chatId);
  const roots = useChatStore((state) => state.sessionAccessRoots);
  const setSessionAccessRoots = useChatStore((state) => state.setSessionAccessRoots);
  const [revokingPath, setRevokingPath] = useState<string | null>(null);

  const handleRevoke = useCallback(
    async (root: SessionAccessRoot) => {
      if (!chatId || revokingPath) {return;}
      setRevokingPath(root.path);
      try {
        const result = await revokeSessionAccessRoot(chatId, root.path);
        setSessionAccessRoots(result.session_access_roots);
      } catch (error) {
        console.error('Failed to revoke session directory access:', error);
        toast.error(t('revokeFailed'));
      } finally {
        setRevokingPath(null);
      }
    },
    [chatId, revokingPath, setSessionAccessRoots, t],
  );

  if (!roots.length) {
    return null;
  }

  return (
    <div
      className="mb-2 flex flex-wrap items-center gap-1.5 rounded-xl border border-border/60 bg-muted/20 px-2 py-1.5 sm:px-2.5"
      data-testid="session-access-roots-bar"
    >
      <span className="mr-0.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {t('label')}
      </span>
      {roots.map((root) => {
        const busy = revokingPath === root.path;
        return (
          <span
            key={root.path}
            className="inline-flex max-w-full items-center gap-1 rounded-lg border border-border/50 bg-background/80 py-0.5 pl-1.5 pr-0.5 text-xs"
          >
            <FolderOpen className="h-3 w-3 shrink-0 text-primary/70" />
            <span className="truncate" title={root.path}>
              {shortenHomePath(root.path)}
            </span>
            <span
              className={`shrink-0 rounded px-1 py-0.5 text-[10px] font-medium ${accessBadgeClass(root.writable)}`}
            >
              {root.writable ? t('writable') : t('readOnly')}
            </span>
            <button
              type="button"
              disabled={busy}
              onClick={() => void handleRevoke(root)}
              className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
              title={t('revoke')}
              aria-label={t('revoke')}
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        );
      })}
    </div>
  );
}
