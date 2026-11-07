'use client';

import { memo, useState, useCallback, useMemo, useRef, useEffect, useLayoutEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Search, Loader2, ArrowDownWideNarrow, Link as LinkIcon } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { toast } from '@/hooks/shared/useToast';
import { useSkillDiscovery } from '@/hooks/agent/useSkillDiscovery';
import type { DiscoveryInstallResponse, DiscoverySearchResult } from '@/services/skill';
import ScanConfirmDialog from './ScanConfirmDialog';
import SkillUrlImportDialog from './SkillUrlImportDialog';
import SkillSourcesPanel from './SkillSourcesPanel';
import SkillRegistryMirrorPanel from './SkillRegistryMirrorPanel';
import { showDiscoveryInstallResultToast } from './skillInstallRollbackToastAction';
import { launchSkillTrialRun } from '@/services/skillTrialRunner';
import { isWorkBuddyMigrationSkill } from '@/services/skillsMigrationMap';
import useChatStore from '@/store/useChatStore';

import { useSearchParams, useRouter, usePathname } from 'next/navigation';
import { SkillResultCard, TagButton, TranslatedTag } from './SkillDiscoverResultCard';
import { SkillUninstallDialogs, useSkillUninstall } from './SkillUninstallFlow';

type SortMode = 'default' | 'stars' | 'downloads';

const SORT_OPTIONS: { value: SortMode; labelKey: string }[] = [
  { value: 'default', labelKey: 'sortDefault' },
  { value: 'stars', labelKey: 'sortStars' },
  { value: 'downloads', labelKey: 'sortDownloads' },
];

interface SkillDiscoverTabProps {
  onInstalled?: () => void;
}

