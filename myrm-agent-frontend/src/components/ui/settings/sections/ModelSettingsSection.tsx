'use client';

import { memo, useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { useSearchParams } from 'next/navigation';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { IconCpu, IconSliders } from '@/components/ui/icons/PremiumIcons';
import { useSettingsSubTabUrl } from '@/hooks/useSettingsSubTabUrl';
import ModelServiceSection from './ModelServiceSection';
import DefaultModelSection from './DefaultModelSection';

const ModelSettingsSection = memo(() => {
  const t = useTranslations('settings');
  const searchParams = useSearchParams();
  const { handleTabChange: syncTabChange } = useSettingsSubTabUrl('models');

  // URL query parameter 'sub' determines the active sub-tab
  const [activeTab, setActiveTab] = useState<string>('providers');

  useEffect(() => {
    const sub = searchParams.get('sub');
    if (sub === 'default' || sub === 'defaultModel') {
      setActiveTab('default');
    } else {
      setActiveTab('providers');
    }
  }, [searchParams]);

  const handleTabChange = (value: string) => {
    syncTabChange(value, setActiveTab, (tabValue) => (tabValue === 'default' ? 'default' : null));
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">{t('menu.models')}</h1>
        <p className="text-sm text-muted-foreground">
          {activeTab === 'providers'
            ? '配置 AI 模型提供商与 API 秘钥 / Configure AI Providers and API credentials'
            : '设定默认与降级模型、路由策略及第三方模型设置 / Define default, routing, and fallback models'}
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        <TabsList className="grid w-full max-w-md grid-cols-2 h-auto min-h-10 bg-secondary/50 backdrop-blur-sm p-1 rounded-xl border border-border/40 mb-6">
          <TabsTrigger
            value="providers"
            className="flex items-center justify-center gap-2 py-2 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <IconSliders className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.models')}</span>
          </TabsTrigger>
          <TabsTrigger
            value="default"
            className="flex items-center justify-center gap-2 py-2 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <IconCpu className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.defaultModel')}</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="providers" className="focus-visible:outline-none focus-visible:ring-0">
          <ModelServiceSection />
        </TabsContent>
        <TabsContent value="default" className="focus-visible:outline-none focus-visible:ring-0">
          <DefaultModelSection />
        </TabsContent>
      </Tabs>
    </div>
  );
});

ModelSettingsSection.displayName = 'ModelSettingsSection';

export default ModelSettingsSection;
