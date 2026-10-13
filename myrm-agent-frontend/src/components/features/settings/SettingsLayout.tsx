'use client';

import { useMemo, useState, useEffect, useCallback, useRef, ComponentType } from 'react';
import dynamic from 'next/dynamic';
import { useParams, useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { useDeferredLocaleReady } from '@/i18n/deferred-locale-context';
import useAuthStore from '@/store/useAuthStore';
import { ArrowLeft, X } from 'lucide-react';
import { motion } from 'framer-motion';
import { toast } from 'sonner';
import { cn } from '@/lib/utils/classnameUtils';
import { showsLocalIntegrationTabs } from '@/lib/deploy-mode';
import useSettingsDirtyStore from '@/store/useSettingsDirtyStore';
import SettingsMenu from './SettingsMenu';
import { SettingsSkeleton } from './common/SettingsSkeleton';
import { SETTINGS_TABS, TAURI_ONLY_TABS, isSettingsTab, type SettingsTab } from './settingsRoutes';
import { trySettingsSubviewBack } from './settingsSubviewBack';

// 设置区块组件 (动态加载)
const AccountSection = dynamic(() => import('./sections/personal/AccountSection'), {
  loading: () => <SettingsSkeleton />,
});
const WorkbenchSection = dynamic(() => import('./sections/personal/WorkbenchRetentionSection'), {
  loading: () => <SettingsSkeleton />,
});
const PreferencesSection = dynamic(() => import('./sections/personal/PreferencesSection'), {
  loading: () => <SettingsSkeleton />,
});
const ThemeStudioSettingsSection = dynamic(() => import('./sections/personal/ThemeStudioSettingsSection'), {
  loading: () => <SettingsSkeleton />,
});
const PersonalizationSection = dynamic(() => import('./sections/personal/PersonalizationSection'), {
  loading: () => <SettingsSkeleton />,
});
const AgentsSection = dynamic(() => import('./sections/ai-core/AgentsSection'), {
  loading: () => <SettingsSkeleton />,
});
const SearchSection = dynamic(() => import('./sections/ai-core/SearchSection'), {
  loading: () => <SettingsSkeleton />,
});
const MCPSection = dynamic(() => import('./sections/ai-tools/MCPSection'), { loading: () => <SettingsSkeleton /> });
const SecurityPolicySection = dynamic(() => import('./sections/system/SecurityPolicySection'), {
  loading: () => <SettingsSkeleton />,
});
const ShareLinksSection = dynamic(() => import('./sections/system/ShareLinksSection'), {
  loading: () => <SettingsSkeleton />,
});
const RiskRulesSection = dynamic(() => import('./sections/system/RiskRulesSection'), {
  loading: () => <SettingsSkeleton />,
});
const CronSection = dynamic(() => import('./sections/system/CronSection'), { loading: () => <SettingsSkeleton /> });
const KanbanSection = dynamic(() => import('./sections/system/KanbanSection'), { loading: () => <SettingsSkeleton /> });
const CredentialsSection = dynamic(() => import('./sections/integration/CredentialsSection'), {
  loading: () => <SettingsSkeleton />,
});
const WikiSection = dynamic(() => import('./sections/knowledge/WikiSection').then((mod) => mod.WikiSection), {
  loading: () => <SettingsSkeleton />,
});
const CheckpointSection = dynamic(() => import('./sections/knowledge/CheckpointSection'), {
  loading: () => <SettingsSkeleton />,
});
const HostingTargetsSection = dynamic(() => import('./sections/hosting/HostingTargetsPanel'), {
  loading: () => <SettingsSkeleton />,
});
const OpenAIApiSection = dynamic(() => import('./sections/integration/OpenAIApiSection'), {
  loading: () => <SettingsSkeleton />,
});
const WorkspaceRulesSection = dynamic(() => import('./sections/ai-core/WorkspaceRulesSection'), {
  loading: () => <SettingsSkeleton />,
});
const IntegrationCatalogSection = dynamic(
  () => import('./sections/integration/integrations/IntegrationCatalogSection'),
  {
    loading: () => <SettingsSkeleton />,
  },
);
const IntegrationMemorySection = dynamic(() => import('./sections/integration/integrations/IntegrationMemorySection'), {
  loading: () => <SettingsSkeleton />,
});
const ExtensionBridgeSection = dynamic(() => import('./sections/integration/ExtensionBridgeSection'), {
  loading: () => <SettingsSkeleton />,
});
const ConnectSection = dynamic(() => import('./sections/integration/ConnectSection'), {
  loading: () => <SettingsSkeleton />,
});
const A2APeersSection = dynamic(() => import('./sections/integration/A2APeersSection'), {
  loading: () => <SettingsSkeleton />,
});

// 新增合并容器组件 (动态加载)
const ModelSettingsSection = dynamic(() => import('./sections/ai-core/ModelSettingsSection'), {
  loading: () => <SettingsSkeleton />,
});
const UnifiedSkillsSection = dynamic(() => import('./sections/ai-tools/UnifiedSkillsSection'), {
  loading: () => <SettingsSkeleton />,
});
const ToolQualitySection = dynamic(() => import('./sections/ai-tools/ToolQualitySection'), {
  loading: () => <SettingsSkeleton />,
});
const MemoryCenterSection = dynamic(() => import('./sections/knowledge/MemoryCenterSection'), {
  loading: () => <SettingsSkeleton />,
});
const CommunicationSection = dynamic(() => import('./sections/integration/CommunicationSection'), {
  loading: () => <SettingsSkeleton />,
});
const DeveloperCenterSection = dynamic(() => import('./sections/system/DeveloperCenterSection'), {
  loading: () => <SettingsSkeleton />,
});
const SystemCenterSection = dynamic(() => import('./sections/system/SystemCenterSection'), {
  loading: () => <SettingsSkeleton />,
});
const EnterpriseOrgSection = dynamic(() => import('./sections/enterprise/EnterpriseOrgSection'), {
  loading: () => <SettingsSkeleton />,
});
const BrandStudioSettingsSection = dynamic(() => import('./sections/knowledge/BrandStudioSettingsSection'), {
  loading: () => <SettingsSkeleton />,
});

/**
 * SettingsLayout - 配置页面布局组件
 *
 * 架构：
 * - URL 为唯一数据源，pendingTab 实现即时切换（不等待 router.push 异步完成）
 * - 已访问的 Section 缓存在 DOM 中，非活动 Section 用 hidden 移出布局，避免叠层拦截点击
 * - 活动 Section 使用 Framer Motion 150ms 淡入过渡
 */

const DEFAULT_TAB: SettingsTab = 'account';

// Section 组件映射表
const SECTION_COMPONENTS: Record<SettingsTab, ComponentType> = {
  account: AccountSection,
  workbench: WorkbenchSection,
  preferences: PreferencesSection,
  'theme-studio': ThemeStudioSettingsSection,
  personalization: PersonalizationSection,
  agents: AgentsSection,
  security: SecurityPolicySection,
  riskRules: RiskRulesSection,
  shares: ShareLinksSection,
  models: ModelSettingsSection,
  defaultModel: ModelSettingsSection,
  search: SearchSection,
  mcp: MCPSection,
  skills: UnifiedSkillsSection,
  skillQuality: ToolQualitySection,
  toolStability: ToolQualitySection,
  toolQuality: ToolQualitySection,
  evolutionPending: UnifiedSkillsSection,
  evolutionRejection: UnifiedSkillsSection,
  credentials: CredentialsSection,
  extensionBridge: ExtensionBridgeSection,
  wiki: WikiSection,
  memory: MemoryCenterSection,
  'brand-studio': BrandStudioSettingsSection,
  'memory-backup': MemoryCenterSection,
  'memory-cloud-backup': MemoryCenterSection,
  'memory-migration': MemoryCenterSection,
  openaiApi: OpenAIApiSection,
  hosting: HostingTargetsSection,
  integrationCatalog: IntegrationCatalogSection,
  integrationMemory: IntegrationMemorySection,
  connect: ConnectSection,
  a2aPeers: A2APeersSection,
  cron: CronSection,
  kanban: KanbanSection,
  checkpoint: CheckpointSection,
  channels: CommunicationSection,
  channelRouting: CommunicationSection,
  voice: CommunicationSection,
  companion: DeveloperCenterSection,
  usageStatistics: DeveloperCenterSection,
  experimentalFeatures: DeveloperCenterSection,
  workspaceRules: WorkspaceRulesSection,
  developer: DeveloperCenterSection,
  importExport: DeveloperCenterSection,
  enterprise: EnterpriseOrgSection,
  system: SystemCenterSection,
  about: SystemCenterSection,
};

// 轻量级 Section（预渲染）
const LIGHTWEIGHT_SECTIONS: SettingsTab[] = ['account', 'preferences', 'theme-studio', 'personalization', 'developer'];

function SettingsLayout() {
  const t = useTranslations('settings');
  const router = useRouter();
  const params = useParams();
  const userRole = useAuthStore((s) => s.user?.role);
  const isAdmin = userRole === 'admin';

  // 别名路由已由服务端页面重定向到父级 Tab，这里只需按部署形态过滤桌面端专属 Tab
  const visibleTabs = useMemo<readonly SettingsTab[]>(
    () => (showsLocalIntegrationTabs() ? SETTINGS_TABS : SETTINGS_TABS.filter((tab) => !TAURI_ONLY_TABS.includes(tab))),
    [],
  );
  const resolveVisibleTab = useCallback(
    (raw: string | null | undefined): SettingsTab | null =>
      raw && isSettingsTab(raw) && visibleTabs.includes(raw) ? raw : null,
    [visibleTabs],
  );

  // 即时切换：pendingTab 在点击时立即设置，URL 更新后自动清除
  const [pendingTab, setPendingTab] = useState<SettingsTab | null>(null);

  const urlTab = useMemo<SettingsTab>(
    () => resolveVisibleTab(params?.tab as string | undefined) ?? DEFAULT_TAB,
    [params?.tab, resolveVisibleTab],
  );

  // URL 更新后清除 pendingTab
  useEffect(() => {
    if (pendingTab && urlTab === pendingTab) {
      setPendingTab(null);
    }
  }, [urlTab, pendingTab]);

  const activeTab = pendingTab ?? urlTab;

  const [visitedTabs, setVisitedTabs] = useState<Set<SettingsTab>>(() => {
    return new Set([DEFAULT_TAB, ...LIGHTWEIGHT_SECTIONS]);
  });

  const renderedTabs = useMemo(() => {
    const tabs = new Set(visitedTabs);
    tabs.add(activeTab);
    return tabs;
  }, [visitedTabs, activeTab]);

  useEffect(() => {
    setVisitedTabs((prev) => new Set([...prev, activeTab]));
  }, [activeTab]);

  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(
    () => resolveVisibleTab(params?.tab as string | undefined) === null,
  );

  useEffect(() => {
    if (resolveVisibleTab(params?.tab as string | undefined)) {
      setIsMobileMenuOpen(false);
    }
  }, [params?.tab, resolveVisibleTab]);

  const isSavingRef = useRef(false);

  const flushDirty = useCallback(async (): Promise<boolean> => {
    const store = useSettingsDirtyStore.getState();
    if (!store.isDirtyAny()) {
      return true;
    }
    if (isSavingRef.current) {
      return false;
    }

    isSavingRef.current = true;
    try {
      const ok = await store.autoSaveAll();
      if (!ok) {
        toast.error(t('autoSaveFailed'));
      }
      return ok;
    } finally {
      isSavingRef.current = false;
    }
  }, [t]);

  const handleTabChange = useCallback(
    (tab: SettingsTab, sub?: string) => {
      void flushDirty().then((ok) => {
        if (!ok) {
          return;
        }
        setPendingTab(tab);
        const url = sub ? `/settings/${tab}?sub=${sub}` : `/settings/${tab}`;
        router.push(url, { scroll: false });
        setIsMobileMenuOpen(false);
      });
    },
    [flushDirty, router],
  );

  const handleBack = useCallback(() => {
    void flushDirty().then((ok) => {
      if (!ok) {
        return;
      }
      if (trySettingsSubviewBack()) {
        return;
      }
      router.push('/');
    });
  }, [flushDirty, router]);

  const handleMobileBack = () => {
    setIsMobileMenuOpen(true);
  };

  const deferredLocaleReady = useDeferredLocaleReady();

  return (
    <div
      className="h-full w-full flex flex-col lg:flex-row overflow-hidden"
      data-testid="settings-layout"
      aria-busy={deferredLocaleReady ? undefined : true}
    >
      {/* 移动端头部 */}
      <div className="lg:hidden flex items-center justify-between p-4 border-b border-border/50 backdrop-blur-xl bg-background/80">
        <button
          onClick={isMobileMenuOpen ? handleBack : handleMobileBack}
          className="p-2 -ml-2 hover:bg-secondary rounded-xl transition-colors"
        >
          <ArrowLeft size={20} className="text-foreground" />
        </button>
        <h1 className="text-base font-semibold text-foreground">
          {isMobileMenuOpen ? t('title') : t(`menu.${activeTab}`)}
        </h1>
        <button onClick={handleBack} className="p-2 -mr-2 hover:bg-secondary rounded-xl transition-colors">
          <X size={20} className="text-foreground" />
        </button>
      </div>

      {/* 左侧菜单 - PC 端始终显示，移动端根据状态切换 */}
      <aside
        className={cn(
          'lg:w-72 lg:border-r lg:border-border/50 lg:p-5 lg:bg-secondary/30 lg:backdrop-blur-sm',
          'flex-shrink-0 overflow-y-auto',
          // 移动端：菜单打开时显示，否则隐藏
          isMobileMenuOpen ? 'block p-4 bg-background/95 backdrop-blur-xl' : 'hidden lg:block',
        )}
      >
        {/* PC 端标题 */}
        <div className="hidden lg:flex items-center gap-2 mb-5">
          <button onClick={handleBack} className="p-2 -ml-2 hover:bg-secondary rounded-xl transition-colors">
            <ArrowLeft size={18} className="text-muted-foreground" />
          </button>
          <h1 className="text-lg font-semibold text-foreground">{t('title')}</h1>
        </div>

        <SettingsMenu activeTab={activeTab} onTabChange={handleTabChange} isAdmin={isAdmin} />
      </aside>

      {/* 右侧内容区 */}
      <main
        className={cn(
          'flex-1 overflow-y-auto p-4 lg:p-8 lg:px-10 relative',
          // 移动端：菜单打开时隐藏，否则显示
          isMobileMenuOpen ? 'hidden lg:block' : 'block',
        )}
      >
        <div className="relative w-full">
          {!deferredLocaleReady ? (
            <SettingsSkeleton />
          ) : (
            <>
              {/* 非活动 Section 用 hidden 移出布局，避免 invisible 叠层子元素拦截点击 */}
              {Array.from(renderedTabs).map((tab) => {
                const SectionComponent = SECTION_COMPONENTS[tab];
                const isActive = tab === activeTab;

                if (!isActive) {
                  return (
                    <div key={tab} hidden aria-hidden data-section={tab} data-active={false}>
                      <SectionComponent />
                    </div>
                  );
                }

                return (
                  <motion.div
                    key={tab}
                    initial={false}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.15, ease: 'easeOut' }}
                    className="w-full"
                    data-section={tab}
                    data-active
                  >
                    <SectionComponent />
                  </motion.div>
                );
              })}
            </>
          )}
        </div>
      </main>
    </div>
  );
}

export default SettingsLayout;
