'use client';

import { memo, useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { useSearchParams } from 'next/navigation';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/primitives/tabs';
import { Terminal, FlaskConical, BarChart3, PawPrint, Download } from 'lucide-react';
import { defaultSubTabResolver, useSettingsSubTabUrl } from '@/hooks/useSettingsSubTabUrl';
import DeveloperSection from './DeveloperSection';
import ExperimentalFeaturesSection from './ExperimentalFeaturesSection';
import UsageStatisticsSection from './UsageStatisticsSection';
import CompanionSection from './CompanionSection';
import ImportExportSection from './ImportExportSection';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';

const DeveloperCenterSection = memo(() => {
  const t = useTranslations('settings');
  const searchParams = useSearchParams();
  const { handleTabChange: syncTabChange } = useSettingsSubTabUrl('developer');
  const isCompanionEnabled = useFeatureGateStore((s) => s.isEnabled('companion_mode'));

  const [activeTab, setActiveTab] = useState<string>('devtools');

  useEffect(() => {
    const sub = searchParams.get('sub');
    if (sub === 'experimental' || sub === 'experimentalFeatures') {
      setActiveTab('experimental');
    } else if (sub === 'usage' || sub === 'usageStatistics') {
      setActiveTab('usage');
    } else if (sub === 'companion') {
      setActiveTab('companion');
    } else if (sub === 'importExport') {
      setActiveTab('importexport');
    } else {
      setActiveTab('devtools');
    }
  }, [searchParams]);

  const handleTabChange = (value: string) => {
    syncTabChange(value, setActiveTab, defaultSubTabResolver('devtools'));
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">{t('menu.developer')}</h1>
        <p className="text-sm text-muted-foreground">
          {activeTab === 'devtools'
            ? '配置系统调试模式与智能体评估诊断设置 / Technical diagnostics and LLM benchmarks'
            : activeTab === 'experimental'
              ? '启用或关闭正在开发测试中的前沿前瞻功能 / Enable preview capabilities and labs flags'
              : activeTab === 'usage'
                ? '追踪详细的模型调用次数、用量分布、费用占比与运行账本 / View detailed usage and billing metrics'
                : activeTab === 'companion'
                  ? '设置萌宠桌面伙伴的互动偏好、语音响应与行为习惯 / Adjust desktop mascot interactions'
                  : '导入或导出全局应用配置，方便跨设备轻松同步 / Backup and restore full app configs'}
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        <TabsList className="flex flex-wrap h-auto w-full bg-secondary/50 backdrop-blur-sm p-1 rounded-xl border border-border/40 mb-6 gap-1">
          <TabsTrigger
            value="devtools"
            className="flex flex-1 items-center justify-center gap-1.5 sm:gap-2 py-2 px-3 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <Terminal className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.developer')}</span>
          </TabsTrigger>
          <TabsTrigger
            value="experimental"
            className="flex flex-1 items-center justify-center gap-1.5 sm:gap-2 py-2 px-3 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <FlaskConical className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.experimentalFeatures')}</span>
          </TabsTrigger>
          <TabsTrigger
            value="usage"
            className="flex flex-1 items-center justify-center gap-1.5 sm:gap-2 py-2 px-3 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <BarChart3 className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.usageStatistics')}</span>
          </TabsTrigger>
          {isCompanionEnabled && (
            <TabsTrigger
              value="companion"
              className="flex flex-1 items-center justify-center gap-1.5 sm:gap-2 py-2 px-3 min-w-0 text-sm font-medium rounded-lg transition-all"
            >
              <PawPrint className="h-4 w-4 shrink-0" />
              <span className="truncate">{t('menu.companion')}</span>
            </TabsTrigger>
          )}
          <TabsTrigger
            value="importexport"
            className="flex flex-1 items-center justify-center gap-1.5 sm:gap-2 py-2 px-3 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <Download className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.importExport')}</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="devtools" className="focus-visible:outline-none focus-visible:ring-0">
          <DeveloperSection />
        </TabsContent>
        <TabsContent value="experimental" className="focus-visible:outline-none focus-visible:ring-0">
          <ExperimentalFeaturesSection />
        </TabsContent>
        <TabsContent value="usage" className="focus-visible:outline-none focus-visible:ring-0">
          <UsageStatisticsSection />
        </TabsContent>
        {isCompanionEnabled && (
          <TabsContent value="companion" className="focus-visible:outline-none focus-visible:ring-0">
            <CompanionSection />
          </TabsContent>
        )}
        <TabsContent value="importexport" className="focus-visible:outline-none focus-visible:ring-0">
          <ImportExportSection />
        </TabsContent>
      </Tabs>
    </div>
  );
});

DeveloperCenterSection.displayName = 'DeveloperCenterSection';

export default DeveloperCenterSection;
