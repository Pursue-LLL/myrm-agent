'use client';

import { memo, useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import {
  Calendar,
  Tag,
  Package,
  Trash2,
  Loader2,
  ExternalLink,
  Shield,
  ShieldCheck,
  ShieldAlert,
  ShieldX,
  AlertTriangle,
  Terminal,
  Key,
  Settings,
  User,
  ChevronDown,
  Lock,
  LockOpen,
  Pin,
  PinOff,
  Archive,
  RotateCcw,
  Zap,
  ArrowUpCircle,
  Undo2,
  Download,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/primitives/sheet';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { Input } from '@/components/primitives/input';
import { toast } from '@/hooks/useToast';
import {
  getSkillFile,
  getSkillEnvVars,
  updateSkillEnvVars,
  trustSkill,
  untrustSkill,
  toggleEvolutionLock,
} from '@/services/skill';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import CodeBlock from '@/components/features/markdown-render-tools/CodeBlock';
import { getChildrenAsText } from '@/lib/utils/reactUtils';
import type { Skill, SkillTrap, SecurityScanSummary } from '@/store/skill/types';
import { SkillQualityGuardian } from './SkillQualityGuardian';
import { SkillVersionsPanel } from './SkillVersionsPanel';
import { getCategoryIcon, getCategoryColor } from './skillCategories';
import { IconAlertTriangle } from '@/components/features/icons/PremiumIcons';
import SkillExportDialog from './SkillExportDialog';

function stripYamlFrontmatter(content: string): string {
  const match = content.match(/^---\s*\n[\s\S]*?\n---\s*\n/);
  return match ? content.slice(match[0].length) : content;
}

const trustColors: Record<string, string> = {
  builtin: 'text-accent-warm',
  installed: 'text-primary',
  untrusted: 'text-amber-600 dark:text-amber-400',
};

interface SkillDetailSheetProps {
  skill: Skill | null;
  open: boolean;
  isEnabled: boolean;
  showDeleteButton?: boolean;
  onOpenChange: (open: boolean) => void;
  onToggle?: (skillId: string) => Promise<void>;
  onDelete?: (skill: Skill) => Promise<void>;
  onTrustChange?: () => void;
  onLifecycleAction?: (skill: Skill, action: import('@/store/skill/types').SkillLifecycleAction) => void;
}

const SkillDetailSheet = memo(
  ({
    skill,
    open,
    isEnabled,
    showDeleteButton = false,
    onOpenChange,
    onToggle,
    onDelete,
    onTrustChange,
    onLifecycleAction,
  }: SkillDetailSheetProps) => {
    const t = useTranslations('settings.skills');
    const [skillContent, setSkillContent] = useState<string>('');
    const [isLoadingContent, setIsLoadingContent] = useState(false);
    const [isToggling, setIsToggling] = useState(false);
    const [isDeleting, setIsDeleting] = useState(false);
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
    const [showTrustConfirm, setShowTrustConfirm] = useState(false);
    const [isTrusting, setIsTrusting] = useState(false);
    const [showOptimizeInput, setShowOptimizeInput] = useState(false);
    const [optimizeInstruction, setOptimizeInstruction] = useState('');
    const [isOptimizing, setIsOptimizing] = useState(false);
    const [isEvolutionLocked, setIsEvolutionLocked] = useState(false);
    const [isTogglingLock, setIsTogglingLock] = useState(false);
    const [showExportDialog, setShowExportDialog] = useState(false);

    const [envVars, setEnvVars] = useState<Record<string, string>>({});
    const [envVarsDirty, setEnvVarsDirty] = useState(false);
    const [isSavingEnv, setIsSavingEnv] = useState(false);

    const hasRequirements = useMemo(() => {
      if (!skill) return false;
      const { bins, env, config } = skill.requires;
      return bins.length > 0 || env.length > 0 || config.length > 0;
    }, [skill]);

    const hasEnvRequirements = useMemo(() => (skill?.requires.env.length ?? 0) > 0 || !!skill?.primary_env, [skill]);

    useEffect(() => {
      if (skill && open) {
        setIsEvolutionLocked(skill.evolution_locked);
        setIsLoadingContent(true);
        getSkillFile(skill.id, 'SKILL.md')
          .then(setSkillContent)
          .catch(() => setSkillContent(''))
          .finally(() => setIsLoadingContent(false));

        if (skill.requires.env.length > 0 || skill.primary_env) {
          getSkillEnvVars(skill.id)
            .then((res) => {
              setEnvVars(res.env_vars);
              setEnvVarsDirty(false);
            })
            .catch(() => setEnvVars({}));
        } else {
          setEnvVars({});
          setEnvVarsDirty(false);
        }
      }
    }, [skill, open]);

    const handleToggle = useCallback(async () => {
      if (!skill || !onToggle) return;
      setIsToggling(true);
      try {
        await onToggle(skill.id);
        toast({
          title: isEnabled ? t('detail.disableSuccess') : t('detail.enableSuccess'),
          description: isEnabled
            ? t('detail.disableSuccessDesc', { name: skill.name })
            : t('detail.enableSuccessDesc', { name: skill.name }),
        });
      } catch {
        toast({ title: t('detail.toggleFailed'), variant: 'destructive' });
      } finally {
        setIsToggling(false);
      }
    }, [skill, onToggle, isEnabled, t]);

    const handleDelete = useCallback(async () => {
      if (!skill || !onDelete) return;
      setIsDeleting(true);
      try {
        await onDelete(skill);
        toast({
          title: t('detail.deleteSuccess'),
          description: t('detail.deleteSuccessDesc', { name: skill.name }),
        });
        onOpenChange(false);
      } catch {
        toast({ title: t('detail.deleteFailed'), variant: 'destructive' });
      } finally {
        setIsDeleting(false);
        setShowDeleteConfirm(false);
      }
    }, [skill, onDelete, onOpenChange, t]);

    const handleEnvVarChange = useCallback((key: string, value: string) => {
      setEnvVars((prev) => ({ ...prev, [key]: value }));
      setEnvVarsDirty(true);
    }, []);

    const handleSaveEnvVars = useCallback(async () => {
      if (!skill) return;
      setIsSavingEnv(true);
      try {
        await updateSkillEnvVars(skill.id, envVars);
        setEnvVarsDirty(false);
        toast({ title: t('card.keysSaved') });
      } catch {
        toast({ title: t('card.keysSaveFailed'), variant: 'destructive' });
      } finally {
        setIsSavingEnv(false);
      }
    }, [skill, envVars, t]);

    const isUserTrustable = skill?.trust === 'installed' && skill?.type !== 'local';
    const isUserTrusted = !!skill?.user_trusted;

    const handleTrust = useCallback(async () => {
      if (!skill) return;
      setIsTrusting(true);
      try {
        await trustSkill(skill.id);
        toast({
          title: t('card.trustSuccess'),
          description: t('card.trustSuccessDesc', { name: skill.name }),
        });
        onTrustChange?.();
        onOpenChange(false);
      } catch {
        toast({ title: t('card.trustFailed'), variant: 'destructive' });
      } finally {
        setIsTrusting(false);
        setShowTrustConfirm(false);
      }
    }, [skill, t, onOpenChange, onTrustChange]);

    const handleUntrust = useCallback(async () => {
      if (!skill) return;
      setIsTrusting(true);
      try {
        await untrustSkill(skill.id);
        toast({
          title: t('card.untrustSuccess'),
          description: t('card.untrustSuccessDesc', { name: skill.name }),
        });
        onTrustChange?.();
        onOpenChange(false);
      } catch {
        toast({ title: t('card.trustFailed'), variant: 'destructive' });
      } finally {
        setIsTrusting(false);
      }
    }, [skill, t, onOpenChange, onTrustChange]);

    const reloadSkillContent = useCallback(() => {
      if (!skill) return;
      getSkillFile(skill.id, 'SKILL.md')
        .then(setSkillContent)
        .catch(() => setSkillContent(''));
    }, [skill]);

    const handleToggleEvolutionLock = useCallback(async () => {
      if (!skill) return;
      const newLocked = !isEvolutionLocked;
      setIsTogglingLock(true);
      try {
        await toggleEvolutionLock(skill.id, newLocked);
        setIsEvolutionLocked(newLocked);
        toast({
          title: newLocked ? t('detail.evolutionLocked') : t('detail.evolutionUnlocked'),
          description: newLocked
            ? t('detail.evolutionLockedDesc', { name: skill.name })
            : t('detail.evolutionUnlockedDesc', { name: skill.name }),
        });
      } catch {
        toast({ title: t('detail.evolutionLockFailed'), variant: 'destructive' });
      } finally {
        setIsTogglingLock(false);
      }
    }, [skill, isEvolutionLocked, t]);

    const handleOptimize = useCallback(async () => {
      if (!skill || !optimizeInstruction.trim()) return;
      setIsOptimizing(true);
      try {
        const response = await fetch(`/api/v1/evolution/derive/${skill.id}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ instruction: optimizeInstruction.trim() }),
        });
        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.detail || 'Failed to start optimization');
        }
        toast({
          title: t('detail.optimizeStarted'),
          description: t('detail.optimizeStartedDesc', { name: skill.name }),
        });
        setShowOptimizeInput(false);
        setOptimizeInstruction('');
      } catch (error) {
        toast({
          title: t('detail.optimizeFailed'),
          description: error instanceof Error ? error.message : t('detail.optimizeFailed'),
          variant: 'destructive',
        });
      } finally {
        setIsOptimizing(false);
      }
    }, [skill, optimizeInstruction]);

    if (!skill) return null;

    const category = skill.category || 'other';
    const CategoryIcon = getCategoryIcon(category);
    const categoryColor = getCategoryColor(category);
    const trustColor = trustColors[skill.trust] || trustColors.installed;

    return (
      <>
        <Sheet open={open} onOpenChange={onOpenChange}>
          <SheetContent side="right" className="w-full sm:max-w-lg flex flex-col p-0 overflow-hidden">
            <SheetHeader className="p-6 pb-4 border-b shrink-0">
              <div className="flex items-start gap-4">
                <div
                  className={cn('flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center', categoryColor)}
                >
                  <CategoryIcon size={24} />
                </div>
                <div className="flex-1 min-w-0">
                  <SheetTitle className="text-xl font-semibold truncate">{skill.name}</SheetTitle>
                  <SheetDescription className="mt-1">
                    <span className="flex items-center gap-3 text-sm">
                      <span className="flex items-center gap-1">
                        <Package size={14} />v{skill.version}
                      </span>
                      <Badge variant="secondary" className={cn('text-xs', categoryColor)}>
                        {t(`categories.${category}` as Parameters<typeof t>[0])}
                      </Badge>
                      {skill.always && (
                        <Badge
                          variant="outline"
                          className="text-xs border-emerald-300 text-emerald-600 dark:border-emerald-700 dark:text-emerald-400"
                        >
                          {t('card.alwaysEnabled')}
                        </Badge>
                      )}
                    </span>
                  </SheetDescription>
                </div>
              </div>
            </SheetHeader>

            <div className="flex-1 overflow-y-auto px-6">
              <div className="py-4 space-y-5">
                <p className="text-muted-foreground">{skill.description}</p>

                {/* Quality Guardian & AB Test Status */}
                <SkillQualityGuardian skillId={skill.id} onPromoted={reloadSkillContent} />

                <SkillVersionsPanel skillId={skill.id} onActivated={reloadSkillContent} />

                {/* Availability warning */}
                {!skill.available && (
                  <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800">
                    <AlertTriangle size={16} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                    <span className="text-sm text-amber-700 dark:text-amber-300">
                      {skill.unavailable_reason || t('card.unavailable')}
                    </span>
                  </div>
                )}

                {/* Meta info: author, trust, homepage */}
                <div className="grid grid-cols-2 gap-3 text-sm">
                  {skill.author && (
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <User size={14} />
                      <span>{skill.author}</span>
                    </div>
                  )}
                  <div className="flex items-center gap-2">
                    <Shield size={14} className={trustColor} />
                    <span className={cn('text-sm', trustColor)}>
                      {t(`card.trustLevels.${skill.trust}` as Parameters<typeof t>[0])}
                    </span>
                    {isUserTrusted && (
                      <Badge
                        variant="outline"
                        className="text-xs border-green-300 text-green-600 dark:border-green-700 dark:text-green-400"
                      >
                        {t('card.userTrusted')}
                      </Badge>
                    )}
                    {isUserTrustable && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-6 text-xs px-2"
                        onClick={() => setShowTrustConfirm(true)}
                        disabled={isTrusting}
                      >
                        {t('card.trustSkill')}
                      </Button>
                    )}
                    {isUserTrusted && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 text-xs px-2 text-muted-foreground"
                        onClick={handleUntrust}
                        disabled={isTrusting}
                      >
                        {t('card.revokeSkill')}
                      </Button>
                    )}
                  </div>
                  {skill.homepage && (
                    <a
                      href={skill.homepage}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 text-primary hover:underline col-span-2"
                    >
                      <ExternalLink size={14} />
                      <span className="truncate">{skill.homepage}</span>
                    </a>
                  )}
                  <div className="flex items-center gap-1 text-muted-foreground">
                    <Calendar size={14} />
                    <span>{new Date(skill.created_at).toLocaleDateString()}</span>
                  </div>
                </div>

                {/* Security scan summary */}
                {skill.security && <SecurityScanSection security={skill.security} t={t} />}

                {/* Evolution lock toggle */}
                {skill.type === 'local' && (
                  <div className="flex items-center justify-between p-3 rounded-lg border bg-muted/30">
                    <div className="flex items-center gap-2">
                      {isEvolutionLocked ? (
                        <Lock size={14} className="text-amber-600 dark:text-amber-400" />
                      ) : (
                        <LockOpen size={14} className="text-muted-foreground" />
                      )}
                      <div>
                        <span className="text-sm font-medium">{t('detail.evolutionLockLabel')}</span>
                        <p className="text-xs text-muted-foreground">{t('detail.evolutionLockHint')}</p>
                      </div>
                    </div>
                    <Button
                      variant={isEvolutionLocked ? 'default' : 'outline'}
                      size="sm"
                      className="h-7 text-xs"
                      onClick={handleToggleEvolutionLock}
                      disabled={isTogglingLock}
                    >
                      {isTogglingLock && <Loader2 className="animate-spin mr-1" size={12} />}
                      {isEvolutionLocked ? t('detail.evolutionUnlock') : t('detail.evolutionLock')}
                    </Button>
                  </div>
                )}

                {/* Lifecycle status & actions */}
                {onLifecycleAction && skill.usage_stats && (
                  <div className="flex items-center justify-between p-3 rounded-lg border bg-muted/30">
                    <div className="flex items-center gap-2">
                      {skill.usage_stats.pinned ? (
                        <Pin size={14} className="text-blue-500" />
                      ) : skill.usage_stats.lifecycle_status === 'stale' ? (
                        <Archive size={14} className="text-amber-500" />
                      ) : skill.usage_stats.lifecycle_status === 'archived' ? (
                        <Archive size={14} className="text-muted-foreground" />
                      ) : null}
                      <div>
                        <div className="flex items-center gap-1.5">
                          <span className="text-sm font-medium">{t('card.pin')}</span>
                          {skill.usage_stats.lifecycle_status !== 'active' && (
                            <Badge variant="outline" className="text-[10px] px-1 py-0">
                              {skill.usage_stats.lifecycle_status === 'stale' ? t('card.stale') : t('card.archived')}
                            </Badge>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      {skill.usage_stats.pinned ? (
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => onLifecycleAction(skill, 'unpin')}
                        >
                          <PinOff size={12} className="mr-1" />
                          {t('card.unpin')}
                        </Button>
                      ) : (
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => onLifecycleAction(skill, 'pin')}
                        >
                          <Pin size={12} className="mr-1" />
                          {t('card.pin')}
                        </Button>
                      )}
                      {(skill.usage_stats.lifecycle_status === 'stale' ||
                        skill.usage_stats.lifecycle_status === 'archived') && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => onLifecycleAction(skill, 'restore')}
                        >
                          <RotateCcw size={12} className="mr-1" />
                          {t('card.restore')}
                        </Button>
                      )}
                    </div>
                  </div>
                )}

                {/* Prebuilt update management */}
                {skill.type === 'prebuilt' && onLifecycleAction && (
                  <div className="space-y-2">
                    {skill.has_upstream_update && (
                      <div className="flex items-center justify-between p-3 rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50/50 dark:bg-blue-950/20">
                        <div className="flex items-center gap-2">
                          <ArrowUpCircle size={14} className="text-blue-500" />
                          <span className="text-sm">{t('card.updateAvailableReason')}</span>
                        </div>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs border-blue-300 text-blue-600 dark:border-blue-700 dark:text-blue-400"
                          onClick={() => onLifecycleAction(skill, 'accept-upstream')}
                        >
                          <ArrowUpCircle size={12} className="mr-1" />
                          {t('card.acceptUpstream')}
                        </Button>
                      </div>
                    )}
                    <div className="flex justify-end">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs text-muted-foreground"
                        onClick={() => onLifecycleAction(skill, 'reset-to-default')}
                      >
                        <Undo2 size={12} className="mr-1" />
                        {t('card.resetToDefault')}
                      </Button>
                    </div>
                  </div>
                )}

                {/* Tags */}
                {skill.tags.length > 0 && (
                  <div className="flex items-center gap-2 flex-wrap">
                    <Tag size={14} className="text-muted-foreground" />
                    {skill.tags.map((tag) => (
                      <Badge key={tag} variant="outline" className="text-xs">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                )}

                <div className="border-t" />

                {/* Requirements section */}
                <div>
                  <h4 className="text-sm font-medium mb-3">{t('card.requirements')}</h4>
                  {hasRequirements ? (
                    <div className="space-y-2">
                      {skill.requires.bins.length > 0 && (
                        <RequirementRow icon={Terminal} label={t('card.requiredBins')} items={skill.requires.bins} />
                      )}
                      {skill.requires.env.length > 0 && (
                        <RequirementRow icon={Key} label={t('card.requiredEnv')} items={skill.requires.env} />
                      )}
                      {skill.requires.config.length > 0 && (
                        <RequirementRow
                          icon={Settings}
                          label={t('card.requiredConfig')}
                          items={skill.requires.config}
                        />
                      )}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">{t('card.noRequirements')}</p>
                  )}
                </div>

                {/* Env var configuration */}
                {hasEnvRequirements && (
                  <>
                    <div className="border-t" />
                    <div>
                      <h4 className="text-sm font-medium mb-3 flex items-center gap-2">
                        <Key size={14} />
                        {t('card.envConfig')}
                      </h4>
                      <div className="space-y-3">
                        {skill.primary_env && (
                          <div>
                            <label className="text-xs font-mono text-muted-foreground mb-1 block">
                              API Key
                              <span className="ml-1 text-[10px] opacity-60">→ {skill.primary_env}</span>
                            </label>
                            <Input
                              type="password"
                              placeholder={t('card.enterApiKey')}
                              value={envVars['api_key'] || ''}
                              onChange={(e) => handleEnvVarChange('api_key', e.target.value)}
                              className="font-mono text-sm h-8"
                            />
                          </div>
                        )}
                        {skill.requires.env
                          .filter((envKey) => envKey !== skill.primary_env)
                          .map((envKey) => (
                            <div key={envKey}>
                              <label className="text-xs font-mono text-muted-foreground mb-1 block">{envKey}</label>
                              <Input
                                type="password"
                                placeholder={`Enter ${envKey}...`}
                                value={envVars[envKey] || ''}
                                onChange={(e) => handleEnvVarChange(envKey, e.target.value)}
                                className="font-mono text-sm h-8"
                              />
                            </div>
                          ))}
                        {envVarsDirty && (
                          <Button size="sm" onClick={handleSaveEnvVars} disabled={isSavingEnv} className="w-full">
                            {isSavingEnv && <Loader2 className="animate-spin mr-2" size={14} />}
                            {t('card.saveKeys')}
                          </Button>
                        )}
                      </div>
                    </div>
                  </>
                )}

                {/* Known Pitfalls */}
                {skill.traps && skill.traps.length > 0 && (
                  <>
                    <div className="border-t" />
                    <KnownPitfallsSection traps={skill.traps} t={t} />
                  </>
                )}

                <div className="border-t" />

                {/* SKILL.md content */}
                <div className="border rounded-lg bg-muted/30">
                  <div className="px-4 py-2 border-b bg-muted rounded-t-lg">
                    <span className="text-sm font-medium">SKILL.md</span>
                  </div>
                  <div className="p-4">
                    {isLoadingContent ? (
                      <div className="flex items-center justify-center py-8">
                        <Loader2 className="animate-spin text-muted-foreground" size={24} />
                      </div>
                    ) : skillContent ? (
                      <div className="prose prose-sm dark:prose-invert max-w-none prose-headings:text-foreground prose-p:text-muted-foreground prose-li:text-muted-foreground prose-strong:text-foreground prose-code:text-accent-foreground prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-pre:bg-muted/50 prose-table:text-sm prose-th:text-foreground prose-td:text-muted-foreground">
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            code({ className, children, ...props }) {
                              const match = /language-(\w+)/.exec(className || '');
                              const language = match && match[1] ? match[1] : '';
                              const value = getChildrenAsText(children);

                              if (language) {
                                return <CodeBlock language={language} value={value} />;
                              }

                              return (
                                <code className={className} {...props}>
                                  {children}
                                </code>
                              );
                            },
                          }}
                        >
                          {stripYamlFrontmatter(skillContent)}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground text-center py-4">{t('detail.loadFailed')}</p>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Footer actions */}
            <div className="p-4 border-t flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowExportDialog(true)}
                  className="hidden sm:flex"
                >
                  <Download className="h-4 w-4 mr-2" />
                  {t('export')}
                </Button>
                {showDeleteButton && (
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => setShowDeleteConfirm(true)}
                    disabled={isDeleting}
                  >
                    {isDeleting ? (
                      <Loader2 className="animate-spin mr-2" size={16} />
                    ) : (
                      <Trash2 size={16} className="mr-2" />
                    )}
                    {t('detail.delete')}
                  </Button>
                )}
                {skill.type === 'local' && (
                  <div className="relative group">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setShowOptimizeInput(!showOptimizeInput)}
                      disabled={isOptimizing || isEvolutionLocked}
                      className={cn(isEvolutionLocked && 'opacity-50 cursor-not-allowed')}
                    >
                      {isOptimizing ? (
                        <Loader2 className="animate-spin mr-2" size={16} />
                      ) : (
                        <Zap size={16} className="mr-2" />
                      )}
                      {t('detail.optimize')}
                    </Button>
                    {isEvolutionLocked && (
                      <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block w-max max-w-[200px] px-2 py-1 bg-popover text-popover-foreground text-xs rounded border z-50 text-center pointer-events-none">
                        Unlock evolution to optimize
                      </div>
                    )}
                  </div>
                )}
              </div>
              {showOptimizeInput && (
                <div className="flex gap-2 mt-2">
                  <Input
                    placeholder={t('detail.optimizePlaceholder')}
                    value={optimizeInstruction}
                    onChange={(e) => setOptimizeInstruction(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && optimizeInstruction.trim()) {
                        handleOptimize();
                      }
                    }}
                    className="flex-1"
                  />
                  <Button size="sm" onClick={handleOptimize} disabled={isOptimizing || !optimizeInstruction.trim()}>
                    {isOptimizing && <Loader2 className="animate-spin mr-2" size={16} />}
                    {t('detail.optimizeSubmit')}
                  </Button>
                </div>
              )}
              <Button
                variant={isEnabled ? 'outline' : 'default'}
                size="sm"
                onClick={handleToggle}
                disabled={isToggling}
              >
                {isToggling && <Loader2 className="animate-spin mr-2" size={16} />}
                {isEnabled ? t('detail.disable') : t('detail.enable')}
              </Button>
            </div>
          </SheetContent>
        </Sheet>

        <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('detail.confirmDelete')}</AlertDialogTitle>
              <AlertDialogDescription>{t('detail.confirmDeleteDesc', { name: skill.name })}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t('upload.cancel')}</AlertDialogCancel>
              <AlertDialogAction
                onClick={handleDelete}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {isDeleting && <Loader2 className="animate-spin mr-2" size={16} />}
                {t('detail.delete')}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <AlertDialog open={showTrustConfirm} onOpenChange={setShowTrustConfirm}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('card.trustConfirmTitle')}</AlertDialogTitle>
              <AlertDialogDescription>{t('card.trustConfirmDesc', { name: skill.name })}</AlertDialogDescription>
            </AlertDialogHeader>
            {skill.security && (
              <div className="px-1">
                <SecurityScanSection security={skill.security} t={t} />
              </div>
            )}
            <AlertDialogFooter>
              <AlertDialogCancel>{t('upload.cancel')}</AlertDialogCancel>
              <AlertDialogAction onClick={handleTrust} className="bg-green-600 text-white hover:bg-green-700">
                {isTrusting && <Loader2 className="animate-spin mr-2" size={16} />}
                {t('card.trustSkill')}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
          </AlertDialog>

        <SkillExportDialog
          skill={skill}
          open={showExportDialog}
          onOpenChange={setShowExportDialog}
        />
      </>
    );
  },
);

SkillDetailSheet.displayName = 'SkillDetailSheet';

interface RequirementRowProps {
  icon: React.ElementType;
  label: string;
  items: string[];
}

function RequirementRow({ icon: Icon, label, items }: RequirementRowProps) {
  return (
    <div className="flex items-start gap-2">
      <Icon size={14} className="text-muted-foreground mt-0.5 shrink-0" />
      <div>
        <span className="text-xs text-muted-foreground">{label}</span>
        <div className="flex flex-wrap gap-1 mt-1">
          {items.map((item) => (
            <code key={item} className="text-xs px-1.5 py-0.5 rounded bg-muted font-mono">
              {item}
            </code>
          ))}
        </div>
      </div>
    </div>
  );
}

const severityConfig: Record<string, { color: string; label: string }> = {
  critical: { color: 'text-red-600 dark:text-red-400', label: 'Critical' },
  high: { color: 'text-orange-600 dark:text-orange-400', label: 'High' },
  medium: { color: 'text-yellow-600 dark:text-yellow-400', label: 'Medium' },
  low: { color: 'text-blue-600 dark:text-blue-400', label: 'Low' },
};

function getScoreConfig(score: number) {
  if (score >= 80)
    return {
      icon: ShieldCheck,
      color: 'text-green-600 dark:text-green-400',
      bg: 'bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800',
    };
  if (score >= 50)
    return {
      icon: Shield,
      color: 'text-yellow-600 dark:text-yellow-400',
      bg: 'bg-yellow-50 dark:bg-yellow-950/30 border-yellow-200 dark:border-yellow-800',
    };
  if (score >= 25)
    return {
      icon: ShieldAlert,
      color: 'text-orange-600 dark:text-orange-400',
      bg: 'bg-orange-50 dark:bg-orange-950/30 border-orange-200 dark:border-orange-800',
    };
  return {
    icon: ShieldX,
    color: 'text-red-600 dark:text-red-400',
    bg: 'bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800',
  };
}

interface SecurityScanSectionProps {
  security: SecurityScanSummary;
  t: ReturnType<typeof useTranslations<'settings.skills'>>;
}

function SecurityScanSection({ security, t }: SecurityScanSectionProps) {
  const [expanded, setExpanded] = useState(false);
  const { icon: ScoreIcon, color, bg } = getScoreConfig(security.score);
  const hasFindings = security.total_findings > 0;

  return (
    <div className={cn('rounded-lg border p-3', bg)}>
      <button
        className="w-full flex items-center justify-between"
        onClick={() => hasFindings && setExpanded((v) => !v)}
        disabled={!hasFindings}
        type="button"
      >
        <div className="flex items-center gap-2">
          <ScoreIcon size={18} className={color} />
          <span className={cn('text-sm font-medium', color)}>{t('card.securityScore', { score: security.score })}</span>
        </div>
        <div className="flex items-center gap-2">
          {hasFindings && (
            <span className="text-xs text-muted-foreground">
              {t('card.findings', { count: security.total_findings })}
            </span>
          )}
          {hasFindings && (
            <ChevronDown
              size={14}
              className={cn('text-muted-foreground transition-transform', expanded && 'rotate-180')}
            />
          )}
        </div>
      </button>

      {expanded && hasFindings && (
        <div className="mt-2 pt-2 border-t border-current/10 space-y-2">
          {(['critical', 'high', 'medium', 'low'] as const).map((severity) => {
            const cfg = severityConfig[severity];
            const items = security.findings.filter((f) => f.severity === severity);
            if (!cfg || items.length === 0) return null;
            return (
              <div key={severity}>
                <div className="flex items-center gap-1.5 mb-1">
                  <span className={cn('text-xs font-medium', cfg.color)}>{cfg.label}</span>
                  <span className="text-xs text-muted-foreground">({items.length})</span>
                </div>
                <div className="space-y-0.5 pl-3">
                  {items.map((finding, i) => (
                    <div key={`${finding.threat_type}-${i}`} className="text-xs text-muted-foreground">
                      <span className="font-mono text-[11px] opacity-70">[{finding.threat_type}]</span>{' '}
                      {finding.description}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

const trapSeverityConfig: Record<string, { color: string; icon: string }> = {
  critical: { color: 'text-red-600 dark:text-red-400', icon: '!!!' },
  high: { color: 'text-orange-600 dark:text-orange-400', icon: '!!' },
  medium: { color: 'text-yellow-600 dark:text-yellow-400', icon: '!' },
  low: { color: 'text-blue-600 dark:text-blue-400', icon: '~' },
};

interface KnownPitfallsSectionProps {
  traps: SkillTrap[];
  t: ReturnType<typeof useTranslations<'settings.skills'>>;
}

function KnownPitfallsSection({ traps }: KnownPitfallsSectionProps) {
  return (
    <div>
      <h4 className="text-sm font-medium mb-3 flex items-center gap-2">
        <AlertTriangle size={14} className="text-amber-500" />
        Known Pitfalls
        <Badge variant="secondary" className="text-xs">
          {traps.length}
        </Badge>
      </h4>
      <div className="space-y-2">
        {traps.map((trap, i) => {
          const cfg = trapSeverityConfig[trap.severity] || trapSeverityConfig.medium;
          return (
            <div key={`${trap.description}-${i}`} className="rounded-full border bg-muted/30 p-2.5 text-sm">
              <div className="flex items-start gap-2">
                <span className={cn('font-mono text-xs font-bold shrink-0 mt-0.5', cfg.color)}>[{cfg.icon}]</span>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-foreground">{trap.description}</p>
                  {trap.trigger_condition && (
                    <p className="text-xs text-muted-foreground mt-1">Trigger: {trap.trigger_condition}</p>
                  )}
                  {trap.mitigation && (
                    <p className="text-xs text-green-600 dark:text-green-400 mt-0.5">→ {trap.mitigation}</p>
                  )}
                  {trap.occurrence_count > 0 && (
                    <span className="text-[10px] text-muted-foreground/60 mt-1 inline-block">
                      x{trap.occurrence_count}
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default SkillDetailSheet;
