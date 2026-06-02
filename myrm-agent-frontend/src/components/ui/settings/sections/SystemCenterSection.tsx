'use client';

import { memo, useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { useSearchParams } from 'next/navigation';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Settings, Info } from 'lucide-react';
import { defaultSubTabResolver, useSettingsSubTabUrl } from '@/hooks/useSettingsSubTabUrl';
import SystemSection from './SystemSection';
import AboutSection from './AboutSection';

const SystemCenterSection = memo(() => {
  const t = useTranslations('settings');
  const searchParams = useSearchParams();
  const { handleTabChange: syncTabChange } = useSettingsSubTabUrl('system');

  const [activeTab, setActiveTab] = useState<string>('settings');

  useEffect(() => {
    const sub = searchParams.get('sub');
    if (sub === 'about') {
      setActiveTab('about');
    } else {
      setActiveTab('settings');
    }
  }, [searchParams]);

  const handleTabChange = (value: string) => {
    syncTabChange(value, setActiveTab, defaultSubTabResolver('settings'));
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">{t('menu.system')}</h1>
        <p className="text-sm text-muted-foreground">
          {activeTab === 'settings'
            ? '管理本地端口、远程服务访问及系统进程状态 / Manage ports, network access, and system runtime'
            : '查看当前系统版本、开发团队信息及应用更新日志 / Inspect system version, changelogs, and team details'}
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        <TabsList className="grid w-full max-w-md grid-cols-2 bg-secondary/50 backdrop-blur-sm p-1 rounded-xl border border-border/40 mb-6">
          <TabsTrigger
            value="settings"
            className="flex items-center justify-center gap-1.5 sm:gap-2 py-2 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <Settings className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.system')}</span>
          </TabsTrigger>
          <TabsTrigger
            value="about"
            className="flex items-center justify-center gap-1.5 sm:gap-2 py-2 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <IconInfo className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.about')}</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="settings" className="focus-visible:outline-none focus-visible:ring-0">
          <SystemSection />
        </TabsContent>
        <TabsContent value="about" className="focus-visible:outline-none focus-visible:ring-0">
          <AboutSection />
        </TabsContent>
      </Tabs>
    </div>
  );
});

// Helper wrapper for the Info icon since Lucide's Info is sometimes styled as IconInfo in pre-existing packages, but let's use Lucide Info icon
const IconInfo = (props: any) => <Info {...props} />;

SystemCenterSection.displayName = 'SystemCenterSection';

export default SystemCenterSection;
