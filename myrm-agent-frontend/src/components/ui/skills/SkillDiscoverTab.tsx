'use client';

import { memo, useState, useCallback, useMemo, useRef, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import {
  Search,
  Download,
  Star,
  ExternalLink,
  Loader2,
  CheckCircle,
  Globe,
  ArrowUpCircle,
  ArrowDownWideNarrow,
  Trash2,
  Store,
  MessageSquare,
  Link as LinkIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { toast } from '@/hooks/useToast';
import { useSkillDiscovery } from '@/hooks/useSkillDiscovery';
import type { DiscoverySearchResult } from '@/services/skill';
import ScanConfirmDialog from './ScanConfirmDialog';
import SkillUrlImportDialog from './SkillUrlImportDialog';
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

import { useSearchParams, useRouter, usePathname } from 'next/navigation';

type SortMode = 'default' | 'stars' | 'downloads';

const SOURCE_ICONS: Record<string, typeof Globe> = {
  prebuilt: Globe,
  github: Globe,
  skills_sh: Globe,
  clawhub: Store,
  lobehub: MessageSquare,
};

const SOURCE_COLORS: Record<string, string> = {
  prebuilt: 'text-accent-warm',
  github: 'text-muted-foreground',
  skills_sh: 'text-primary',
  clawhub: 'text-accent-warm',
  lobehub: 'text-primary',
};

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
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const initialLoadRef = useRef(false);

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
    uninstall,
    clearPreview,
  } = useSkillDiscovery();

  useEffect(() => {
    if (!initialLoadRef.current) {
      initialLoadRef.current = true;
      search('');
    }
  }, [search]);

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
    if (activeTag !== 'all') {
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

      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => search(value), 500);
    },
    [search],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        if (debounceRef.current) clearTimeout(debounceRef.current);
        search(query);
      }
    },
    [query, search],
  );

  const doInstall = useCallback(
    async (skill: DiscoverySearchResult) => {
      const success = await install(skill.id, skill.source);
      if (success) {
        toast({ title: `${t('installed')} ${skill.name}` });
        onInstalled?.();
      } else {
        toast({ title: t('installFailed'), variant: 'destructive' });
      }
    },
    [install, t, onInstalled],
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

  const [uninstallDialogOpen, setUninstallDialogOpen] = useState(false);
  const [pendingUninstall, setPendingUninstall] = useState<DiscoverySearchResult | null>(null);

  const handleUninstall = useCallback((skill: DiscoverySearchResult) => {
    setPendingUninstall(skill);
    setUninstallDialogOpen(true);
  }, []);

  const handleConfirmUninstall = useCallback(async () => {
    setUninstallDialogOpen(false);
    if (!pendingUninstall) return;

    const skillId = `local::${pendingUninstall.name}`;
    const success = await uninstall(skillId);
    if (success) {
      toast({ title: `${t('uninstalled')} ${pendingUninstall.name}` });
      onInstalled?.();
    } else {
      toast({ title: t('uninstallFailed'), variant: 'destructive' });
    }
    setPendingUninstall(null);
  }, [pendingUninstall, uninstall, t, onInstalled]);

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
      if (debounceRef.current) clearTimeout(debounceRef.current);
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

      {searchError && <p className="text-sm text-destructive">{searchError}</p>}
      {installError && <p className="text-sm text-destructive">{installError}</p>}

      {filteredAndSorted.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {filteredAndSorted.map((skill) => (
            <SkillResultCard
              key={`${skill.source}-${skill.id}`}
              skill={skill}
              isInstalling={isInstalling === skill.id}
              isPreviewing={isPreviewing === skill.id}
              isUninstalling={isUninstalling === `local::${skill.name}`}
              justInstalled={installSuccess === skill.name}
              onInstall={handleInstall}
              onUninstall={handleUninstall}
              t={t}
            />
          ))}
        </div>
      ) : !isSearching ? (
        <div className="text-center py-12 text-muted-foreground">
          <Search className="h-12 w-12 mx-auto mb-3 opacity-30" />
          <p className="font-medium">{t('noResults')}</p>
          <p className="text-sm mt-1">{t('noResultsDesc')}</p>
        </div>
      ) : null}

      <ScanConfirmDialog
        open={scanDialogOpen}
        previewResult={previewResult}
        onConfirm={handleConfirmInstall}
        onCancel={handleCancelInstall}
      />

      <AlertDialog
        open={uninstallDialogOpen}
        onOpenChange={(v) => {
          if (!v) {
            setUninstallDialogOpen(false);
            setPendingUninstall(null);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Trash2 className="h-5 w-5 text-destructive" />
              {t('uninstall')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('uninstallConfirm')}
              {pendingUninstall && <span className="font-medium text-foreground"> {pendingUninstall.name}</span>}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('scanCancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmUninstall}
              className="bg-destructive hover:bg-destructive/90 text-destructive-foreground"
            >
              <Trash2 className="h-4 w-4 mr-1.5" />
              {t('uninstall')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <SkillUrlImportDialog
        open={urlImportOpen}
        onOpenChange={setUrlImportOpen}
        onInstalled={() => {
          onInstalled?.();
          search(query);
        }}
        initialUrl={initialImportUrl}
      />
    </div>
  );
});

SkillDiscoverTab.displayName = 'SkillDiscoverTab';
export default SkillDiscoverTab;

// ========== Tag Button ==========

function TagButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'px-2.5 py-1 text-xs rounded-lg transition-colors',
        active
          ? 'bg-primary text-primary-foreground'
          : 'bg-muted text-muted-foreground hover:bg-accent border border-border',
      )}
    >
      {children}
    </button>
  );
}

