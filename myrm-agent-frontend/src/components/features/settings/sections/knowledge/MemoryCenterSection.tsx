'use client';

import { memo, useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { useSearchParams } from 'next/navigation';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/primitives/tabs';
import dynamic from 'next/dynamic';
import { Brain, Archive, Database, Cloud, ArrowRightLeft, MessageCircle } from 'lucide-react';
import { defaultSubTabResolver, useSettingsSubTabUrl } from '@/hooks/useSettingsSubTabUrl';
import { isLocalMode } from '@/lib/deploy-mode';
import MemorySection from './MemorySection';
import MemoryBackupSection from './MemoryBackupSection';
import MemoryArchivalSection from './MemoryArchivalSection';
import RemoteBackupSection from './RemoteBackupSection';
import { SettingsSkeleton } from '../../common/SettingsSkeleton';
import { Button } from '@/components/primitives/button';

const MigrationWizardSection = dynamic(() => import('./MigrationWizardSection'), {
  loading: () => <SettingsSkeleton />,
});

const FollowUpsPanel = dynamic(() => import('../system/CommitmentPanel'), {
  loading: () => <SettingsSkeleton />,
});

const MigrationPendingReviewSection = dynamic(() => import('./MigrationPendingReviewSection'), {
  loading: () => <SettingsSkeleton />,
});

const MemoryCenterSection = memo(() => {
  const t = useTranslations('settings');
  const searchParams = useSearchParams();
  const { handleTabChange: syncTabChange } = useSettingsSubTabUrl('memory');
  const showMigration = isLocalMode();
  const wantsMigrationTab = searchParams.get('sub') === 'migration';
  const migrationUnavailable = wantsMigrationTab && !showMigration;
  const marketingSiteUrl = process.env.NEXT_PUBLIC_MARKETING_SITE_URL ?? 'https://myrm.ai';
  const desktopDownloadHref = `${marketingSiteUrl.replace(/\/+$/, '')}/download`;

  const [activeTab, setActiveTab] = useState<string>('explorer');
  const [pendingReviewRefresh, setPendingReviewRefresh] = useState(0);

  useEffect(() => {
    const sub = searchParams.get('sub');
    if (sub === 'backup' || sub === 'memory-backup') {
      setActiveTab('backup');
    } else if (sub === 'cloud-backup' || sub === 'memory-cloud-backup') {
      setActiveTab('cloud-backup');
    } else if (sub === 'archival' || sub === 'memory-archival') {
      setActiveTab('archival');
    } else if (sub === 'follow-ups' || sub === 'followups') {
      setActiveTab('follow-ups');
    } else if (sub === 'migration') {
      setActiveTab(showMigration ? 'migration' : 'explorer');
    } else {
      setActiveTab('explorer');
    }
  }, [searchParams, showMigration]);

  const handleTabChange = (value: string) => {
    syncTabChange(value, setActiveTab, defaultSubTabResolver('explorer'));
  };

  const getDescription = () => {
    switch (activeTab) {
      case 'explorer':
        return '管理智能体的长期记忆、事实、经历及跨智能体共享上下文 / Browse and manage agent long-term memory';
      case 'backup':
        return '创建系统记忆的安全备份、随时恢复或进行快照版本控制 / Create or restore memory snapshots and backups';
      case 'cloud-backup':
        return '将备份自动同步至云存储(WebDAV/S3)，确保跨设备数据安全 / Auto-sync backups to cloud storage for cross-device safety';
      case 'archival':
        return '配置归档策略、运行自动归档，维持高性能的大脑索引 / Manage criteria and run older memory archival';
      case 'follow-ups':
        return t('memoryCenter.tabDescriptions.followUps');
      case 'migration':
        return t('memoryCenter.tabDescriptions.migration');
      default:
        return '';
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">{t('menu.memory')}</h1>
        <p className="text-sm text-muted-foreground">{getDescription()}</p>
      </div>

      {migrationUnavailable && (
        <div
          role="alert"
          className="rounded-xl border border-border/60 bg-secondary/40 px-4 py-4 sm:px-5 space-y-3"
        >
          <h2 className="text-base font-semibold text-foreground">
            {t('memoryCenter.migrationUnavailable.title')}
          </h2>
          <p className="text-sm text-muted-foreground leading-relaxed">
            {t('memoryCenter.migrationUnavailable.description')}
          </p>
          <Button asChild className="rounded-lg bg-primary text-primary-foreground hover:opacity-90">
            <a href={desktopDownloadHref} target="_blank" rel="noopener noreferrer">
              {t('memoryCenter.migrationUnavailable.downloadCta')}
            </a>
          </Button>
        </div>
      )}

      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        <TabsList
          className={`grid w-full max-w-3xl ${showMigration ? 'grid-cols-2 sm:grid-cols-6' : 'grid-cols-2 sm:grid-cols-5'} h-auto bg-secondary/50 backdrop-blur-sm p-1 rounded-xl border border-border/40 mb-6 gap-1`}
        >
          <TabsTrigger
            value="explorer"
            className="flex items-center justify-center gap-1.5 sm:gap-2 py-2 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <Brain className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.memory')}</span>
          </TabsTrigger>
          <TabsTrigger
            value="backup"
            className="flex items-center justify-center gap-1.5 sm:gap-2 py-2 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <Database className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.memory-backup')}</span>
          </TabsTrigger>
          <TabsTrigger
            value="cloud-backup"
            className="flex items-center justify-center gap-1.5 sm:gap-2 py-2 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <Cloud className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.memory-cloud-backup')}</span>
          </TabsTrigger>
          <TabsTrigger
            value="archival"
            className="flex items-center justify-center gap-1.5 sm:gap-2 py-2 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <Archive className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('menu.memory-archival')}</span>
          </TabsTrigger>
          <TabsTrigger
            value="follow-ups"
            className="flex items-center justify-center gap-1.5 sm:gap-2 py-2 min-w-0 text-sm font-medium rounded-lg transition-all"
          >
            <MessageCircle className="h-4 w-4 shrink-0" />
            <span className="truncate">{t('memoryCenter.tabs.followUps')}</span>
          </TabsTrigger>
          {showMigration && (
            <TabsTrigger
              value="migration"
              className="flex items-center justify-center gap-1.5 sm:gap-2 py-2 min-w-0 text-sm font-medium rounded-lg transition-all sm:col-span-1 col-span-2"
            >
              <ArrowRightLeft className="h-4 w-4 shrink-0" />
              <span className="truncate">{t('menu.memory-migration')}</span>
            </TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="explorer" className="focus-visible:outline-none focus-visible:ring-0">
          <MemorySection />
        </TabsContent>
        <TabsContent value="backup" className="focus-visible:outline-none focus-visible:ring-0">
          <MemoryBackupSection />
        </TabsContent>
        <TabsContent value="cloud-backup" className="focus-visible:outline-none focus-visible:ring-0">
          <RemoteBackupSection />
        </TabsContent>
        <TabsContent value="archival" className="focus-visible:outline-none focus-visible:ring-0">
          <MemoryArchivalSection />
        </TabsContent>
        <TabsContent value="follow-ups" className="focus-visible:outline-none focus-visible:ring-0">
          <FollowUpsPanel />
        </TabsContent>
        {showMigration && (
          <TabsContent value="migration" className="focus-visible:outline-none focus-visible:ring-0 space-y-6">
            <MigrationPendingReviewSection refreshToken={pendingReviewRefresh} />
            <MigrationWizardSection onMigrationComplete={() => setPendingReviewRefresh((v) => v + 1)} />
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
});

MemoryCenterSection.displayName = 'MemoryCenterSection';

export default MemoryCenterSection;
