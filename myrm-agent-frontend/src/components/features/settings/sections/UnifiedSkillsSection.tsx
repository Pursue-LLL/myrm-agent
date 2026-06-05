'use client';

import { memo, useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { useSearchParams } from 'next/navigation';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/primitives/tabs';
import { Clock3, ShieldAlert } from 'lucide-react';
import { IconGlow } from '@/components/features/icons/PremiumIcons';
import { defaultSubTabResolver, useSettingsSubTabUrl } from '@/hooks/useSettingsSubTabUrl';
import SkillsSection from './SkillsSection';
import { PendingEvolutionsDashboard } from '@/components/features/skills/PendingEvolutionsDashboard';
import { EvolutionRejectionDashboard } from '@/components/features/skills/EvolutionRejectionDashboard';

const UnifiedSkillsSection = memo(() => {
  const t = useTranslations('settings');
  const searchParams = useSearchParams();
  const { handleTabChange: syncTabChange } = useSettingsSubTabUrl('skills');

  const [activeTab, setActiveTab] = useState<string>('inventory');

  useEffect(() => {
    const sub = searchParams.get('sub');
    if (sub === 'pending' || sub === 'evolutionPending') {
      setActiveTab('pending');
    } else if (sub === 'rejections' || sub === 'evolutionRejection') {
      setActiveTab('rejections');
    } else {
      setActiveTab('inventory');
    }
  }, [searchParams]);

  const handleTabChange = (value: string) => {
    syncTabChange(value, setActiveTab, defaultSubTabResolver('inventory'));
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">{t('menu.skills')}</h1>
        <p className="text-sm text-muted-foreground">
          {activeTab === 'inventory'
            ? '管理和发现智能体的核心技能与方法 / Manage and discover core agent capabilities'
            : activeTab === 'pending'
              ? '审查和批准智能体自动成长并进化出的新技能 / Review and approve self-evolved agent skills'
              : '查看技能成长审计与进化过程中的异常阻断记录 / Inspect growth blockages and audit trails'}
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        <TabsList className="grid w-full max-w-xl grid-cols-3 bg-secondary/50 backdrop-blur-sm p-1 rounded-xl border border-border/40 mb-6">
          <TabsTrigger
            value="inventory"
            className="flex items-center justify-center gap-1.5 sm:gap-2 py-2 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <IconGlow className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.skills')}</span>
          </TabsTrigger>
          <TabsTrigger
            value="pending"
            className="flex items-center justify-center gap-1.5 sm:gap-2 py-2 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <Clock3 className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.evolutionPending')}</span>
          </TabsTrigger>
          <TabsTrigger
            value="rejections"
            className="flex items-center justify-center gap-1.5 sm:gap-2 py-2 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <ShieldAlert className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.evolutionRejection')}</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="inventory" className="focus-visible:outline-none focus-visible:ring-0">
          <SkillsSection />
        </TabsContent>
        <TabsContent value="pending" className="focus-visible:outline-none focus-visible:ring-0">
          <PendingEvolutionsDashboard />
        </TabsContent>
        <TabsContent value="rejections" className="focus-visible:outline-none focus-visible:ring-0">
          <EvolutionRejectionDashboard />
        </TabsContent>
      </Tabs>
    </div>
  );
});

UnifiedSkillsSection.displayName = 'UnifiedSkillsSection';

export default UnifiedSkillsSection;
