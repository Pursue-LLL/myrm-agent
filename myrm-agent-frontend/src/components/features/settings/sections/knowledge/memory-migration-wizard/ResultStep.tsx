'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { CheckCircle2, Loader2, RotateCcw } from 'lucide-react';
import { toast } from 'sonner';

import { agentSettingsHref, teamAssetsHubHref } from '@/components/features/loadout/loadoutDeepLinks';
import { Button } from '@/components/primitives/button';
import {
  queueMigrationChatAgent,
  queueMigrationReadinessAnchor,
  type MigrationWorkspaceBindCandidate,
} from '@/lib/migrationChatHandoff';
import { isLocalMode } from '@/lib/deploy-mode';
import { cn } from '@/lib/utils/classnameUtils';
import { recheckImportReadiness } from '@/services/memory/archive';
import type { MemoryImportConfirmResponse, MemoryImportReadiness } from '@/services/memory/archive';
import type { SkillMigrationSubmitResponse } from '@/services/skill/migration';
import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';

import CodexWikiCompletionLane from '../CodexWikiCompletionLane';
import {
  formatReadinessIssue,
  getImportReadinessStatus,
  getReadinessIssueAction,
  IMPORT_READINESS_STYLES,
} from '../MigrationWizardReadiness';
import MigrationVaultBindPanel from '../MigrationVaultBindPanel';
import type { TranslationFn } from './wizardShared';

