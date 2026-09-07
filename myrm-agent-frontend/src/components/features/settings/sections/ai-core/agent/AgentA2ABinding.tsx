'use client';

import { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Globe, Plus, X, ExternalLink, ShieldCheck } from 'lucide-react';
import Link from 'next/link';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Switch } from '@/components/primitives/switch';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { listA2APeers, type A2APeer } from '@/services/a2aPeer';

interface AgentA2ABindingProps {
  a2aEnabled: boolean;
  onA2AEnabledChange: (enabled: boolean) => void;
  selectedPeerIds: string[];
  onSelectedPeerIdsChange: (ids: string[]) => void;
  readonly?: boolean;
}

export function AgentA2ABinding({
  a2aEnabled,
  onA2AEnabledChange,
  selectedPeerIds,
  onSelectedPeerIdsChange,
  readonly = false,
}: AgentA2ABindingProps) {
  const t = useTranslations('agent');
  const [peers, setPeers] = useState<A2APeer[]>([]);
  const [popoverOpen, setPopoverOpen] = useState(false);

  useEffect(() => {
    listA2APeers(true)
      .then((data) => setPeers(Array.isArray(data) ? data : []))
      .catch(() => setPeers([]));
  }, []);

  const availablePeers = peers.filter((p) => !selectedPeerIds.includes(p.id));
  const selectedPeers = selectedPeerIds
    .map((id) => peers.find((p) => p.id === id))
    .filter(Boolean) as A2APeer[];

  const handleAdd = (peerId: string) => {
    onSelectedPeerIdsChange([...selectedPeerIds, peerId]);
    setPopoverOpen(false);
  };

  const handleRemove = (peerId: string) => {
    onSelectedPeerIdsChange(selectedPeerIds.filter((id) => id !== peerId));
  };

  return (
    <div className="rounded-xl border border-border bg-card p-4 transition-all">
      <div className="flex items-center justify-between gap-3 mb-2">
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
            <Globe className="w-4 h-4 text-indigo-500" />
            {t('a2aBinding')}
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">{t('a2aBindingDesc')}</p>
        </div>
        <Switch
          checked={a2aEnabled}
          disabled={readonly}
          onCheckedChange={onA2AEnabledChange}
          aria-label={t('a2aEnableSwitch')}
        />
      </div>

      {a2aEnabled && (
        <div className="mt-4 pt-3 border-t border-border/60 animate-in fade-in-50">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-foreground flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
              {t('a2aTrustedPeers')}
            </span>
            <Link
              href="/settings/a2aPeers"
              className="text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
            >
              {t('manageA2APeersLink')}
              <ExternalLink className="w-3 h-3" />
            </Link>
          </div>

          <div className="flex flex-wrap items-center gap-2 min-h-8">
            {selectedPeers.map((peer) => (
              <span
                key={peer.id}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border/80 bg-muted/60 px-2.5 py-1 text-xs text-foreground"
              >
                <Globe className="w-3 h-3 text-indigo-500 shrink-0" />
                <span className="font-medium max-w-[140px] truncate">{peer.name}</span>
                {!readonly && (
                  <button
                    type="button"
                    onClick={() => handleRemove(peer.id)}
                    className="ml-0.5 rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                    aria-label={`Remove ${peer.name}`}
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </span>
            ))}

            {!readonly && (
              <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
                <PopoverTrigger asChild>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs gap-1 border-dashed"
                    disabled={availablePeers.length === 0}
                  >
                    <Plus className="w-3 h-3" />
                    {t('addA2APeer')}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-64 p-1.5" align="start">
                  <div className="max-h-56 overflow-y-auto space-y-1">
                    {availablePeers.map((peer) => (
                      <button
                        key={peer.id}
                        type="button"
                        onClick={() => handleAdd(peer.id)}
                        className="w-full flex flex-col text-left px-2.5 py-1.5 rounded-md hover:bg-accent hover:text-accent-foreground text-xs transition-colors"
                      >
                        <span className="font-medium text-foreground truncate">{peer.name}</span>
                        <span className="text-[10px] text-muted-foreground font-mono truncate">{peer.base_url}</span>
                      </button>
                    ))}
                  </div>
                </PopoverContent>
              </Popover>
            )}
          </div>

          {selectedPeers.length === 0 && (
            <p className="text-[11px] text-muted-foreground italic mt-1.5">{t('noA2APeers')}</p>
          )}
        </div>
      )}
    </div>
  );
}
