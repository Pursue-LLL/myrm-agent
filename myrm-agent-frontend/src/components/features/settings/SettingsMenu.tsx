'use client';

import { memo, useMemo, useState, useCallback, useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { isLocalMode, isSandbox } from '@/lib/deploy-mode';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import {
  User,
  Sliders,
  Palette,
  Server,
  Plug,
  Search,
  Code,
  Settings,
  Timer,
  Radio,
  Shield,
  Activity,
  Globe,
  KeyRound,
  BookOpen,
  Archive,
  Columns,
  Wand2,
  ChevronDown,
  ChevronUp,
  XCircle,
  Brain,
  Database,
  Cable,
  Share2,
  Building2,
} from 'lucide-react';
import { AiNetworkIcon } from 'hugeicons-react';

export type SettingsGroup = 'personal' | 'ai-core' | 'ai-tools' | 'knowledge' | 'integration' | 'system';

const groupConfig: Record<SettingsGroup, { labelKey: string; order: number }> = {
  personal: { labelKey: 'group.personal', order: 1 },
  'ai-core': { labelKey: 'group.ai-core', order: 2 },
  'ai-tools': { labelKey: 'group.ai-tools', order: 3 },
  knowledge: { labelKey: 'group.knowledge', order: 4 },
  integration: { labelKey: 'group.integration', order: 5 },
  system: { labelKey: 'group.system', order: 6 },
};

export type SettingsTab =
  | 'account'
  | 'preferences'
  | 'personalization'
  | 'agents'
  | 'security'
  | 'riskRules'
  | 'models'
  | 'defaultModel'
  | 'search'
  | 'mcp'
  | 'skills'
  | 'skillQuality'
  | 'toolStability'
  | 'toolQuality'
  | 'evolutionPending'
  | 'evolutionRejection'
  | 'credentials'
  | 'wiki'
  | 'openaiApi'
  | 'hosting'
  | 'developer'
  | 'importExport'
  | 'cron'
  | 'kanban'
  | 'checkpoint'
  | 'channels'
  | 'channelRouting'
  | 'voice'
  | 'companion'
  | 'usageStatistics'
  | 'experimentalFeatures'
  | 'memory'
  | 'memory-backup'
  | 'memory-cloud-backup'
  | 'memory-archival'
  | 'memory-migration'
  | 'integrationCatalog'
  | 'integrationMemory'
  | 'extensionBridge'
  | 'connect'
  | 'workspaceRules'
  | 'enterprise'
  | 'system'
  | 'about';

interface MenuItem {
  id: SettingsTab;
  icon: React.ElementType;
  labelKey: string;
  group: SettingsGroup;
  tauriOnly?: boolean;
  sandboxOnly?: boolean;
  adminOnly?: boolean;
}

const menuItems: MenuItem[] = [
  // 个人与偏好
  { id: 'account', icon: User, labelKey: 'account', group: 'personal' },
  { id: 'preferences', icon: Sliders, labelKey: 'preferences', group: 'personal' },
  { id: 'personalization', icon: Palette, labelKey: 'personalization', group: 'personal' },

  // 智能体配置
  { id: 'agents', icon: AiNetworkIcon, labelKey: 'agents', group: 'ai-core' },
  { id: 'models', icon: Server, labelKey: 'models', group: 'ai-core' },
  { id: 'search', icon: Search, labelKey: 'search', group: 'ai-core' },
  { id: 'workspaceRules', icon: Code, labelKey: 'workspaceRules', group: 'ai-core' },

  // 技能与插件
  { id: 'skills', icon: Wand2, labelKey: 'skills', group: 'ai-tools' },
  { id: 'mcp', icon: Plug, labelKey: 'mcp', group: 'ai-tools' },
  { id: 'toolQuality', icon: Activity, labelKey: 'toolQuality', group: 'ai-tools' },

  // 知识与数据
  { id: 'wiki', icon: BookOpen, labelKey: 'wiki', group: 'knowledge' },
  { id: 'memory', icon: Brain, labelKey: 'memory', group: 'knowledge' },

  // 通信与集成
  { id: 'integrationCatalog', icon: Plug, labelKey: 'integrationCatalog', group: 'integration' },
  { id: 'integrationMemory', icon: Database, labelKey: 'integrationMemory', group: 'integration' },
  { id: 'extensionBridge', icon: Cable, labelKey: 'extensionBridge', group: 'integration' },
  { id: 'connect', icon: Share2, labelKey: 'connect', group: 'integration' },
  { id: 'channels', icon: Radio, labelKey: 'channels', group: 'integration', tauriOnly: true },
  { id: 'hosting', icon: Globe, labelKey: 'hosting', group: 'integration' },
  { id: 'openaiApi', icon: KeyRound, labelKey: 'openaiApi', group: 'integration' },

  // 系统与安全
  { id: 'security', icon: Shield, labelKey: 'security', group: 'system' },
  { id: 'cron', icon: Timer, labelKey: 'cron', group: 'system' },
  { id: 'kanban', icon: Columns, labelKey: 'kanban', group: 'system' },
  { id: 'checkpoint', icon: Archive, labelKey: 'checkpoint', group: 'system' },
  { id: 'enterprise', icon: Building2, labelKey: 'enterprise', group: 'system', sandboxOnly: true },
  { id: 'developer', icon: Code, labelKey: 'developer', group: 'system' },
  { id: 'system', icon: Settings, labelKey: 'system', group: 'system' },
];

interface SubMenuItem {
  id: string;
  labelKey: string;
}

const subMenuItems: Partial<Record<SettingsTab, SubMenuItem[]>> = {
  models: [{ id: 'default', labelKey: 'defaultModel' }],
  skills: [
    { id: 'pending', labelKey: 'evolutionPending' },
    { id: 'rejections', labelKey: 'evolutionRejection' },
  ],
  toolQuality: [
    { id: 'quality', labelKey: 'skillQuality' },
    { id: 'stability', labelKey: 'toolStability' },
  ],
  memory: [
    { id: 'backup', labelKey: 'memory-backup' },
    { id: 'cloud-backup', labelKey: 'memory-cloud-backup' },
    { id: 'archival', labelKey: 'memory-archival' },
    { id: 'migration', labelKey: 'memory-migration' },
  ],
  channels: [
    { id: 'routing', labelKey: 'channelRouting' },
    { id: 'voice', labelKey: 'voice' },
  ],
  developer: [
    { id: 'experimental', labelKey: 'experimentalFeatures' },
    { id: 'usage', labelKey: 'usageStatistics' },
    { id: 'companion', labelKey: 'companion' },
    { id: 'importexport', labelKey: 'importExport' },
  ],
  system: [{ id: 'about', labelKey: 'about' }],
};

export interface FilteredMenuItem {
  item: MenuItem;
  matchedSubLabel?: string;
  subTabId?: string;
}

interface SettingsMenuProps {
  activeTab: SettingsTab;
  onTabChange: (tab: SettingsTab, sub?: string) => void;
  isAdmin?: boolean;
  className?: string;
}

/** 高亮搜索匹配文字 */
function highlightMatch(text: string, query: string): React.ReactNode {
  if (!query.trim()) return text;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-primary/20 text-primary rounded-sm px-0.5">{text.slice(idx, idx + query.length)}</mark>
      {text.slice(idx + query.length)}
    </>
  );
}