function TranslatedTag({ tag }: { tag: string }) {
  const tSkills = useTranslations('settings.skills');
  const key = `tagLabels.${tag.toLowerCase()}` as Parameters<typeof tSkills>[0];
  return <>{tSkills.has(key) ? tSkills(key) : tag}</>;
}

// ========== Skill Result Card ==========

interface SkillResultCardProps {
  skill: DiscoverySearchResult;
  isInstalling: boolean;
  isPreviewing: boolean;
  isUninstalling: boolean;
  justInstalled: boolean;
  onInstall: (skill: DiscoverySearchResult) => void;
  onUninstall: (skill: DiscoverySearchResult) => void;
  t: ReturnType<typeof useTranslations>;
}

const SkillResultCard = memo(
  ({
    skill,
    isInstalling,
    isPreviewing,
    isUninstalling,
    justInstalled,
    onInstall,
    onUninstall,
    t,
  }: SkillResultCardProps) => {
    const SourceIcon = SOURCE_ICONS[skill.source] || Globe;
    const sourceColor = SOURCE_COLORS[skill.source] || 'text-gray-500';
    const sourceLabel = t(`source.${skill.source}` as Parameters<typeof t>[0]);
    const isBusy = isInstalling || isPreviewing || isUninstalling;
    const isLocalInstalled = !!skill.installed_version;

    return (
      <div
        className={cn('p-4 rounded-lg border bg-card transition-colors', 'hover:border-primary/30 hover:bg-accent/30')}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h4 className="font-medium text-sm truncate">{skill.name}</h4>
              <Badge variant="outline" className={cn('text-xs shrink-0 gap-1', sourceColor)}>
                <SourceIcon className="h-3 w-3" />
                {sourceLabel}
              </Badge>
              {skill.upgrade_available && (
                <Badge
                  variant="secondary"
                  className="text-xs shrink-0 gap-1 text-amber-600 dark:text-amber-400 bg-amber-500/10"
                >
                  <ArrowUpCircle className="h-3 w-3" />
                  {t('updateAvailable')}
                </Badge>
              )}
            </div>

            <div className="flex items-center gap-3 text-xs text-muted-foreground mb-2">
              {skill.author && <span>{skill.author}</span>}
              {skill.stars > 0 && (
                <span className="flex items-center gap-0.5">
                  <Star className="h-3 w-3" />
                  {skill.stars}
                </span>
              )}
              {skill.installed_version && (
                <span className="text-accent-warm font-medium">
                  v{skill.installed_version}
                  {skill.upgrade_available && skill.version && ` → v${skill.version}`}
                </span>
              )}
            </div>

            <p className="text-xs text-muted-foreground line-clamp-2">{skill.description || 'No description'}</p>

            {skill.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {skill.tags.slice(0, 3).map((tag) => (
                  <Badge key={tag} variant="secondary" className="text-[10px] px-1.5 py-0">
                    <TranslatedTag tag={tag} />
                  </Badge>
                ))}
              </div>
            )}
          </div>

          <div className="flex flex-col items-end gap-1 shrink-0">
            <Button
              size="sm"
              variant={justInstalled ? 'outline' : skill.upgrade_available ? 'secondary' : 'default'}
              disabled={isBusy || justInstalled}
              onClick={() => onInstall(skill)}
              className="gap-1.5"
            >
              {isPreviewing ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  {t('scanning')}
                </>
              ) : isInstalling ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  {t('installing')}
                </>
              ) : justInstalled ? (
                <>
                  <CheckCircle className="h-3.5 w-3.5 text-green-500" />
                  {t('installed')}
                </>
              ) : skill.upgrade_available ? (
                <>
                  <ArrowUpCircle className="h-3.5 w-3.5" />
                  {t('update')}
                </>
              ) : (
                <>
                  <Download className="h-3.5 w-3.5" />
                  {t('install')}
                </>
              )}
            </Button>
            {isLocalInstalled && !skill.upgrade_available && (
              <Button
                size="sm"
                variant="ghost"
                disabled={isBusy}
                onClick={() => onUninstall(skill)}
                className="gap-1.5 text-destructive hover:text-destructive"
              >
                {isUninstalling ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    {t('uninstalling')}
                  </>
                ) : (
                  <>
                    <Trash2 className="h-3.5 w-3.5" />
                    {t('uninstall')}
                  </>
                )}
              </Button>
            )}
            {skill.readme_url && (
              <a
                href={skill.readme_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1"
              >
                <ExternalLink className="h-3 w-3" />
                README
              </a>
            )}
          </div>
        </div>
      </div>
    );
  },
);

SkillResultCard.displayName = 'SkillResultCard';
