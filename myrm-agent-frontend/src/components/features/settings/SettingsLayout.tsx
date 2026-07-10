'use client';

import { useMemo, useState, useEffect, useCallback, useRef, ComponentType } from 'react';
import dynamic from 'next/dynamic';
import { useParams, useRouter, usePathname } from 'next/navigation';
import { useTranslations } from 'next-intl';
import useAuthStore from '@/store/useAuthStore';
import { ArrowLeft, X } from 'lucide-react';
import { motion } from 'framer-motion';
import { toast } from 'sonner';
import { cn } from '@/lib/utils/classnameUtils';
import { isLocalMode } from '@/lib/deploy-mode';
import useSettingsDirtyStore from '@/store/useSettingsDirtyStore';
import SettingsMenu, { SettingsTab } from './SettingsMenu';
import { SettingsSkeleton } from './common/SettingsSkeleton';
import { trySettingsSubviewBack } from './settingsSubviewBack';

// 设置区块组件 (动态加载)
const AccountSection = dynamic(() => import('./sections/personal/AccountSection'), { loading: () => <SettingsSkeleton /> });
const PreferencesSection = dynamic(() => import('./sections/personal/PreferencesSection'), {
  loading: () => <SettingsSkeleton />,
});
const PersonalizationSection = dynamic(() => import('./sections/personal/PersonalizationSection'), {
  loading: () => <SettingsSkeleton />,
});
const AgentsSection = dynamic(() => import('./sections/ai-core/AgentsSection'), { loading: () => <SettingsSkeleton /> });
const SearchSection = dynamic(() => import('./sections/ai-core/SearchSection'), { loading: () => <SettingsSkeleton /> });
const MCPSection = dynamic(() => import('./sections/ai-tools/MCPSection'), { loading: () => <SettingsSkeleton /> });
const SecurityPolicySection = dynamic(() => import('./sections/system/SecurityPolicySection'), {
  loading: () => <SettingsSkeleton />,
});
const RiskRulesSection = dynamic(() => import('./sections/system/RiskRulesSection'), { loading: () => <SettingsSkeleton /> });
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
const OpenAIApiSection = dynamic(() => import('./sections/integration/OpenAIApiSection'), { loading: () => <SettingsSkeleton /> });
const WorkspaceRulesSection = dynamic(() => import('./sections/ai-core/WorkspaceRulesSection'), {
  loading: () => <SettingsSkeleton />,
});
const IntegrationCatalogSection = dynamic(() => import('./sections/integration/integrations/IntegrationCatalogSection'), {
  loading: () => <SettingsSkeleton />,
});
const IntegrationMemorySection = dynamic(() => import('./sections/integration/integrations/IntegrationMemorySection'), {
  loading: () => <SettingsSkeleton />,
});
const ExtensionBridgeSection = dynamic(() => import('./sections/integration/ExtensionBridgeSection'), {
  loading: () => <SettingsSkeleton />,
});
const ConnectSection = dynamic(() => import('./sections/integration/ConnectSection'), {
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

/**
 * SettingsLayout - 配置页面布局组件
 *
 * 架构：
 * - URL 为唯一数据源，pendingTab 实现即时切换（不等待 router.push 异步完成）
 * - 已访问的 Section 缓存在 DOM 中，非活动 Section 用 hidden 移出布局，避免叠层拦截点击
 * - 活动 Section 使用 Framer Motion 150ms 淡入过渡
 */

const DEFAULT_TAB: SettingsTab = 'account';

const BASE_TABS: SettingsTab[] = [
  'account',
  'preferences',
  'personalization',
  'agents',
  'security',
  'riskRules',
  'models',
  'defaultModel',
  'search',
  'mcp',
  'skills',
  'skillQuality',
  'toolStability',
  'toolQuality',
  'evolutionPending',
  'evolutionRejection',
  'credentials',
  'wiki',
  'memory',
  'cron',
  'kanban',
  'checkpoint',
  'openaiApi',
  'hosting',
  'integrationCatalog',
  'integrationMemory',
  'connect',
  'workspaceRules',
  'developer',
  'importExport',
  'companion',
  'usageStatistics',
  'experimentalFeatures',
  'memory-backup',
  'memory-cloud-backup',
  'memory-archival',
  'memory-migration',
  'enterprise',
  'system',
  'about',
];

const TAURI_ONLY_TABS: SettingsTab[] = ['channels', 'channelRouting', 'voice'];

// 扁平路由自动分发到整合后的父组件并携带 sub 参数，实现路由多层兼容
const DEPRECATED_TAB_MAP: Record<string, { parent: SettingsTab; sub?: string }> = {
  defaultModel: { parent: 'models', sub: 'default' },
  evolutionPending: { parent: 'skills', sub: 'pending' },
  evolutionRejection: { parent: 'skills', sub: 'rejections' },
  skillQuality: { parent: 'toolQuality', sub: 'quality' },
  toolStability: { parent: 'toolQuality', sub: 'stability' },
  'memory-backup': { parent: 'memory', sub: 'backup' },
  'memory-cloud-backup': { parent: 'memory', sub: 'cloud-backup' },
  'memory-archival': { parent: 'memory', sub: 'archival' },
  'memory-migration': { parent: 'memory', sub: 'migration' },
  channelRouting: { parent: 'channels', sub: 'routing' },
  voice: { parent: 'channels', sub: 'voice' },
  experimentalFeatures: { parent: 'developer', sub: 'experimental' },
  usageStatistics: { parent: 'developer', sub: 'usage' },
  companion: { parent: 'developer', sub: 'companion' },
  importExport: { parent: 'developer', sub: 'importExport' },
  eval: { parent: 'developer' },
  about: { parent: 'system', sub: 'about' },
};

// Section 组件映射表
const SECTION_COMPONENTS: Record<SettingsTab, ComponentType> = {
  account: AccountSection,
  preferences: PreferencesSection,
  personalization: PersonalizationSection,
  agents: AgentsSection,
  security: SecurityPolicySection,
  riskRules: RiskRulesSection,
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
  'memory-backup': MemoryCenterSection,
  'memory-cloud-backup': MemoryCenterSection,
  'memory-archival': MemoryCenterSection,
  'memory-migration': MemoryCenterSection,
  openaiApi: OpenAIApiSection,
  hosting: HostingTargetsSection,
  integrationCatalog: IntegrationCatalogSection,
  integrationMemory: IntegrationMemorySection,
  connect: ConnectSection,
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
const LIGHTWEIGHT_SECTIONS: SettingsTab[] = ['account', 'preferences', 'personalization', 'developer'];

function SettingsLayout() {
  const t = useTranslations('settings');
  const router = useRouter();
  const params = useParams();
  const pathname = usePathname();
  const userRole = useAuthStore((s) => s.user?.role);
  const isAdmin = userRole === 'admin';

  const validTabs = useMemo<SettingsTab[]>(() => {
    const extra = isLocalMode() ? TAURI_ONLY_TABS : [];
    return [...BASE_TABS.slice(0, 12), ...extra, ...BASE_TABS.slice(12)];
  }, []);

  // 即时切换：pendingTab 在点击时立即设置，URL 更新后自动清除
  const [pendingTab, setPendingTab] = useState<SettingsTab | null>(null);

  const urlTab = useMemo<SettingsTab>(() => {
    const raw = (params?.tab as string) || null;
    // 如果是废弃的扁平路由，在渲染时返回其父路由以防白屏，然后由下面的 useEffect 完成实际 URL 跳转
    if (raw && DEPRECATED_TAB_MAP[raw]) {
      return DEPRECATED_TAB_MAP[raw].parent;
    }
    return raw && validTabs.includes(raw as SettingsTab) ? (raw as SettingsTab) : DEFAULT_TAB;
  }, [params?.tab, validTabs]);

  // 自动将扁平子路由转换映射并进行 URL 路由跳转，确保后向兼容性
  useEffect(() => {
    const raw = (params?.tab as string) || null;
    if (raw && DEPRECATED_TAB_MAP[raw]) {
      const mapping = DEPRECATED_TAB_MAP[raw];
      const nextUrl = `/settings/${mapping.parent}${mapping.sub ? `?sub=${mapping.sub}` : ''}`;
      router.replace(nextUrl);
    }
  }, [params?.tab, router]);

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

  useEffect(() => {
    setVisitedTabs((prev) => new Set([...prev, activeTab]));
  }, [activeTab]);

  // 监听预加载事件
  useEffect(() => {
    const handlePrefetch = (e: Event) => {
      const customEvent = e as CustomEvent<{ tabId: string }>;
      const tabId = customEvent.detail?.tabId as SettingsTab;
      if (tabId && !visitedTabs.has(tabId)) {
        // 将其加入 visitedTabs，触发 React 渲染该组件（但可能通过 CSS 隐藏），从而实现预加载
        // 由于我们使用了 next/dynamic，渲染组件就会触发网络请求拉取代码
        setVisitedTabs((prev) => new Set([...prev, tabId]));
      }
    };
    window.addEventListener('prefetch-settings-tab', handlePrefetch);
    return () => window.removeEventListener('prefetch-settings-tab', handlePrefetch);
  }, [visitedTabs]);

  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(() => {
    const initialTab = (params?.tab as string) || null;
    return !(initialTab && validTabs.includes(initialTab as SettingsTab));
  });

  useEffect(() => {
    if (params?.tab && validTabs.includes(params.tab as SettingsTab)) {
      setIsMobileMenuOpen(false);
    } else if (!params?.tab && pathname === '/settings') {
      setIsMobileMenuOpen(true);
    }
  }, [params?.tab, pathname, validTabs]);

  const isSavingRef = useRef(false);

  const flushDirty = useCallback(async (): Promise<boolean> => {
    const store = useSettingsDirtyStore.getState();
    if (!store.isDirtyAny()) return true;
    if (isSavingRef.current) return false;

    isSavingRef.current = true;
    try {
      const ok = await store.autoSaveAll();
      if (!ok) toast.error(t('autoSaveFailed'));
      return ok;
    } finally {
      isSavingRef.current = false;
    }
  }, [t]);

  const handleTabChange = useCallback(
    (tab: SettingsTab, sub?: string) => {
      void flushDirty().then((ok) => {
        if (!ok) return;
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
      if (!ok) return;
      if (trySettingsSubviewBack()) return;
      router.push('/');
    });
  }, [flushDirty, router]);

  const handleMobileBack = () => {
    setIsMobileMenuOpen(true);
  };

  return (
    <div className="h-full w-full flex flex-col lg:flex-row overflow-hidden">
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
          {/* 非活动 Section 用 hidden 移出布局，避免 invisible 叠层子元素拦截点击 */}
          {Array.from(visitedTabs).map((tab) => {
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
        </div>
      </main>
    </div>
  );
}

export default SettingsLayout;
