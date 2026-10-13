'use client';

import { memo, useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { useSearchParams } from 'next/navigation';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/primitives/tabs';
import { Activity, ShieldCheck } from 'lucide-react';
import { defaultSubTabResolver, useSettingsSubTabUrl } from '@/hooks/settings/useSettingsSubTabUrl';
import SkillQualitySection from './SkillQualitySection';
import ToolStabilitySection from './ToolStabilitySection';

const ToolQualitySection = memo(() => {
  const t = useTranslations('settings');
  const tDescription = useTranslations('settings.toolQualityCenter.tabDescriptions');
  const searchParams = useSearchParams();
  const { handleTabChange: syncTabChange } = useSettingsSubTabUrl('toolQuality');

  const [activeTab, setActiveTab] = useState<string>('quality');

  useEffect(() => {
    const sub = searchParams.get('sub');
    if (sub === 'stability' || sub === 'toolStability') {
      setActiveTab('stability');
    } else {
      setActiveTab('quality');
    }
  }, [searchParams]);

  const handleTabChange = (value: string) => {
    syncTabChange(value, setActiveTab, defaultSubTabResolver('quality'));
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">{t('menu.toolQuality')}</h1>
        <p className="text-sm text-muted-foreground">
          {tDescription(activeTab === 'stability' ? 'stability' : 'quality')}
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        <TabsList className="grid w-full max-w-md grid-cols-2 bg-secondary/50 backdrop-blur-sm p-1 rounded-xl border border-border/40 mb-6">
          <TabsTrigger
            value="quality"
            className="flex items-center justify-center gap-1.5 sm:gap-2 py-2 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <ShieldCheck className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.skillQuality')}</span>
          </TabsTrigger>
          <TabsTrigger
            value="stability"
            className="flex items-center justify-center gap-1.5 sm:gap-2 py-2 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <Activity className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.toolStability')}</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="quality">
          <SkillQualitySection />
        </TabsContent>
        <TabsContent value="stability">
          <ToolStabilitySection />
        </TabsContent>
      </Tabs>
    </div>
  );
});

ToolQualitySection.displayName = 'ToolQualitySection';

export default ToolQualitySection;