const SkillDiscoverTab = memo(({ onInstalled }: SkillDiscoverTabProps) => {
  const t = useTranslations('settings.skills.discover');
  const [query, setQuery] = useState('');
  const [activeTag, setActiveTag] = useState('all');
  const [sortMode, setSortMode] = useState<SortMode>('default');
  const [scanDialogOpen, setScanDialogOpen] = useState(false);
  const [urlImportOpen, setUrlImportOpen] = useState(false);
  const [initialImportUrl, setInitialImportUrl] = useState('');
  const [pendingSkill, setPendingSkill] = useState<DiscoverySearchResult | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const mountAgentId = useChatStore((state) => state.agentConfig?.agentId) ?? 'builtin-general';

  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    const action = searchParams.get('action');
    const url = searchParams.get('url');
    if (action === 'install' && url) {
      setInitialImportUrl(url);
      setUrlImportOpen(true);

      // Clear URL parameters to prevent re-triggering on refresh
      const newParams = new URLSearchParams(searchParams.toString());
      newParams.delete('action');
      newParams.delete('url');
      router.replace(`${pathname}?${newParams.toString()}`, { scroll: false });
    }
  }, [searchParams, pathname, router]);
  const {
    results,
    isSearching,
    isInstalling,
    isPreviewing,
    isUninstalling,
    previewResult,
    searchError,
    installError,
    installSuccess,
    search,
    preview,
    install,
    update,
    uninstall,
    clearPreview,
  } = useSkillDiscovery({ agentId: mountAgentId, mountToAgent: true });

  const runSearch = useCallback(
    async (value: string) => {
      setHasSearched(true);
      await search(value);
    },
    [search],
  );

  const availableTags = useMemo(() => {
    const tagCounts = new Map<string, number>();
    for (const skill of results) {
      for (const tag of skill.tags) {
        tagCounts.set(tag, (tagCounts.get(tag) ?? 0) + 1);
      }
    }
    return [...tagCounts.entries()].sort((a, b) => b[1] - a[1]).map(([tag]) => tag);
  }, [results]);

  const filteredAndSorted = useMemo(() => {
    let filtered = results;
    if (activeTag === 'wb-top20') {
      filtered = results.filter((s) => isWorkBuddyMigrationSkill(s.id) || isWorkBuddyMigrationSkill(s.name));
    } else if (activeTag !== 'all') {
      filtered = results.filter((s) => s.tags.includes(activeTag));
    }
    if (sortMode === 'stars') {
      filtered = [...filtered].sort((a, b) => b.stars - a.stars);
    } else if (sortMode === 'downloads') {
      filtered = [...filtered].sort((a, b) => b.downloads - a.downloads);
    }
    return filtered;
  }, [results, activeTag, sortMode]);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;
      setQuery(value);
      setActiveTag('all');

      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
      debounceRef.current = setTimeout(() => runSearch(value), 500);
    },
    [runSearch],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        if (debounceRef.current) {
          clearTimeout(debounceRef.current);
        }
        runSearch(query);
      }
    },
    [query, runSearch],
  );

  const showInstallToast = useCallback(
    (skill: DiscoverySearchResult, response: DiscoveryInstallResponse, marketUpdate: boolean) => {
      showDiscoveryInstallResultToast({
        skillName: skill.name,
        response,
        marketUpdate,
        t,
        onInstalled,
        extraCallbacks: {
          onTrialRun: () => {
            launchSkillTrialRun({
              skillId: skill.id,
              skillName: skill.name,
              description: skill.description,
            });
          },
        },
      });
    },
    [t, onInstalled],
  );

  useLayoutEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    const host = window.location.hostname;
    if (host !== 'localhost' && host !== '127.0.0.1') {
      return;
    }
    window.__MYRM_E2E_SKILLS_DISCOVER__ = {
      showInstallResultToast: (payload) => {
        showDiscoveryInstallResultToast({
          skillName: payload.skillName,
          response: payload.response,
          marketUpdate: payload.marketUpdate,
          t,
          onInstalled,
        });
      },
    };
    return () => {
      delete window.__MYRM_E2E_SKILLS_DISCOVER__;
    };
  }, [t, onInstalled]);

  const doInstall = useCallback(
    async (skill: DiscoverySearchResult) => {
      const isMarketUpdate = Boolean(skill.upgrade_available && skill.installed_version);
      const response = isMarketUpdate
        ? await update(skill.name, skill.id, skill.source)
        : await install(skill.id, skill.source);
      if (response) {
        showInstallToast(skill, response, isMarketUpdate);
        onInstalled?.();
      } else {
        toast({
          title: isMarketUpdate ? t('updateFailed') : t('installFailed'),
          variant: 'destructive',
        });
      }
    },
    [install, update, t, onInstalled, showInstallToast],
  );

  const handleInstall = useCallback(
    async (skill: DiscoverySearchResult) => {
      if (skill.source === 'prebuilt') {
        await doInstall(skill);
        return;
      }
      setPendingSkill(skill);
      const result = await preview(skill.id, skill.source);
      if (!result) {
        toast({ title: t('previewFailed'), variant: 'destructive' });
        return;
      }
      if (result.is_clean) {
        await doInstall(skill);
      } else {
        setScanDialogOpen(true);
      }
    },
    [preview, doInstall, t],
  );

  const { requestUninstall, dialogProps } = useSkillUninstall({ uninstall, onInstalled });

  const handleConfirmInstall = useCallback(async () => {
    setScanDialogOpen(false);
    if (pendingSkill) {
      await doInstall(pendingSkill);
      setPendingSkill(null);
      clearPreview();
    }
  }, [pendingSkill, doInstall, clearPreview]);

  const handleCancelInstall = useCallback(() => {
    setScanDialogOpen(false);
    setPendingSkill(null);
    clearPreview();
  }, [clearPreview]);

  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={query}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder={t('searchPlaceholder')}
            className="pl-9 pr-4"
          />
          {isSearching && (
            <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground" />
          )}
        </div>
        <Button variant="outline" onClick={() => setUrlImportOpen(true)}>
          <LinkIcon className="h-4 w-4 mr-2" />
          {t('importUrl')}
        </Button>
      </div>

      {(availableTags.length > 0 || sortMode !== 'default') && (
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-1 flex-wrap flex-1 min-w-0">
            <TagButton active={activeTag === 'all'} onClick={() => setActiveTag('all')}>
              {t('allTags')}
            </TagButton>
            <TagButton active={activeTag === 'wb-top20'} onClick={() => setActiveTag('wb-top20')}>
              <span className="font-medium text-amber-600 dark:text-amber-400">WorkBuddy Top 20</span>
            </TagButton>
            {availableTags.slice(0, 8).map((tag) => (
              <TagButton key={tag} active={activeTag === tag} onClick={() => setActiveTag(tag)}>
                <TranslatedTag tag={tag} />
              </TagButton>
            ))}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <ArrowDownWideNarrow className="h-3.5 w-3.5 text-muted-foreground" />
            {SORT_OPTIONS.map((opt) => (
              <TagButton key={opt.value} active={sortMode === opt.value} onClick={() => setSortMode(opt.value)}>
                {t(opt.labelKey as Parameters<typeof t>[0])}
              </TagButton>
            ))}
          </div>
        </div>
      )}

      {searchError && <p className="text-sm text-destructive-text">{searchError}</p>}
      {installError && <p className="text-sm text-destructive-text">{installError}</p>}

      {filteredAndSorted.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {filteredAndSorted.map((skill) => (
            <SkillResultCard
              key={`${skill.source}-${skill.id}`}
              skill={skill}
              isInstalling={isInstalling === skill.id}
              isPreviewing={isPreviewing === skill.id}
              isUninstalling={isUninstalling === skill.installed_skill_id}
              justInstalled={installSuccess === skill.name}
              onInstall={handleInstall}
              onUninstall={requestUninstall}
              t={t}
            />
          ))}
        </div>
      ) : !isSearching && hasSearched ? (
        <div className="text-center py-12 text-muted-foreground">
          <Search className="h-12 w-12 mx-auto mb-3 opacity-30" />
          <p className="font-medium">{t('noResults')}</p>
          <p className="text-sm mt-1">{t('noResultsDesc')}</p>
        </div>
      ) : !isSearching && !hasSearched ? (
        <div className="text-center py-12 text-muted-foreground">
          <Search className="h-12 w-12 mx-auto mb-3 opacity-30" />
          <p className="font-medium">{t('browseEmptyTitle')}</p>
          <p className="text-sm mt-1">{t('browseEmptyDesc')}</p>
        </div>
      ) : null}

      <ScanConfirmDialog
        open={scanDialogOpen}
        previewResult={previewResult}
        onConfirm={handleConfirmInstall}
        onCancel={handleCancelInstall}
      />

      <SkillUninstallDialogs {...dialogProps} />

      <SkillUrlImportDialog
        open={urlImportOpen}
        onOpenChange={setUrlImportOpen}
        onInstalled={() => {
          onInstalled?.();
          search(query);
        }}
        initialUrl={initialImportUrl}
      />

      {/* Custom Sources Management */}
      <div className="border-t pt-4 mt-4">
        <SkillRegistryMirrorPanel />
        <SkillSourcesPanel />
      </div>
    </div>
  );
});

SkillDiscoverTab.displayName = 'SkillDiscoverTab';
export default SkillDiscoverTab;
