'use client';

import { memo, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { getMemoryContext } from '@/services/memory';
import { IconLoader } from '@/components/features/icons/PremiumIcons';
import { Brain, User } from 'lucide-react';

const MemoryContextPanel = memo(() => {
  const t = useTranslations('memory');
  const [loading, setLoading] = useState(true);
  const [contextData, setContextData] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    let mounted = true;
    const loadData = async () => {
      try {
        setLoading(true);
        const data = await getMemoryContext();
        if (mounted) {
          setContextData(data);
        }
      } catch (error) {
        console.error('Failed to load memory context:', error);
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };
    loadData();
    return () => {
      mounted = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="flex min-h-[300px] flex-col items-center justify-center gap-3 rounded-xl border border-border/40 bg-accent/20">
        <IconLoader className="h-6 w-6 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">{t('loading') || 'Loading...'}</p>
      </div>
    );
  }

  const globalProfile = (contextData?.global_profile as Record<string, string>) || {};
  const peerProfile = (contextData?.peer_profile as Record<string, string>) || {};

  const globalProfileEntries = Object.entries(globalProfile);
  const peerProfileEntries = Object.entries(peerProfile);

  return (
    <div className="space-y-6">
      <div className="grid gap-6 md:grid-cols-2">
        {/* Global Profile Card */}
        <div className="flex flex-col overflow-hidden rounded-xl border border-border/60 bg-background/60 shadow-sm">
          <div className="flex items-center gap-3 border-b border-border/40 bg-accent/30 px-4 py-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <User className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">Global User Profile</h3>
              <p className="text-xs text-muted-foreground">Cross-agent stable identity</p>
            </div>
          </div>
          <div className="flex-1 p-4">
            {globalProfileEntries.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                No global profile data yet.
              </div>
            ) : (
              <div className="space-y-3">
                {globalProfileEntries.map(([key, value]) => (
                  <div key={key} className="flex flex-col gap-1 rounded-lg border border-border/40 bg-accent/20 p-3">
                    <span className="text-xs font-medium text-muted-foreground uppercase">{key}</span>
                    <span className="text-sm text-foreground">{value}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Peer Profile Card */}
        <div className="flex flex-col overflow-hidden rounded-xl border border-border/60 bg-background/60 shadow-sm">
          <div className="flex items-center gap-3 border-b border-border/40 bg-accent/30 px-4 py-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Brain className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">Our Relationship & Your Persona</h3>
              <p className="text-xs text-muted-foreground">Agent-specific interactions</p>
            </div>
          </div>
          <div className="flex-1 p-4">
            {peerProfileEntries.length === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                No agent-specific profile data yet.
              </div>
            ) : (
              <div className="space-y-3">
                {peerProfileEntries.map(([key, value]) => (
                  <div key={key} className="flex flex-col gap-1 rounded-lg border border-border/40 bg-accent/20 p-3">
                    <span className="text-xs font-medium text-muted-foreground uppercase">{key}</span>
                    <span className="text-sm text-foreground">{value}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
});

MemoryContextPanel.displayName = 'MemoryContextPanel';

export default MemoryContextPanel;
