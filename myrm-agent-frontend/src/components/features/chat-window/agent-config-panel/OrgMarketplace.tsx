'use client';

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { isSandbox } from '@/lib/deploy-mode';
import { getMyOrg } from '@/services/enterprise-org';
import {
  forcePushUpdate,
  importMarketplaceAgent,
  installFromMarketplace,
  listMarketplaceEntries,
  type ForcePushResult,
  type MarketplaceEntry,
} from '@/services/marketplace';
import { cn } from '@/lib/utils/classnameUtils';
import { Bot, Download, Loader2, Search, Store, CheckCircle, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { resolveLucideIcon } from '@/components/agent/agent-icons';

interface OrgMarketplaceProps {
  className?: string;
  onInstalled?: (agentId: string) => void;
}

const renderAvatar = (avatar: string | null | undefined) => {
  if (avatar?.startsWith('lucide:')) {
    const IconComponent = resolveLucideIcon(avatar.slice(7));
    if (IconComponent) return <IconComponent size={16} />;
  }
  return <Bot size={16} />;
};

const OrgMarketplace = ({ className, onInstalled }: OrgMarketplaceProps) => {
  const t = useTranslations('agent.configPanel');
  const router = useRouter();
  const [entries, setEntries] = useState<MarketplaceEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [installingId, setInstallingId] = useState<string | null>(null);
  const [pushingId, setPushingId] = useState<string | null>(null);
  const [orgId, setOrgId] = useState<string | null>(null);

  useEffect(() => {
    if (!isSandbox()) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    const load = async () => {
      try {
        const org = await getMyOrg();
        if (cancelled) return;
        setOrgId(org.id);
        const data = await listMarketplaceEntries(org.id);
        if (!cancelled) setEntries(data);
      } catch {
        // Marketplace is optional; silently hide when CP unavailable
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, []);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleSearch = useCallback((query: string) => {
    setSearch(query);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      if (!orgId) return;
      setLoading(true);
      try {
        const data = await listMarketplaceEntries(orgId, { search: query || undefined });
        setEntries(data);
      } catch {
        // silent
      } finally {
        setLoading(false);
      }
    }, 300);
  }, [orgId]);

  const handleInstall = useCallback(async (entry: MarketplaceEntry) => {
    if (installingId) return;
    setInstallingId(entry.id);
    try {
      const result = await installFromMarketplace(entry.id);
      const agent = await importMarketplaceAgent(result.profile_data);
      toast.success(t('installSuccess') || `Installed "${entry.name}"`);
      if (onInstalled) {
        onInstalled(agent.id);
      } else {
        router.push(`/?agent_id=${agent.id}`);
      }
      setEntries(prev => prev.map(e =>
        e.id === entry.id
          ? { ...e, install_count: e.install_count + 1, is_installed: true }
          : e
      ));
    } catch (e) {
      console.error(e);
      toast.error(t('installError') || 'Failed to install agent');
    } finally {
      setInstallingId(null);
    }
  }, [installingId, onInstalled, router, t]);

  const handleForcePush = useCallback(async (entry: MarketplaceEntry) => {
    if (pushingId) return;

    const confirmed = window.confirm(
      t('forcePushConfirm') ||
      `Force-push "${entry.name}" v${entry.latest_version} to all installed users? This will overwrite their current configuration (a snapshot will be saved for rollback).`,
    );
    if (!confirmed) return;

    setPushingId(entry.id);
    try {
      const result: ForcePushResult = await forcePushUpdate(entry.id);
      toast.success(
        t('forcePushSuccess') || 'Force push completed',
        {
          description: `v${result.version} → ${result.synced} synced, ${result.buffered} buffered, ${result.failed} failed (${result.total} total)`,
          duration: 8_000,
        },
      );
    } catch (e) {
      console.error(e);
      toast.error(t('forcePushError') || 'Force push failed');
    } finally {
      setPushingId(null);
    }
  }, [pushingId, t]);

  if (!isSandbox()) return null;
  if (loading && entries.length === 0) {
    return (
      <div className={cn('flex justify-center p-4', className)}>
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (entries.length === 0 && !search) return null;

  return (
    <div className={cn('space-y-3 pt-2', className)}>
      <div className="flex items-center gap-2 px-1">
        <div className="flex-1 h-px bg-border/50" />
        <Store size={12} className="text-muted-foreground" />
        <span className="text-xs text-muted-foreground">
          {t('orgMarketplace') || 'Org Marketplace'}
        </span>
        <div className="flex-1 h-px bg-border/50" />
      </div>

      {entries.length > 3 && (
        <div className="relative px-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder={t('searchMarketplace') || 'Search agents...'}
            className={cn(
              'w-full pl-8 pr-3 py-1.5 text-xs rounded-lg',
              'bg-muted/30 border border-border/40',
              'focus:outline-none focus:ring-1 focus:ring-primary/30',
              'placeholder:text-muted-foreground/60'
            )}
          />
        </div>
      )}

      {search && entries.length === 0 && !loading && (
        <p className="text-center text-xs text-muted-foreground py-3">
          {t('noResults') || 'No agents found'}
        </p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {entries.map(entry => (
          <div
            key={entry.id}
            className={cn(
              'relative flex flex-col gap-2 p-3 rounded-xl',
              'border border-border/40 bg-card/40 backdrop-blur-sm',
              'hover:border-primary/30 hover:bg-primary/5 transition-all',
              'group cursor-pointer',
              entry.is_installed && 'border-green-500/20 bg-green-500/5'
            )}
            onClick={() => !entry.is_installed && handleInstall(entry)}
          >
            <div className="flex items-center gap-2">
              <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary/10 text-primary shrink-0">
                {renderAvatar(entry.avatar)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-foreground truncate">{entry.name}</div>
                {entry.description && (
                  <div className="text-xs text-muted-foreground truncate">{entry.description}</div>
                )}
              </div>
              <div className="shrink-0 flex items-center justify-center w-6 h-6 rounded-md bg-background border border-border/50 opacity-0 group-hover:opacity-100 transition-opacity">
                {installingId === entry.id ? (
                  <Loader2 size={12} className="animate-spin text-primary" />
                ) : entry.is_installed ? (
                  <CheckCircle size={12} className="text-green-500" />
                ) : (
                  <Download size={12} className="text-primary" />
                )}
              </div>
            </div>
            <div className="flex items-center gap-2 text-[10px] text-muted-foreground/70">
              <span>v{entry.latest_version}</span>
              <span>·</span>
              <span>{entry.install_count} {t('installs') || 'installs'}</span>
              {entry.is_installed && (
                <>
                  <span>·</span>
                  <span className="text-green-600 font-medium">
                    {t('installed') || 'Installed'}
                  </span>
                </>
              )}
              {entry.install_count > 0 && (
                <button
                  onClick={(e) => { e.stopPropagation(); handleForcePush(entry); }}
                  disabled={!!pushingId}
                  className={cn(
                    'ml-auto flex items-center gap-1 px-1.5 py-0.5 rounded',
                    'text-[10px] font-medium transition-colors',
                    'text-amber-600 dark:text-amber-400 hover:bg-amber-500/10',
                    'disabled:opacity-50 disabled:cursor-not-allowed',
                  )}
                  title={t('forcePushTooltip') || 'Force-push latest version to all installed users'}
                >
                  {pushingId === entry.id ? (
                    <Loader2 size={10} className="animate-spin" />
                  ) : (
                    <RefreshCw size={10} />
                  )}
                  {t('forcePush') || 'Push'}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default memo(OrgMarketplace);