const SettingsMenu = memo<SettingsMenuProps>(({ activeTab, onTabChange, isAdmin = false, className }) => {
  const t = useTranslations('settings.menu');
  const tauriMode = isLocalMode();
  const sandboxMode = isSandbox();
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedGroups, setExpandedGroups] = useState<Set<SettingsGroup>>(() => {
    return new Set(Object.keys(groupConfig) as SettingsGroup[]);
  });
  const [focusIndex, setFocusIndex] = useState(-1);
  const navRef = useRef<HTMLElement>(null);

  const visibleItems = useMemo(
    () =>
      menuItems.filter((item) => {
        if (item.tauriOnly && !tauriMode) return false;
        if (item.sandboxOnly && !sandboxMode) return false;
        if (item.adminOnly && !isAdmin) return false;
        return true;
      }),
    [tauriMode, sandboxMode, isAdmin],
  );

  const isSearching = searchQuery.trim().length > 0;
  const isCompanionEnabled = useFeatureGateStore((s) => s.isEnabled('companion_mode'));

  const dynamicSubMenuItems = useMemo(() => {
    if (isCompanionEnabled) return subMenuItems;
    const next = { ...subMenuItems };
    if (next.developer) {
      next.developer = next.developer.filter((item) => item.id !== 'companion');
    }
    return next;
  }, [isCompanionEnabled]);

  // 搜索过滤
  const filteredItems = useMemo<FilteredMenuItem[]>(() => {
    if (!isSearching) {
      return visibleItems.map((item) => ({ item }));
    }
    const query = searchQuery.toLowerCase();
    const result: FilteredMenuItem[] = [];

    visibleItems.forEach((item) => {
      const parentLabel = t(item.labelKey).toLowerCase();
      if (parentLabel.includes(query)) {
        result.push({ item });
        return;
      }

      // 检索子项
      const subs = dynamicSubMenuItems[item.id];
      if (subs) {
        const matchedSub = subs.find((sub) => t(sub.labelKey).toLowerCase().includes(query));
        if (matchedSub) {
          result.push({
            item,
            matchedSubLabel: t(matchedSub.labelKey),
            subTabId: matchedSub.id,
          });
        }
      }
    });

    return result;
  }, [visibleItems, searchQuery, t, isSearching, dynamicSubMenuItems]);

  // 按分组排序并分组，过滤掉空分组
  const groupedItems = useMemo(() => {
    const groups = new Map<SettingsGroup, FilteredMenuItem[]>();
    filteredItems.forEach((fItem) => {
      const group = fItem.item.group;
      if (!groups.has(group)) groups.set(group, []);
      groups.get(group)!.push(fItem);
    });
    return Array.from(groups.entries())
      .filter(([, items]) => items.length > 0)
      .sort(([a], [b]) => groupConfig[a].order - groupConfig[b].order);
  }, [filteredItems]);

  // 扁平化的可见项列表（用于键盘导航）
  const flatItems = useMemo(() => {
    return groupedItems.flatMap(([, items]) => items);
  }, [groupedItems]);

  // 搜索时自动展开包含匹配项的分组
  useEffect(() => {
    if (!isSearching) return;
    const matchedGroups = new Set(filteredItems.map((fItem) => fItem.item.group));
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      matchedGroups.forEach((g) => next.add(g));
      return next;
    });
    setFocusIndex(-1);
  }, [isSearching, filteredItems]);

  // 切换分组展开/折叠状态
  const toggleGroup = useCallback((group: SettingsGroup) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) {
        next.delete(group);
      } else {
        next.add(group);
      }
      return next;
    });
  }, []);

  const clearSearch = useCallback(() => {
    setSearchQuery('');
    setFocusIndex(-1);
  }, []);

  // 键盘导航
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!isSearching) return;

      switch (e.key) {
        case 'ArrowDown': {
          e.preventDefault();
          setFocusIndex((prev) => (prev < flatItems.length - 1 ? prev + 1 : 0));
          break;
        }
        case 'ArrowUp': {
          e.preventDefault();
          setFocusIndex((prev) => (prev > 0 ? prev - 1 : flatItems.length - 1));
          break;
        }
        case 'Enter': {
          if (focusIndex >= 0 && focusIndex < flatItems.length) {
            e.preventDefault();
            const fItem = flatItems[focusIndex];
            onTabChange(fItem.item.id, fItem.subTabId);
          }
          break;
        }
        case 'Escape': {
          e.preventDefault();
          clearSearch();
          break;
        }
      }
    },
    [isSearching, flatItems, focusIndex, onTabChange, clearSearch],
  );

  // focusIndex 变化时滚动到可见区域
  useEffect(() => {
    if (focusIndex < 0 || !navRef.current) return;
    const buttons = navRef.current.querySelectorAll('[data-menu-item]');
    buttons[focusIndex]?.scrollIntoView({ block: 'nearest' });
  }, [focusIndex]);

  // 计算当前 focusIndex 对应的全局索引（在扁平列表中的位置）
  let itemGlobalIndex = 0;

  return (
    <nav
      ref={navRef}
      className={cn('flex flex-col gap-0.5 overflow-y-auto scrollbar-hide', className)}
      onKeyDown={handleKeyDown}
    >
      {/* 搜索框 */}
      <div className="relative mb-4">
        <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
          <Search className="text-primary/40" />
        </div>
        <input
          type="text"
          placeholder={t('searchPlaceholder')}
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value);
            setFocusIndex(-1);
          }}
          className="w-full pl-11 pr-9 py-2.5 text-sm bg-secondary/50 backdrop-blur-sm border border-border/50 rounded-xl placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 transition-all"
        />
        {isSearching && (
          <button
            onClick={clearSearch}
            className="absolute inset-y-0 right-0 pr-3 flex items-center text-muted-foreground/40 hover:text-muted-foreground/70 transition-colors"
            aria-label="Clear search"
          >
            <XCircle />
          </button>
        )}
      </div>

      {/* 无结果提示 */}
      {isSearching && flatItems.length === 0 && (
        <div className="px-3 py-12 text-center text-sm text-muted-foreground/40">{t('noResults')}</div>
      )}

      {groupedItems.map(([group, items]) => {
        const isExpanded = expandedGroups.has(group);

        return (
          <div key={group} className="mb-3">
            <button
              onClick={() => toggleGroup(group)}
              className="flex items-center justify-between w-full pl-4 pr-3 py-2 text-[11px] font-medium text-muted-foreground/40 tracking-wide hover:text-muted-foreground/60 transition-colors border-l-2 border-primary/10"
            >
              <span>{t(groupConfig[group].labelKey)}</span>
              {isExpanded ? (
                <ChevronUp className="text-muted-foreground/25" />
              ) : (
                <ChevronDown className="text-muted-foreground/25" />
              )}
            </button>
            {isExpanded && (
              <div className="flex flex-col gap-0.5 mt-1.5">
                {items.map((fItem) => {
                  const item = fItem.item;
                  const Icon = item.icon;
                  const isActive = activeTab === item.id;
                  const currentIdx = itemGlobalIndex++;
                  const isFocused = currentIdx === focusIndex;

                  return (
                    <button
                      key={item.id}
                      data-menu-item
                      onClick={() => onTabChange(item.id, fItem.subTabId)}
                      className={cn(
                        'group relative flex flex-col items-start gap-1 pl-4 pr-3 py-2 rounded-xl text-sm transition-all duration-200 w-full',
                        isActive
                          ? 'bg-primary/[0.08] text-primary font-semibold'
                          : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground',
                        isFocused && !isActive && 'ring-2 ring-primary/30 bg-secondary/40',
                      )}
                    >
                      <div className="flex items-center gap-3 w-full">
                        {/* 活跃指示条 */}
                        {isActive && (
                          <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 bg-primary rounded-r-full" />
                        )}
                        <Icon
                          size={18}
                          className={cn(
                            'shrink-0 transition-colors',
                            isActive ? 'text-primary' : 'text-muted-foreground/60 group-hover:text-foreground/70',
                          )}
                        />
                        <span className="truncate flex-1 text-left">
                          {isSearching ? highlightMatch(t(item.labelKey), searchQuery) : t(item.labelKey)}
                        </span>
                      </div>
                      {fItem.matchedSubLabel && (
                        <div className="text-[10px] pl-[30px] text-muted-foreground/50 font-normal">
                          匹配: {highlightMatch(fItem.matchedSubLabel, searchQuery)}
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </nav>
  );
});

SettingsMenu.displayName = 'SettingsMenu';

export default SettingsMenu;
