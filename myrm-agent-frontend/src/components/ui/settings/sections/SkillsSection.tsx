'use client';

import { memo, useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconRefresh,
  IconExplore,
  IconFolder,
  IconSearch,
  IconChevronDown,
  IconChevronRight,
  IconShieldAlert,
  IconUpload,
  IconDownload,
} from '@/components/ui/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { toast } from '@/hooks/useToast';
import useAuthStore from '@/store/useAuthStore';
import { useSkillStore } from '@/store/skill';
import { useSkillDraftStore } from '@/store/skill/useSkillDraftStore';
import type { Skill, SkillLifecycleAction, SkillSourceFilter, SkillStatusFilter } from '@/store/skill/types';
import {
  SkillList,
  SkillDiscoverTab,
  LocalPathsConfig,
  SkillDraftReviewPanel,
  SkillHistoryPanel,
  SkillSyncIndicator,
} from '@/components/ui/skills';
import { EvolutionStrategyConfig } from '@/components/ui/skills/EvolutionStrategyConfig';
import CuratorSettingsPanel from '@/components/ui/skills/CuratorSettingsPanel';
import SkillDetailSheet from '@/components/ui/skills/SkillDetailSheet';
import { SkillPermissionApprovalDialog } from '@/components/ui/skills/SkillPermissionApprovalDialog';
import { SkillInstanceManager } from '@/components/ui/skills/SkillInstanceManager';
import SkillBatchImportDialog from '@/components/ui/skills/SkillBatchImportDialog';
import { getSkillStatus } from '@/components/ui/skills/SkillCard';
import { isLocalMode } from '@/lib/deploy-mode';
import SettingsSection from './SettingsSection';

type TabValue = 'discover' | 'installed';

