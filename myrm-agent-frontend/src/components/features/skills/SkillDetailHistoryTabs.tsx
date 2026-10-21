'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/primitives/tabs';
import { getSkillAgentUsage } from '@/services/skill/core';
import { SkillPackageRevisionsPanel } from './SkillPackageRevisionsPanel';
import { SkillVersionsPanel } from './SkillVersionsPanel';

interface SkillDetailHistoryTabsProps {
  skillId: string;
  onContentChanged: () => void;
}

export function SkillDetailHistoryTabs({ skillId, onContentChanged }: SkillDetailHistoryTabsProps) {
  const t = useTranslations('settings.skills.detail.history');
  const [agentCount, setAgentCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    void getSkillAgentUsage(skillId)
      .then((usage) => {
        if (!cancelled) {
          setAgentCount(usage.agent_count);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAgentCount(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [skillId]);

  return (
    <Tabs defaultValue="overview" className="w-full">
      <TabsList className="grid w-full grid-cols-3 h-auto">
        <TabsTrigger value="overview" className="text-xs sm:text-sm">
          {t('tabOverview')}
        </TabsTrigger>
        <TabsTrigger value="skill-md" className="text-xs sm:text-sm">
          {t('tabSkillMd')}
        </TabsTrigger>
        <TabsTrigger value="resources" className="text-xs sm:text-sm">
          {t('tabResources')}
        </TabsTrigger>
      </TabsList>
      <TabsContent value="overview" className="mt-4 space-y-4">
        <p className="text-xs leading-relaxed text-muted-foreground rounded-lg border border-border/60 bg-muted/30 px-3 py-2">
          {t('rollbackGuide')}
        </p>
        {agentCount !== null && (
          <p className="text-xs text-muted-foreground">
            {agentCount > 0 ? t('agentUsage', { count: agentCount }) : t('agentUsageNone')}
          </p>
        )}
      </TabsContent>
      <TabsContent value="skill-md" className="mt-4">
        <SkillVersionsPanel skillId={skillId} onActivated={onContentChanged} />
      </TabsContent>
      <TabsContent value="resources" className="mt-4">
        <SkillPackageRevisionsPanel skillId={skillId} onRestored={onContentChanged} />
      </TabsContent>
    </Tabs>
  );
}
