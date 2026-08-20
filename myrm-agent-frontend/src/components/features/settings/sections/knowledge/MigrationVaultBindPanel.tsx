'use client';

/**
 * [INPUT]
 * - @/services/projects::{getProjects, createProject}
 * - @/components/features/project-workspace/ProjectWorkspaceMount
 * - @/lib/migrationChatHandoff::{queueMigrationBoundProjectId, clearMigrationWorkspaceBindCandidates}
 *
 * [OUTPUT]
 * - MigrationVaultBindPanel: post-migration workspace bind with optional candidate pre-fill
 *
 * [POS]
 * Shared by Settings migration result (Settings path) and onboarding sync_folder step.
 */

import { useCallback, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { createProject, getProjects, type Project } from '@/services/projects';
import ProjectWorkspaceMount from '@/components/features/project-workspace/ProjectWorkspaceMount';
import {
  clearMigrationWorkspaceBindCandidates,
  queueMigrationBoundProjectId,
  applyMigrationBoundProjectToChat,
  type MigrationWorkspaceBindCandidate,
} from '@/lib/migrationChatHandoff';
import useChatStore from '@/store/useChatStore';
import { cn } from '@/lib/utils/classnameUtils';

export interface MigrationVaultBindPanelProps {
  candidates: MigrationWorkspaceBindCandidate[];
  onBound?: () => void;
  onSkip?: () => void;
  showSkip?: boolean;
  defaultProjectNameKey?: 'migrationWizard' | 'syncFolder';
  className?: string;
}

export default function MigrationVaultBindPanel({
  candidates,
  onBound,
  onSkip,
  showSkip = false,
  defaultProjectNameKey = 'migrationWizard',
  className,
}: MigrationVaultBindPanelProps) {
  const tWizard = useTranslations('memory.migrationWizard.result.vaultBind');
  const tSync = useTranslations('boot.onboarding.syncFolder');
  const defaultProjectName =
    defaultProjectNameKey === 'syncFolder' ? tSync('defaultProjectName') : tWizard('defaultProjectName');

  const [project, setProject] = useState<Project | null>(null);
  const [mountOpen, setMountOpen] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [boundPath, setBoundPath] = useState<string | null>(null);

  const primaryCandidate = candidates[0] ?? null;
  const candidateSummary = useMemo(() => {
    if (!primaryCandidate) {
      return null;
    }
    if (primaryCandidate.has_obsidian_config) {
      return tWizard('candidateObsidian', { count: primaryCandidate.markdown_file_count });
    }
    if (primaryCandidate.markdown_file_count > 0) {
      return tWizard('candidateMarkdown', { count: primaryCandidate.markdown_file_count });
    }
    return tWizard('candidateGeneric');
  }, [primaryCandidate, tWizard]);

  const ensureProjectForBind = useCallback(async (): Promise<Project | null> => {
    if (project) {
      return project;
    }
    setPreparing(true);
    try {
      const existing = await getProjects();
      const bound = existing.find((item) => Boolean(item.workspacePath?.trim()));
      if (bound) {
        setProject(bound);
        return bound;
      }
      if (existing.length > 0) {
        setProject(existing[0] ?? null);
        return existing[0] ?? null;
      }
      const created = await createProject(defaultProjectName);
      setProject(created);
      return created;
    } finally {
      setPreparing(false);
    }
  }, [defaultProjectName, project]);

  const handleChooseFolder = useCallback(async () => {
    const target = await ensureProjectForBind();
    if (!target) {
      return;
    }
    setMountOpen(true);
  }, [ensureProjectForBind]);

  const handleBound = useCallback(
    (workspacePath: string | null) => {
      if (project?.id && workspacePath) {
        queueMigrationBoundProjectId(project.id);
        setBoundPath(workspacePath);
        const activeChatId = useChatStore.getState().chatId?.trim();
        if (activeChatId) {
          void applyMigrationBoundProjectToChat(activeChatId);
        }
      }
      clearMigrationWorkspaceBindCandidates();
      onBound?.();
    },
    [onBound, project?.id],
  );

  if (boundPath) {
    return (
      <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-left text-sm text-emerald-700 dark:text-emerald-400">
        {tWizard('linkedSuccess')}
      </div>
    );
  }

  return (
    <div
      className={cn(
        'rounded-xl border border-border/60 bg-card/40 px-4 py-4 sm:px-5 sm:py-5 text-left space-y-3',
        className,
      )}
    >
      <div>
        <div className="text-sm font-medium">{tWizard('title')}</div>
        <p className="mt-1 text-xs text-muted-foreground leading-relaxed">{tWizard('description')}</p>
      </div>
      {primaryCandidate && (
        <div className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground space-y-1">
          <div className="font-medium text-foreground/90">{primaryCandidate.label}</div>
          <div className="truncate">{primaryCandidate.path}</div>
          {candidateSummary && <div>{candidateSummary}</div>}
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          className="h-8 w-full sm:w-auto"
          disabled={preparing}
          onClick={() => void handleChooseFolder()}
        >
          {preparing ? tWizard('preparing') : tWizard('chooseFolder')}
        </Button>
        {showSkip && onSkip && (
          <Button size="sm" variant="ghost" onClick={onSkip}>
            {tWizard('skip')}
          </Button>
        )}
      </div>
      {project && mountOpen && (
        <ProjectWorkspaceMount
          projectId={project.id}
          projectName={project.name}
          initialPath={primaryCandidate?.path ?? project.workspacePath}
          open={mountOpen}
          onOpenChange={setMountOpen}
          onBound={handleBound}
        />
      )}
    </div>
  );
}
