'use client';

/**
 * [INPUT]
 * @/services/skillMigration (POS: migration pending review client)
 *
 * [OUTPUT]
 * MigrationPendingReviewSection: list and approve/reject staged competitor migrations
 *
 * [POS]
 * Memory Center migration tab — closes the skills review loop after wizard submit.
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Check, Loader2, RefreshCw, X } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import {
  approvePendingMigration,
  listPendingMigrations,
  rejectPendingMigration,
  type PendingMigrationItem,
} from '@/services/skillMigration';
import useSkillStore from '@/store/skill/useSkillStore';
import useAgentStore from '@/store/useAgentStore';
import { getCompetitorDisplayName } from '@/services/migrationDiscovery';

interface MigrationPendingReviewSectionProps {
  refreshToken?: number;
}

const MigrationPendingReviewSection = memo(({ refreshToken = 0 }: MigrationPendingReviewSectionProps) => {
  const t = useTranslations('memory.pendingReview');
  const [items, setItems] = useState<PendingMigrationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [actingId, setActingId] = useState<string | null>(null);
  const fetchLocalSkills = useSkillStore((state) => state.fetchLocalSkills);
  const fetchUserSkillConfig = useSkillStore((state) => state.fetchUserSkillConfig);
  const agents = useAgentStore((state) => state.agents);

  const resolveAgentLabel = useCallback(
    (item: PendingMigrationItem): string | null => {
      if (item.target_agent_name?.trim()) {
        return item.target_agent_name.trim();
      }
      const agentId = item.target_agent_id?.trim();
      if (!agentId) {
        return null;
      }
      const matched = agents.find((agent) => agent.id === agentId);
      return matched?.name?.trim() || agentId;
    },
    [agents],
  );

  const loadPending = useCallback(async () => {
    setLoading(true);
    try {
      const result = await listPendingMigrations();
      setItems(result.items.filter((item) => item.status === 'pending'));
    } catch {
      toast.error(t('loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  const fetchAgents = useAgentStore((state) => state.fetchAgents);

  useEffect(() => {
    void loadPending();
    void fetchAgents(1, 50, true);
  }, [loadPending, refreshToken, fetchAgents]);

  const handleApprove = useCallback(
    async (id: string) => {
      setActingId(id);
      try {
        await approvePendingMigration(id);
        await Promise.all([fetchLocalSkills(), fetchUserSkillConfig(true)]);
        toast.success(t('approveSuccess'));
        await loadPending();
      } catch {
        toast.error(t('approveFailed'));
      } finally {
        setActingId(null);
      }
    },
    [fetchLocalSkills, fetchUserSkillConfig, loadPending, t],
  );

  const handleReject = useCallback(
    async (id: string) => {
      setActingId(id);
      try {
        await rejectPendingMigration(id);
        toast.success(t('rejectSuccess'));
        await loadPending();
      } catch {
        toast.error(t('rejectFailed'));
      } finally {
        setActingId(null);
      }
    },
    [loadPending, t],
  );

  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-border/50 bg-secondary/20 px-4 py-3 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t('loading')}
      </div>
    );
  }

  if (items.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3 rounded-xl border border-amber-500/25 bg-amber-500/5 p-4 sm:p-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-sm font-semibold">{t('title')}</h3>
          <p className="text-xs text-muted-foreground">{t('description')}</p>
        </div>
        <Button size="sm" variant="outline" className="h-8 shrink-0 text-xs" onClick={() => void loadPending()}>
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          {t('refresh')}
        </Button>
      </div>

      <div className="space-y-2">
        {items.map((item) => {
          const isActing = actingId === item.id;
          const skillCount = item.item_counts.skills ?? item.total_items;
          const bindAgentLabel = resolveAgentLabel(item);
          return (
            <div
              key={item.id}
              className="flex flex-col gap-3 rounded-lg border border-border/50 bg-card p-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">{getCompetitorDisplayName(item.source)}</span>
                  <Badge variant="secondary" className="text-[10px]">
                    {item.migration_type}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground line-clamp-2">{item.summary}</p>
                <p className="text-[11px] text-muted-foreground/70">{t('skillCount', { count: skillCount })}</p>
                {bindAgentLabel && (
                  <p className="text-[11px] text-amber-700/90 dark:text-amber-400/90">
                    {t('bindTargetAgent', { name: bindAgentLabel })}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 text-xs"
                  disabled={isActing}
                  onClick={() => void handleReject(item.id)}
                >
                  {isActing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <X className="mr-1 h-3.5 w-3.5" />}
                  {t('reject')}
                </Button>
                <Button
                  size="sm"
                  className="h-8 text-xs"
                  disabled={isActing}
                  onClick={() => void handleApprove(item.id)}
                >
                  {isActing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="mr-1 h-3.5 w-3.5" />}
                  {t('approve')}
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
});

MigrationPendingReviewSection.displayName = 'MigrationPendingReviewSection';
export default MigrationPendingReviewSection;