const SkillsSection = memo(() => {
  const t = useTranslations('settings.skills');
  const { user, isInitialized } = useAuthStore();

  const [isMounted, setIsMounted] = useState(false);
  useEffect(() => {
    setIsMounted(true);
  }, []);

  const {
    marketSkills,
    localSkills,
    enabledPrebuiltIds,
    enabledLocalSkillIds,
    isLoadingMarket,
    isLoadingLocal,
    isLoadingConfig,
    fetchMarketSkills,
    fetchUserSkillConfig,
    fetchLocalSkillPaths,
    fetchLocalSkills,
    toggleSkill,
    toggleLocalSkill,
    batchToggleSkills,
    isSkillEnabled,
  } = useSkillStore();

  const { unreviewedCount, fetchUnreviewedCount } = useSkillDraftStore();

  const [activeTab, setActiveTab] = useState<TabValue>('discover');
  const [detailSkill, setDetailSkill] = useState<Skill | null>(null);
  const [installedSearch, setInstalledSearch] = useState('');
  const [sourceFilter, setSourceFilter] = useState<SkillSourceFilter>('all');
  const [statusFilter, setStatusFilter] = useState<SkillStatusFilter>('all');
  const [localPathsOpen, setLocalPathsOpen] = useState(false);
  const [instanceManagerSkill, setInstanceManagerSkill] = useState<string | null>(null);

  // Permission approval dialog state
  const [pendingApproval, setPendingApproval] = useState<{
    skillId: string;
    skillName: string;
    requiredPermissions: string[];
    description: string;
    allowedDomains?: string[] | null;
  } | null>(null);

  // Security scan blocked dialog state
  const [blockedSkill, setBlockedSkill] = useState<{
    skillId: string;
    skillName: string;
    scanFindings: Array<{
      threat_type: string;
      severity: number;
      description: string;
      line_number: number | null;
    }>;
  } | null>(null);

  const [pendingDestructiveAction, setPendingDestructiveAction] = useState<{
    skill: Skill;
    action: 'reset-to-default' | 'accept-upstream';
  } | null>(null);

  const [isSyncing, setIsSyncing] = useState(false);
  const [isBatchImportOpen, setIsBatchImportOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleExport = useCallback(async () => {
    if (!user?.id) return;
    try {
      setIsSyncing(true);
      const res = await fetch(`/api/v1/skills/export`);
      if (!res.ok) throw new Error('Export failed');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `myrm_skills_backup_${user.id}.zip`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      toast({ title: t('installed.exportFailed') || 'Export failed', variant: 'destructive' });
    } finally {
      setIsSyncing(false);
    }
  }, [user?.id, t]);

  const handleImport = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      if (!user?.id || !e.target.files?.length) return;
      const file = e.target.files[0];
      try {
        setIsSyncing(true);
        const formData = new FormData();
        formData.append('file', file);
        const res = await fetch(`/api/v1/skills/import`, {
          method: 'POST',
          body: formData,
        });
        if (!res.ok) throw new Error('Import failed');
        const data = await res.json();
        toast({ title: data.message || t('installed.importSuccess') || 'Import success' });
        fetchLocalSkills();
        fetchUserSkillConfig(true);
      } catch {
        toast({ title: t('installed.importFailed') || 'Import failed', variant: 'destructive' });
      } finally {
        setIsSyncing(false);
        if (fileInputRef.current) fileInputRef.current.value = '';
      }
    },
    [user?.id, fetchLocalSkills, fetchUserSkillConfig, t],
  );

  useEffect(() => {
    fetchMarketSkills();
    fetchUserSkillConfig();
    fetchLocalSkillPaths();
    fetchLocalSkills();
    fetchUnreviewedCount();
  }, [fetchMarketSkills, fetchUserSkillConfig, fetchLocalSkillPaths, fetchLocalSkills, fetchUnreviewedCount]);

  useEffect(() => {
    if (!user?.id) return;

    const refreshGrowthState = () => {
      void Promise.all([fetchUnreviewedCount(), fetchUserSkillConfig(true), fetchLocalSkills()]);
    };

    window.addEventListener('skill-draft-created', refreshGrowthState);
    window.addEventListener('skill-growth-updated', refreshGrowthState);
    window.addEventListener('skill-evolved', refreshGrowthState);
    return () => {
      window.removeEventListener('skill-draft-created', refreshGrowthState);
      window.removeEventListener('skill-growth-updated', refreshGrowthState);
      window.removeEventListener('skill-evolved', refreshGrowthState);
    };
  }, [fetchLocalSkills, fetchUnreviewedCount, fetchUserSkillConfig, user?.id]);

  const allInstalledSkills = useMemo(() => {
    return [...marketSkills, ...localSkills].filter((s) => s.user_invocable !== false);
  }, [marketSkills, localSkills]);

  const archivedCount = useMemo(() => {
    return allInstalledSkills.filter((s) => s.usage_stats?.lifecycle_status === 'archived').length;
  }, [allInstalledSkills]);

  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  const toggleGroup = useCallback((group: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) {
        next.delete(group);
      } else {
        next.add(group);
      }
      return next;
    });
  }, []);

  const filteredInstalledSkills = useMemo(() => {
    let skills = allInstalledSkills;

    if (sourceFilter !== 'all') {
      skills = skills.filter((s) => s.type === sourceFilter);
    }

    if (statusFilter === 'all') {
      // Hide archived skills by default, unless searching
      if (!installedSearch.trim()) {
        skills = skills.filter((s) => s.usage_stats?.lifecycle_status !== 'archived');
      }
    } else if (statusFilter === 'stale' || statusFilter === 'archived') {
      skills = skills.filter((s) => s.usage_stats?.lifecycle_status === statusFilter);
    } else {
      skills = skills.filter((s) => {
        if (s.usage_stats?.lifecycle_status === 'archived') return false;
        const status = getSkillStatus(s, isSkillEnabled(s.id));
        return status === statusFilter;
      });
    }

    if (installedSearch.trim()) {
      const q = installedSearch.toLowerCase();
      skills = skills.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          s.description.toLowerCase().includes(q) ||
          s.tags.some((tag) => tag.toLowerCase().includes(q)),
      );
    }

    // Sort by usage stats (last_used_at DESC, then call_count DESC, then updated_at DESC)
    skills.sort((a, b) => {
      const aTime = a.usage_stats?.last_used_at ? new Date(a.usage_stats.last_used_at).getTime() : 0;
      const bTime = b.usage_stats?.last_used_at ? new Date(b.usage_stats.last_used_at).getTime() : 0;
      if (aTime !== bTime) return bTime - aTime;

      const aCount = a.usage_stats?.call_count || 0;
      const bCount = b.usage_stats?.call_count || 0;
      if (aCount !== bCount) return bCount - aCount;

      const aUpdate = new Date(a.updated_at).getTime();
      const bUpdate = new Date(b.updated_at).getTime();
      return bUpdate - aUpdate;
    });

    return skills;
  }, [allInstalledSkills, sourceFilter, statusFilter, installedSearch, isSkillEnabled]);

  type SkillGroup = { key: string; label: string; skills: Skill[] };

  const groupedSkills = useMemo((): SkillGroup[] => {
    const groups: SkillGroup[] = [];
    const byType: Record<string, Skill[]> = {};
    for (const s of filteredInstalledSkills) {
      (byType[s.type] ??= []).push(s);
    }
    const sourceOrder: { key: string; labelKey: string }[] = [
      { key: 'workspace', labelKey: 'installed.sourceLabel.workspace' },
      { key: 'prebuilt', labelKey: 'installed.sourceLabel.prebuilt' },
      { key: 'local', labelKey: 'installed.sourceLabel.local' },
    ];
    for (const { key, labelKey } of sourceOrder) {
      const skills = byType[key];
      if (skills && skills.length > 0) {
        groups.push({ key, label: t(labelKey as Parameters<typeof t>[0]), skills });
      }
    }
    return groups;
  }, [filteredInstalledSkills, t]);

  const showGrouped = sourceFilter === 'all' && groupedSkills.length > 1;

  const handleToggleSkill = useCallback(
    async (skillId: string) => {
      if (!user?.id) {
        toast({
          title: t('loginRequired'),
          description: t('loginRequiredDesc'),
          variant: 'default',
        });
        return;
      }
      try {
        if (skillId.startsWith('local::')) {
          await toggleLocalSkill(skillId);
        } else {
          await toggleSkill(skillId);
        }
      } catch (error) {
        // Check if this is a permission approval error
        if (error && typeof error === 'object' && 'name' in error && error.name === 'SkillPermissionRequiredError') {
          const err = error as {
            skillId: string;
            skillName: string;
            requiredPermissions: string[];
            description: string;
          };
          const skill = allInstalledSkills.find((s) => s.id === err.skillId);
          setPendingApproval({
            skillId: err.skillId,
            skillName: err.skillName,
            requiredPermissions: err.requiredPermissions,
            description: err.description,
            allowedDomains: skill?.allowed_domains,
          });
        } else if (error && typeof error === 'object' && 'name' in error && error.name === 'SkillBlockedError') {
          const err = error as {
            skillId: string;
            skillName: string;
            scanFindings: {
              threat_type: string;
              severity: number;
              description: string;
              line_number: number | null;
            }[];
          };
          setBlockedSkill({
            skillId: err.skillId,
            skillName: err.skillName,
            scanFindings: err.scanFindings,
          });
        } else {
          toast({ title: t('detail.toggleFailed'), variant: 'destructive' });
        }
      }
    },
    [user?.id, toggleSkill, toggleLocalSkill, t],
  );

  const handleBatchToggle = useCallback(
    async (enable: boolean) => {
      if (!user?.id) return;
      const ids = filteredInstalledSkills.map((s) => s.id);
      try {
        await batchToggleSkills(ids, enable);
        toast({
          title: enable ? t('installed.batchEnable') : t('installed.batchDisable'),
          variant: 'default',
        });
      } catch {
        toast({ title: t('detail.toggleFailed'), variant: 'destructive' });
      }
    },
    [user?.id, filteredInstalledSkills, batchToggleSkills, t],
  );

  const handleRefresh = useCallback(() => {
    fetchMarketSkills(true);
    fetchUserSkillConfig(true);
    fetchLocalSkills();
  }, [fetchMarketSkills, fetchUserSkillConfig, fetchLocalSkills]);

  const executeDestructiveAction = useCallback(
    async (skill: Skill, action: 'reset-to-default' | 'accept-upstream') => {
      try {
        if (action === 'reset-to-default') {
          const { resetPrebuiltToDefault } = await import('@/services/skill');
          await resetPrebuiltToDefault(skill.id);
          toast({ title: t('card.resetSuccess') });
        } else {
          const { acceptPrebuiltUpstream } = await import('@/services/skill');
          await acceptPrebuiltUpstream(skill.id);
          toast({ title: t('card.acceptUpstreamSuccess') });
        }
        handleRefresh();
      } catch (err: unknown) {
        const detail = err instanceof Error ? err.message : typeof err === 'string' ? err : undefined;
        const failKey = action === 'reset-to-default' ? 'card.resetFailed' : 'card.acceptUpstreamFailed';
        toast({ title: t(failKey as Parameters<typeof t>[0]), description: detail, variant: 'destructive' });
      }
    },
    [t, handleRefresh],
  );

  const handleLifecycleAction = useCallback(
    async (skill: Skill, action: SkillLifecycleAction) => {
      if (action === 'reset-to-default' || action === 'accept-upstream') {
        setPendingDestructiveAction({ skill, action });
        return;
      }
      try {
        const { updateSkillLifecycle } = await import('@/services/skill');
        await updateSkillLifecycle(skill.name, action);
        const actionKey = `${action}Success` as const;
        toast({ title: t(`card.${actionKey}` as Parameters<typeof t>[0]) });
        handleRefresh();
      } catch (err: unknown) {
        const detail = err instanceof Error ? err.message : typeof err === 'string' ? err : undefined;
        toast({ title: t('card.lifecycleActionFailed'), description: detail, variant: 'destructive' });
      }
    },
    [t, handleRefresh],
  );

  const handleApprovePermissions = useCallback(
    async (alwaysAllow: boolean, template?: string) => {
      if (!user?.id || !pendingApproval) return;

      try {
        let response: Response;

        if (template) {
          // 使用模板快速授权
          response = await fetch(`/api/v1/skills/${pendingApproval.skillId}/permissions/apply-template`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              template,
            }),
          });
        } else {
          // 单独授权指定权限
          response = await fetch(`/api/v1/skills/${pendingApproval.skillId}/permissions/grant`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              permissions: pendingApproval.requiredPermissions,
              always_allow: alwaysAllow,
            }),
          });
        }

        if (!response.ok) {
          throw new Error('Failed to grant permissions');
        }

        // Close dialog
        setPendingApproval(null);

        // Re-enable skill
        await toggleSkill(pendingApproval.skillId);

        toast({
          title: t('permissions.approved'),
          description: template ? t('permissions.templateApplied') : t('permissions.skillEnabled'),
          variant: 'default',
        });
      } catch (error) {
        toast({
          title: t('permissions.error'),
          description: error instanceof Error ? error.message : 'Failed to approve permissions',
          variant: 'destructive',
        });
      }
    },
    [user?.id, pendingApproval, toggleSkill, t],
  );

  const handleDenyPermissions = useCallback(() => {
    setPendingApproval(null);
    toast({
      title: t('permissions.denied'),
      description: t('permissions.skillNotEnabled'),
      variant: 'default',
    });
  }, [t]);

  const handleForceEnable = useCallback(async () => {
    if (!user?.id || !blockedSkill) return;

    try {
      const { enableSkill } = useSkillStore.getState();
      await enableSkill(blockedSkill.skillId, true);

      setBlockedSkill(null);

      toast({
        title: t('detail.forceEnableSuccess'),
        description: t('detail.forceEnableDesc'),
        variant: 'default',
      });
    } catch (error) {
      toast({
        title: t('detail.toggleFailed'),
        description: error instanceof Error ? error.message : 'Force enable failed',
        variant: 'destructive',
      });
    }
  }, [user?.id, blockedSkill, t]);

  const isLoggedIn = isMounted && !!user;
  const isLocal = isMounted && isLocalMode();
  const isLoading = isLoadingMarket || isLoadingLocal || isLoadingConfig;
  const enabledCount = enabledPrebuiltIds.length + enabledLocalSkillIds.length;

  if (!isInitialized) {
    return (
      <SettingsSection title={t('title')}>
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Skeleton className="h-10 w-24" />
            <Skeleton className="h-10 w-24" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="p-4 border rounded-lg space-y-3">
                <div className="flex items-center gap-3">
                  <Skeleton className="h-10 w-10 rounded-lg" />
                  <div className="flex-1 space-y-2">
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-3 w-1/2" />
                  </div>
                </div>
                <Skeleton className="h-12 w-full" />
              </div>
            ))}
          </div>
        </div>
      </SettingsSection>
    );
  }

  return (
    <div className="space-y-6">
      <SettingsSection title={t('title')} description={t('description')}>
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as TabValue)}>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
            <TabsList className="grid w-full sm:w-auto grid-cols-2">
              <TabsTrigger value="discover" className="gap-2">
                <IconExplore className="h-4 w-4" />
                {t('tabs.discover')}
              </TabsTrigger>
              <TabsTrigger value="installed" className="gap-2">
                <IconFolder className="h-4 w-4" />
                {t('tabs.installed')}
                {unreviewedCount > 0 && <span className="flex h-2 w-2 rounded-full bg-red-500" />}
                {enabledCount > 0 && (
                  <Badge variant="secondary" className="ml-1 px-1.5 py-0 text-xs">
                    {enabledCount}
                  </Badge>
                )}
              </TabsTrigger>
            </TabsList>

            <div className="flex items-center gap-2">
              {isLoggedIn && activeTab === 'installed' && (
                <>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={handleExport}
                    disabled={isSyncing}
                    className="h-9 w-9"
                    title={t('installed.export')}
                  >
                    <IconDownload className="w-4 h-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setIsBatchImportOpen(true)}
                    disabled={isSyncing}
                    className="h-9 w-9"
                    title={t('installed.import')}
                  >
                    <IconUpload className={cn('h-4 w-4', isSyncing && 'animate-pulse')} />
                  </Button>
                </>
              )}
              <Button variant="ghost" size="icon" onClick={handleRefresh} disabled={isLoading} className="h-9 w-9">
                <IconRefresh className={cn('h-4 w-4', isLoading && 'animate-spin')} />
              </Button>
            </div>
          </div>

          {/* Discover Tab */}
          <TabsContent value="discover" className="mt-0">
            <SkillDiscoverTab onInstalled={handleRefresh} />
          </TabsContent>

          {/* Installed Tab */}
          <TabsContent value="installed" className="mt-0 space-y-4">
            {/* Skill Sync Status */}
            {isLoggedIn && <SkillSyncIndicator />}

            {/* Skill Draft Review Panel */}
            {isLoggedIn && <SkillDraftReviewPanel className="mb-4" />}

            {/* Skill History Panel (Auto-Learned) */}
            {isLoggedIn && <SkillHistoryPanel className="mb-4" />}

            {/* Evolution Strategy Config */}
            {isLoggedIn && <EvolutionStrategyConfig />}

            {/* Curator settings */}
            {isLoggedIn && (
              <CuratorSettingsPanel className="my-4 rounded-lg border bg-card p-4" onSweepComplete={handleRefresh} />
            )}

            {/* Local paths config (Tauri mode only) */}
            {isLocal && isLoggedIn && user && (
              <Collapsible open={localPathsOpen} onOpenChange={setLocalPathsOpen}>
                <CollapsibleTrigger asChild>
                  <Button variant="outline" size="sm" className="gap-2 mb-2">
                    <IconChevronDown className={cn('h-4 w-4 transition-transform', localPathsOpen && 'rotate-180')} />
                    {t('installed.localPathsTitle')}
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <LocalPathsConfig className="mb-4" />
                </CollapsibleContent>
              </Collapsible>
            )}

            {/* Archived skills shortcut banner */}
            {archivedCount > 0 && statusFilter !== 'archived' && (
              <div className="flex items-center justify-between bg-muted/40 border rounded-full px-3 py-2.5 text-sm mb-2">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <IconFolder className="h-4 w-4" />
                  <span>{t('installed.archivedHidden', { count: archivedCount })}</span>
                </div>
                <Button
                  variant="link"
                  size="sm"
                  className="h-auto p-0 text-xs font-medium"
                  onClick={() => setStatusFilter('archived')}
                >
                  {t('installed.viewArchived')}
                </Button>
              </div>
            )}

            {/* Filter bar */}
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="relative flex-1">
                <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder={t('installed.searchPlaceholder')}
                  value={installedSearch}
                  onChange={(e) => setInstalledSearch(e.target.value)}
                  className="pl-9"
                />
              </div>

              <Select value={sourceFilter} onValueChange={(v) => setSourceFilter(v as SkillSourceFilter)}>
                <SelectTrigger className="w-full sm:w-[160px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('installed.sourceFilter.all')}</SelectItem>
                  <SelectItem value="prebuilt">{t('installed.sourceFilter.prebuilt')}</SelectItem>
                  <SelectItem value="local">{t('installed.sourceFilter.local')}</SelectItem>
                  <SelectItem value="workspace">{t('installed.sourceFilter.workspace')}</SelectItem>
                </SelectContent>
              </Select>

              <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as SkillStatusFilter)}>
                <SelectTrigger className="w-full sm:w-[140px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('installed.statusFilter.all')}</SelectItem>
                  <SelectItem value="ready">{t('installed.statusFilter.ready')}</SelectItem>
                  <SelectItem value="needs-setup">{t('installed.statusFilter.needs-setup')}</SelectItem>
                  <SelectItem value="disabled">{t('installed.statusFilter.disabled')}</SelectItem>
                  <SelectItem value="stale">{t('card.stale')}</SelectItem>
                  <SelectItem value="archived">{t('card.archived')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Batch actions & count */}
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">
                {t('installed.count', { count: filteredInstalledSkills.length })}
              </span>
              {isLoggedIn && filteredInstalledSkills.length > 0 && (
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={() => handleBatchToggle(true)}>
                    {t('installed.batchEnable')}
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => handleBatchToggle(false)}>
                    {t('installed.batchDisable')}
                  </Button>
                </div>
              )}
            </div>

            {/* Skill list — grouped or flat */}
            {showGrouped ? (
              <div className="space-y-4">
                {groupedSkills.map((group) => {
                  const isCollapsed = collapsedGroups.has(group.key);
                  return (
                    <div key={group.key}>
                      <button
                        type="button"
                        className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors mb-2"
                        onClick={() => toggleGroup(group.key)}
                      >
                        {isCollapsed ? (
                          <IconChevronRight className="w-3.5 h-3.5" />
                        ) : (
                          <IconChevronDown className="w-3.5 h-3.5" />
                        )}
                        {group.label}
                        <Badge variant="secondary" className="text-xs px-1.5 py-0">
                          {group.skills.length}
                        </Badge>
                      </button>
                      {!isCollapsed && (
                        <SkillList
                          skills={group.skills}
                          isSkillEnabled={isSkillEnabled}
                          isLoading={false}
                          emptyStateType="search"
                          onToggle={handleToggleSkill}
                          onViewDetails={setDetailSkill}
                          onLifecycleAction={handleLifecycleAction}
                          onManageInstances={setInstanceManagerSkill}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <SkillList
                skills={filteredInstalledSkills}
                isSkillEnabled={isSkillEnabled}
                isLoading={isLoading}
                emptyStateType={
                  installedSearch || sourceFilter !== 'all' || statusFilter !== 'all' ? 'search' : 'market'
                }
                onToggle={handleToggleSkill}
                onViewDetails={setDetailSkill}
                onLifecycleAction={handleLifecycleAction}
                onManageInstances={setInstanceManagerSkill}
              />
            )}
          </TabsContent>
        </Tabs>
      </SettingsSection>

      <SkillDetailSheet
        skill={detailSkill}
        open={!!detailSkill}
        isEnabled={detailSkill ? isSkillEnabled(detailSkill.id) : false}
        onOpenChange={(open) => !open && setDetailSkill(null)}
        onToggle={handleToggleSkill}
        onTrustChange={() => fetchMarketSkills(true)}
        onLifecycleAction={handleLifecycleAction}
      />

      <SkillPermissionApprovalDialog
        open={!!pendingApproval}
        request={pendingApproval as any}
        onApprove={handleApprovePermissions}
        onDeny={handleDenyPermissions}
        onOpenChange={(open) => !open && setPendingApproval(null)}
      />

      <AlertDialog open={!!blockedSkill} onOpenChange={(v) => !v && setBlockedSkill(null)}>
        <AlertDialogContent className="max-w-lg">
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <IconShieldAlert className="h-5 w-5 text-red-500" />
              {t('detail.scanBlockedTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-3">
                <p>
                  {t('detail.scanBlockedDesc', {
                    name: blockedSkill?.skillName,
                    count: blockedSkill?.scanFindings.length || 0,
                  })}
                </p>
                <div className="space-y-2 max-h-48 overflow-y-auto rounded-full border p-3 bg-muted/30">
                  {blockedSkill?.scanFindings.map((finding, idx) => (
                    <div key={idx} className="flex items-start gap-2 text-sm">
                      <Badge
                        variant="outline"
                        className={cn(
                          'text-[10px] shrink-0 mt-0.5',
                          finding.severity === 1 && 'text-yellow-500',
                          finding.severity === 2 && 'text-orange-500',
                          finding.severity === 3 && 'text-red-500',
                          finding.severity === 4 && 'text-red-700 dark:text-red-400',
                        )}
                      >
                        {finding.severity === 1 && 'LOW'}
                        {finding.severity === 2 && 'MEDIUM'}
                        {finding.severity === 3 && 'HIGH'}
                        {finding.severity === 4 && 'CRITICAL'}
                      </Badge>
                      <span className="text-foreground">{finding.description}</span>
                    </div>
                  ))}
                </div>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('detail.scanCancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleForceEnable} className="bg-red-600 hover:bg-red-700 text-white">
              {t('detail.scanForceEnable')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Destructive action confirmation for prebuilt skill reset/accept */}
      <AlertDialog open={!!pendingDestructiveAction} onOpenChange={(v) => !v && setPendingDestructiveAction(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pendingDestructiveAction?.action === 'reset-to-default'
                ? t('card.confirmResetTitle')
                : t('card.confirmAcceptTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pendingDestructiveAction?.action === 'reset-to-default'
                ? t('card.confirmResetDesc', { name: pendingDestructiveAction?.skill.name })
                : t('card.confirmAcceptDesc', { name: pendingDestructiveAction?.skill.name })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('card.cancelAction')}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (pendingDestructiveAction) {
                  executeDestructiveAction(pendingDestructiveAction.skill, pendingDestructiveAction.action);
                }
                setPendingDestructiveAction(null);
              }}
            >
              {t('card.confirmAction')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Skill Instance Manager Dialog */}
      {instanceManagerSkill && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm">
          <div className="fixed left-1/2 top-1/2 z-50 w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-background p-6 shadow-lg">
            <SkillInstanceManager skillName={instanceManagerSkill} onClose={() => setInstanceManagerSkill(null)} />
          </div>
        </div>
      )}

      {/* Batch Import Dialog */}
      <SkillBatchImportDialog
        open={isBatchImportOpen}
        onOpenChange={setIsBatchImportOpen}
        onImportComplete={() => {
          fetchLocalSkills();
          fetchUserSkillConfig(true);
        }}
      />
    </div>
  );
});

SkillsSection.displayName = 'SkillsSection';

export default SkillsSection;
