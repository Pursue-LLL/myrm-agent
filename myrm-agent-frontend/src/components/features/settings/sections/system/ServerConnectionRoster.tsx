'use client';

/**
 * [INPUT]
 * - @/lib/remote-profiles::RemoteConnectionProfile
 * - next-intl (settings.system.serverConnection)
 *
 * [OUTPUT]
 * - ServerConnectionRoster: remote connection profile list with test / switch / remove actions
 *
 * [POS]
 * Presentational roster of ServerConnectionCard; all state and side effects stay in the parent.
 */

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import type { RemoteConnectionProfile } from '@/lib/remote-profiles';
import { cn } from '@/lib/utils/classnameUtils';

interface ServerConnectionRosterProps {
  profiles: RemoteConnectionProfile[];
  activeId: string | null;
  testingId: string | null;
  switchingKey: string | null;
  onTest: (profile: RemoteConnectionProfile) => void;
  onSelect: (id: string) => void;
  onRemove: (id: string) => void;
}

const ServerConnectionRoster = memo<ServerConnectionRosterProps>(
  ({ profiles, activeId, testingId, switchingKey, onTest, onSelect, onRemove }) => {
    const t = useTranslations('settings.system.serverConnection');

    return (
      <div className="space-y-2">
        {profiles.map((p) => (
          <div
            key={p.id}
            className={cn(
              'flex flex-col gap-2 rounded-2xl border p-3 sm:flex-row sm:items-center',
              p.id === activeId ? 'border-indigo-500/50 bg-indigo-500/5' : 'border-white/10',
            )}
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-bold text-foreground">{p.name}</p>
              <p className="truncate text-xs text-muted-foreground">{p.url}</p>
            </div>
            <div className="flex gap-2">
              {p.kind !== 'cloud' && (
                <button
                  type="button"
                  onClick={() => onTest(p)}
                  disabled={testingId === p.id}
                  className="px-3 py-1.5 rounded-lg border border-white/10 text-xs font-bold hover:bg-white/5 disabled:opacity-50 transition-colors"
                >
                  {testingId === p.id ? t('testing') : t('testConnection')}
                </button>
              )}
              {p.id !== activeId && (
                <button
                  type="button"
                  onClick={() => onSelect(p.id)}
                  disabled={switchingKey === p.id}
                  className="px-3 py-1.5 rounded-lg bg-indigo-500 text-white text-xs font-bold hover:bg-indigo-600 disabled:opacity-50 transition-colors"
                >
                  {switchingKey === p.id ? t('testing') : t('save')}
                </button>
              )}
              <button
                type="button"
                onClick={() => onRemove(p.id)}
                className="px-3 py-1.5 rounded-lg border border-white/10 text-xs font-bold text-muted-foreground hover:bg-white/5 transition-colors"
              >
                {t('remove')}
              </button>
            </div>
          </div>
        ))}
      </div>
    );
  },
);

ServerConnectionRoster.displayName = 'ServerConnectionRoster';

export default ServerConnectionRoster;
