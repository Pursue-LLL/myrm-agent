'use client';

/**
 * [INPUT]
 * - @/services/projects::{getProjects, createProject}
 * - @/components/features/project-workspace/ProjectWorkspaceMount
 *
 * [OUTPUT]
 * - SyncFolderOnboardingStep: optional first-run folder bind
 *
 * [POS]
 * Onboarding step for GUI users to bind Obsidian/docs folder to a project.
 * Creates a project only when the user chooses to link a folder.
 */

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { createProject, getProjects, type Project } from '@/services/projects';
import ProjectWorkspaceMount from '@/components/features/project-workspace/ProjectWorkspaceMount';

interface SyncFolderOnboardingStepProps {
  onComplete: () => void;
  onSkip: () => void;
}

export default function SyncFolderOnboardingStep({ onComplete, onSkip }: SyncFolderOnboardingStepProps) {
  const t = useTranslations('boot.onboarding.syncFolder');
  const [project, setProject] = useState<Project | null>(null);
  const [mountOpen, setMountOpen] = useState(false);
  const [preparing, setPreparing] = useState(false);

  const ensureProjectForBind = useCallback(async (): Promise<Project | null> => {
    if (project) return project;
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
      const created = await createProject(t('defaultProjectName'));
      setProject(created);
      return created;
    } finally {
      setPreparing(false);
    }
  }, [project, t]);

  const handleChooseFolder = useCallback(async () => {
    const target = await ensureProjectForBind();
    if (!target) return;
    setMountOpen(true);
  }, [ensureProjectForBind]);

  const handleBound = useCallback(() => {
    onComplete();
  }, [onComplete]);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground leading-relaxed">{t('hint')}</p>
      <Button className="w-full sm:w-auto" disabled={preparing} onClick={() => void handleChooseFolder()}>
        {preparing ? t('preparing') : t('chooseFolder')}
      </Button>
      {project && mountOpen && (
        <ProjectWorkspaceMount
          projectId={project.id}
          projectName={project.name}
          initialPath={project.workspacePath}
          open={mountOpen}
          onOpenChange={setMountOpen}
          onBound={handleBound}
        />
      )}
      <div className="flex justify-center pt-2">
        <Button variant="ghost" onClick={onSkip}>
          {t('skip')}
        </Button>
      </div>
    </div>
  );
}