export function ResultStep({
  result,
  skillSubmitResult,
  skillSubmitFailed,
  secretsImportMessage,
  rollingBack,
  onRollback,
  onRetrySkillSubmit,
  retryingSkills,
  onDone,
  vaultBindHandoffMode = 'settings',
  workspaceBindCandidates = [],
  migrationSource = null,
  t,
}: {
  result: MemoryImportConfirmResponse;
  skillSubmitResult: SkillMigrationSubmitResponse | null;
  skillSubmitFailed: boolean;
  secretsImportMessage: string | null;
  rollingBack: boolean;
  onRollback: () => void;
  onRetrySkillSubmit: () => void;
  retryingSkills: boolean;
  onDone: () => void;
  vaultBindHandoffMode?: 'settings' | 'onboarding';
  workspaceBindCandidates?: MigrationWorkspaceBindCandidate[];
  migrationSource?: string | null;
  t: TranslationFn;
}) {
  const router = useRouter();
  const memoryEnableConversationSearch = useConfigStore((s) => s.memoryEnableConversationSearch);
  const setMemoryEnableConversationSearch = useConfigStore((s) => s.setMemoryEnableConversationSearch);
  const [readinessOverride, setReadinessOverride] = useState<MemoryImportReadiness | null>(null);
  const [startingChat, setStartingChat] = useState(false);

  const handleEnableConversationSearch = useCallback(() => {
    setMemoryEnableConversationSearch(true);
    toast.success(t('result.conversationSearchEnabled'));
  }, [setMemoryEnableConversationSearch, t]);
  const effectiveResult: MemoryImportConfirmResponse = readinessOverride
    ? { ...result, readiness: readinessOverride }
    : result;
  const readinessStatus = getImportReadinessStatus(effectiveResult);
  const readinessIssues = effectiveResult.readiness?.issues ?? [];
  const readinessIsCritical = readinessStatus === 'critical';
  const resultAnchorQueuedRef = useRef(false);
  const showSettingsVaultBind = vaultBindHandoffMode === 'settings' && isLocalMode();
  const primaryObsidianCandidate =
    workspaceBindCandidates.find((candidate) => candidate.has_obsidian_config) ?? workspaceBindCandidates[0] ?? null;

  useEffect(() => {
    if (resultAnchorQueuedRef.current || !result.target_agent_id) {
      return;
    }
    resultAnchorQueuedRef.current = true;

    const queueFromStatus = (status: 'ready' | 'warning', batchId: string) => {
      queueMigrationReadinessAnchor({
        importBatchId: batchId,
        readinessStatus: status,
        targetAgentId: result.target_agent_id ?? '',
      });
    };

    void (async () => {
      try {
        const recheck = await recheckImportReadiness(result.import_batch_id);
        setReadinessOverride(recheck.readiness);
        if (recheck.readiness.status === 'ready' || recheck.readiness.status === 'warning') {
          queueFromStatus(recheck.readiness.status, result.import_batch_id);
        }
      } catch {
        if (readinessStatus === 'ready' || readinessStatus === 'warning') {
          queueFromStatus(readinessStatus, result.import_batch_id);
        }
      }
    })();
  }, [readinessStatus, result.import_batch_id, result.target_agent_id]);

  const handleStartChat = async () => {
    if (!result.target_agent_id || startingChat) {
      return;
    }
    setStartingChat(true);
    try {
      const recheck = await recheckImportReadiness(result.import_batch_id);
      setReadinessOverride(recheck.readiness);
      if (recheck.readiness.status === 'critical') {
        return;
      }
      queueMigrationReadinessAnchor({
        importBatchId: result.import_batch_id,
        readinessStatus: recheck.readiness.status,
        targetAgentId: result.target_agent_id,
      });
      queueMigrationChatAgent(result.target_agent_id);
      router.push('/');
    } catch {
      toast.error(t('result.readinessRecheckFailed'));
    } finally {
      setStartingChat(false);
    }
  };

  const handleVerifyMemories = () => {
    if (!result.target_agent_id) {
      return;
    }
    queueMigrationChatAgent(result.target_agent_id);
    useChatStore.getState().setInputMessage(t('result.verifyPrompt'));
    router.push('/');
  };

  return (
    <div className="space-y-6 text-center max-w-lg mx-auto py-8">
      <CheckCircle2 className="mx-auto h-12 w-12 text-emerald-500" />
      <div className="space-y-2">
        <h2 className="text-xl font-semibold">{t('result.title')}</h2>
        <p className="text-sm text-muted-foreground">{t('result.totalImported', { count: result.total_imported })}</p>
        {skillSubmitResult && (
          <p className="text-sm text-muted-foreground">
            {t('result.skillsSubmitted', { count: skillSubmitResult.total_items })}
          </p>
        )}
        {skillSubmitFailed && (
          <p className="text-sm text-amber-600 dark:text-amber-400">{t('result.skillsSubmitFailed')}</p>
        )}
        {secretsImportMessage && <p className="text-sm text-muted-foreground">{secretsImportMessage}</p>}
        {result.agent_created && result.target_agent_id && (
          <p className="text-sm text-muted-foreground">{t('result.agentCreated', { id: result.target_agent_id })}</p>
        )}
        {!result.agent_created && result.target_agent_id && (
          <p className="text-sm text-muted-foreground">{t('result.agentUpdated', { id: result.target_agent_id })}</p>
        )}
        {result.global_instructions_updated && (
          <p className="text-sm text-muted-foreground">{t('result.globalInstructionsUpdated')}</p>
        )}
        {(result.workspace_rules_written ?? 0) > 0 && (
          <p className="text-sm text-muted-foreground">
            {t('result.workspaceRulesWritten', { count: result.workspace_rules_written ?? 0 })}
          </p>
        )}
        {(result.workspace_rules_skipped ?? 0) > 0 && (
          <p className="text-sm text-amber-600 dark:text-amber-400">
            {t('result.workspaceRulesSkipped', { count: result.workspace_rules_skipped ?? 0 })}
          </p>
        )}
        {result.cron_import_summary && (
          <>
            {result.cron_import_summary.imported_count > 0 && (
              <p className="text-sm text-muted-foreground">
                {t('result.cronImported', { count: result.cron_import_summary.imported_count })}
              </p>
            )}
            {result.cron_import_summary.failed_count > 0 && (
              <p className="text-sm text-amber-600 dark:text-amber-400">
                {t('result.cronImportFailed', { count: result.cron_import_summary.failed_count })}
              </p>
            )}
            {result.cron_import_summary.imported_count === 0 && result.cron_import_summary.skipped_count > 0 && (
              <p className="text-sm text-muted-foreground">
                {t('result.cronSkippedOnly', { count: result.cron_import_summary.skipped_count })}
              </p>
            )}
          </>
        )}
        {(result.imported_session_count ?? 0) > 0 && (
          <p className="text-sm font-medium text-emerald-600 dark:text-emerald-400">
            {t('result.sessionsImported', { count: result.imported_session_count ?? 0 })}
          </p>
        )}
        <div className={cn('rounded-xl border px-4 py-3 text-left text-xs', IMPORT_READINESS_STYLES[readinessStatus])}>
          <p className="font-medium">{t(`result.readinessStatus.${readinessStatus}`)}</p>
          <p className="mt-1 opacity-90">{t('result.readinessSummary')}</p>
          {readinessIssues.length > 0 && (
            <ul className="mt-2 space-y-1">
              {readinessIssues.map((issue, index) => {
                const action = getReadinessIssueAction(issue, t);
                return (
                  <li key={`${issue.code}-${index}`} className="flex items-start justify-between gap-3">
                    <span className="text-left">- {formatReadinessIssue(issue, t)}</span>
                    {action ? (
                      <Link
                        href={action.href}
                        className="shrink-0 rounded-md border border-current/30 px-2 py-0.5 text-[11px] font-medium hover:opacity-85"
                      >
                        {action.label}
                      </Link>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
          {readinessIsCritical && <p className="mt-2 font-medium">{t('result.readinessResolveBeforeChat')}</p>}
        </div>
      </div>

      {showSettingsVaultBind && (
        <MigrationVaultBindPanel candidates={workspaceBindCandidates} className="mx-auto max-w-xl w-full" />
      )}

      {migrationSource === 'codex' && result.target_agent_id ? (
        <CodexWikiCompletionLane targetAgentId={result.target_agent_id} vaultCandidate={primaryObsidianCandidate} />
      ) : null}

      <div className="flex flex-wrap justify-center gap-4 text-[11px] text-muted-foreground/50">
        <span>
          {t('result.batchId')}: {result.import_batch_id}
        </span>
      </div>

      <p className="text-xs text-muted-foreground/60">
        {skillSubmitResult
          ? t('result.nextStepsWithSkills')
          : skillSubmitFailed
            ? t('result.nextStepsPartialFailure')
            : t('result.nextStepsMemoryOnly')}
      </p>

      <div className="flex flex-wrap justify-center gap-2">
        {result.target_agent_id && (
          <Button size="sm" className="h-8 text-xs" onClick={() => void handleStartChat()} disabled={startingChat}>
            {startingChat && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            {startingChat
              ? t('result.startChatChecking')
              : readinessIsCritical
                ? t('result.startChatRecheck')
                : t('result.startChat')}
          </Button>
        )}
        {result.target_agent_id && result.total_imported > 0 && (
          <Button size="sm" variant="secondary" className="h-8 text-xs" onClick={handleVerifyMemories}>
            {t('result.verifyMemory')}
          </Button>
        )}
        {skillSubmitFailed && (
          <Button
            size="sm"
            variant="secondary"
            className="h-8 text-xs"
            onClick={onRetrySkillSubmit}
            disabled={retryingSkills}
          >
            {retryingSkills && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            {retryingSkills ? t('result.retryingSkillsSubmit') : t('result.retrySkillsSubmit')}
          </Button>
        )}
        {skillSubmitResult && (
          <Button asChild size="sm" variant="secondary" className="h-8 text-xs">
            <Link href="/settings/memory?sub=migration">{t('result.reviewSkills')}</Link>
          </Button>
        )}
        <Button asChild size="sm" variant="secondary" className="h-8 text-xs">
          <Link href={teamAssetsHubHref()}>{t('result.reviewTeamAssets')}</Link>
        </Button>
        {!memoryEnableConversationSearch && (
          <Button size="sm" variant="secondary" className="h-8 text-xs" onClick={handleEnableConversationSearch}>
            {t('result.enableConversationSearch')}
          </Button>
        )}
        {(result.imported_session_count ?? 0) > 0 && result.imported_chat_ids?.[0] && (
          <Button
            asChild
            size="sm"
            variant="default"
            className="h-8 text-xs bg-indigo-600 hover:bg-indigo-700 text-white"
          >
            <Link href={`/chat/${result.imported_chat_ids[0]}`}>{t('result.resumeChat')}</Link>
          </Button>
        )}
        {result.target_agent_id && (
          <Button asChild size="sm" variant="secondary" className="h-8 text-xs">
            <Link href={agentSettingsHref(result.target_agent_id)}>{t('result.reviewAgentLoadout')}</Link>
          </Button>
        )}
        <Button asChild size="sm" variant="outline" className="h-8 text-xs">
          <Link href="/settings/mcp">{t('result.configureMcp')}</Link>
        </Button>
        {(result.cron_import_summary?.imported_count ?? 0) > 0 && (
          <Button asChild size="sm" variant="outline" className="h-8 text-xs">
            <Link href="/settings/cron">{t('result.configureCron')}</Link>
          </Button>
        )}
        <Button asChild size="sm" variant="outline" className="h-8 text-xs">
          <Link href="/settings/channels">{t('result.configureChannels')}</Link>
        </Button>
        <Button asChild size="sm" variant="outline" className="h-8 text-xs">
          <Link href="/settings/models">{t('result.configureProviders')}</Link>
        </Button>
      </div>

      <p className="text-xs text-muted-foreground/60">{t('result.rollbackAvailable')}</p>

      <div className="flex justify-center gap-3 pt-2">
        <Button variant="outline" size="sm" onClick={onRollback} disabled={rollingBack}>
          {rollingBack ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
          )}
          {rollingBack ? t('result.rollingBack') : t('result.rollbackButton')}
        </Button>
        <Button size="sm" onClick={onDone}>
          {t('result.done')}
        </Button>
      </div>
    </div>
  );
}
