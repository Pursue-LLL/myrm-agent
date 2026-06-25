'use client';

import {
  Calendar,
  Tag,
  Shield,
  AlertTriangle,
  Terminal,
  Key,
  Settings,
  User,
  Lock,
  LockOpen,
  Pin,
  PinOff,
  Archive,
  RotateCcw,
  Zap,
  ArrowUpCircle,
  Undo2,
  Loader2,
  ExternalLink,
  FolderOpen,
  FolderX,
  Copy,
  Trash2,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Input } from '@/components/primitives/input';
import { toast } from '@/hooks/useToast';
import { isLocalMode, isTauriRuntime } from '@/lib/deploy-mode';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import CodeBlock from '@/components/features/markdown-render-tools/CodeBlock';
import { getChildrenAsText } from '@/lib/utils/reactUtils';
import type { Skill, SkillLifecycleAction } from '@/store/skill/types';
import Link from 'next/link';
import {
  getSkillUnavailableDisplayMessage,
  isGoogleWorkspaceOAuthUnavailable,
  SETTINGS_GOOGLE_OAUTH_PATH,
} from '@/lib/skills/integrationOAuthDisplay';
import { SkillQualityGuardian } from './SkillQualityGuardian';
import { SkillVersionsPanel } from './SkillVersionsPanel';
import { getCategoryIcon, getCategoryColor } from './skillCategories';
import { RequirementRow, SecurityScanSection, KnownPitfallsSection } from './SkillDetailHelpers';

function stripYamlFrontmatter(content: string): string {
  const match = content.match(/^---\s*\n[\s\S]*?\n---\s*\n/);
  return match ? content.slice(match[0].length) : content;
}

const trustColors: Record<string, string> = {
  builtin: 'text-accent-warm',
  installed: 'text-primary',
  untrusted: 'text-amber-600 dark:text-amber-400',
};

interface SkillDetailSheetContentProps {
  skill: Skill;
  skillContent: string;
  isLoadingContent: boolean;
  isUserTrustable: boolean;
  isUserTrusted: boolean;
  isTrusting: boolean;
  isEvolutionLocked: boolean;
  isTogglingLock: boolean;
  isPathInvalid: boolean;
  isRevealing: boolean;
  hasRequirements: boolean;
  hasEnvRequirements: boolean;
  envVars: Record<string, string>;
  envVarsDirty: boolean;
  isSavingEnv: boolean;
  reloadSkillContent: () => void;
  handleUntrust: () => void;
  handleToggleEvolutionLock: () => void;
  handleReveal: () => void;
  handleEnvVarChange: (key: string, value: string) => void;
  handleSaveEnvVars: () => void;
  setShowTrustConfirm: (v: boolean) => void;
  setShowDeleteConfirm: (v: boolean) => void;
  onLifecycleAction?: (skill: Skill, action: SkillLifecycleAction) => void;
  t: (key: string, fallbackOrParams?: string | Record<string, unknown>) => string;
}

export function SkillDetailSheetContent({
  skill,
  skillContent,
  isLoadingContent,
  isUserTrustable,
  isUserTrusted,
  isTrusting,
  isEvolutionLocked,
  isTogglingLock,
  isPathInvalid,
  isRevealing,
  hasRequirements,
  hasEnvRequirements,
  envVars,
  envVarsDirty,
  isSavingEnv,
  reloadSkillContent,
  handleUntrust,
  handleToggleEvolutionLock,
  handleReveal,
  handleEnvVarChange,
  handleSaveEnvVars,
  setShowTrustConfirm,
  setShowDeleteConfirm,
  onLifecycleAction,
  t,
}: SkillDetailSheetContentProps) {
  const category = skill.category || 'other';
  const trustColor = trustColors[skill.trust] || trustColors.installed;

  return (
    <div className="py-4 space-y-5">
      <p className="text-muted-foreground">{skill.description}</p>

      <SkillQualityGuardian skillId={skill.id} onPromoted={reloadSkillContent} />
      <SkillVersionsPanel skillId={skill.id} onActivated={reloadSkillContent} />

      {/* Availability warning */}
      {!skill.available && (
        <div className="flex flex-col gap-2 p-3 rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-2 min-w-0">
            <AlertTriangle size={16} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            <span className="text-sm text-amber-700 dark:text-amber-300">
              {getSkillUnavailableDisplayMessage(skill, t)}
            </span>
          </div>
          {isGoogleWorkspaceOAuthUnavailable(skill) && (
            <Link
              href={SETTINGS_GOOGLE_OAUTH_PATH}
              className="shrink-0 text-sm font-medium text-amber-800 dark:text-amber-200 underline underline-offset-2 hover:opacity-90"
            >
              {t('card.integrationOAuth.googleWorkspace.connectInSettings')}
            </Link>
          )}
        </div>
      )}

      {/* Meta info */}
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
        {skill.token_cost != null && skill.token_cost > 0 && (
          <div className="flex items-center gap-2 col-span-2">
            <Zap size={14} className="text-muted-foreground" />
            <span className="text-sm text-muted-foreground">
              {t('detail.tokenCost', { count: skill.token_cost.toLocaleString() })}
            </span>
          </div>
        )}
      </div>

      {/* Security scan */}
      {skill.security && <SecurityScanSection security={skill.security} t={t} />}

      {/* Local Storage Path */}
      {skill.type === 'local' && (isLocalMode() || isTauriRuntime()) && skill.storage_path && (
        <div
          className={cn(
            'flex items-center justify-between p-3 rounded-lg border',
            isPathInvalid ? 'bg-red-500/10 border-red-500/50' : 'bg-muted/30',
          )}
        >
          <div className="flex items-center gap-2 overflow-hidden flex-1 mr-4">
            {isPathInvalid ? (
              <FolderX size={14} className="text-red-500 flex-shrink-0" />
            ) : (
              <FolderOpen size={14} className="text-muted-foreground flex-shrink-0" />
            )}
            <div className="overflow-hidden">
              <span className={cn('text-sm font-medium', isPathInvalid && 'text-red-500')}>
                {isPathInvalid ? t('detail.pathInvalid', 'Path Invalid') : t('detail.storagePath', 'Storage Path')}
              </span>
              <p
                className={cn('text-xs truncate', isPathInvalid ? 'text-red-400' : 'text-muted-foreground')}
                title={skill.storage_path}
              >
                {skill.storage_path}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => {
                navigator.clipboard.writeText(skill.storage_path!);
                toast({ title: t('detail.pathCopied', 'Path copied') });
              }}
              title={t('detail.copyPath', 'Copy path')}
            >
              <Copy size={14} />
            </Button>
            {!isPathInvalid ? (
              <Button variant="outline" size="sm" className="h-7 text-xs" onClick={handleReveal} disabled={isRevealing}>
                {isRevealing ? (
                  <Loader2 className="animate-spin mr-1" size={12} />
                ) : (
                  <FolderOpen className="mr-1" size={12} />
                )}
                {t('detail.revealInManager', 'Reveal')}
              </Button>
            ) : (
              <Button
                variant="destructive"
                size="sm"
                className="h-7 text-xs"
                onClick={() => setShowDeleteConfirm(true)}
              >
                <Trash2 className="mr-1" size={12} />
                {t('detail.cleanupInvalid', 'Cleanup')}
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Evolution lock */}
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

      {/* Requirements */}
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
              <RequirementRow icon={Settings} label={t('card.requiredConfig')} items={skill.requires.config} />
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
  );
}
