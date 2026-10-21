'use client';

/**
 * [INPUT]
 * - @/components/features/settings/sections/knowledge/MigrationVaultBindPanel
 * - @/lib/migrationChatHandoff::readMigrationWorkspaceBindCandidates
 *
 * [OUTPUT]
 * - SyncFolderOnboardingStep: optional first-run folder bind
 *
 * [POS]
 * Onboarding step for GUI users to bind Obsidian/docs folder to a project.
 * Pre-fills paths discovered during competitor migration when available.
 */

import { useMemo } from 'react';
import { readMigrationWorkspaceBindCandidates } from '@/lib/migrationChatHandoff';
import MigrationVaultBindPanel from '@/components/features/settings/sections/knowledge/MigrationVaultBindPanel';

interface SyncFolderOnboardingStepProps {
  onComplete: () => void;
  onSkip: () => void;
}

export default function SyncFolderOnboardingStep({ onComplete, onSkip }: SyncFolderOnboardingStepProps) {
  const candidates = useMemo(() => readMigrationWorkspaceBindCandidates(), []);

  return (
    <MigrationVaultBindPanel
      candidates={candidates}
      onBound={onComplete}
      onSkip={onSkip}
      showSkip
      defaultProjectNameKey="syncFolder"
    />
  );
}
