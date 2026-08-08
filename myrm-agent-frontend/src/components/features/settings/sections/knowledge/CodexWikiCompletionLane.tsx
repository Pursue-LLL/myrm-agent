'use client';

import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import {
  queueMigrationObsidianVaultImport,
  type MigrationWorkspaceBindCandidate,
} from '@/lib/migrationChatHandoff';
import { applySecondBrainPreset } from '@/services/onboarding';

interface CodexWikiCompletionLaneProps {
  targetAgentId: string;
  vaultCandidate?: MigrationWorkspaceBindCandidate | null;
}

export default function CodexWikiCompletionLane({
  targetAgentId,
  vaultCandidate = null,
}: CodexWikiCompletionLaneProps) {
  const t = useTranslations('memory.migrationWizard.result.codexCompletion');
  const router = useRouter();

  const wikiUrl = `/settings/wiki?agentId=${encodeURIComponent(targetAgentId)}`;

  const goWikiImport = () => {
    if (vaultCandidate?.path) {
      queueMigrationObsidianVaultImport({
        vaultPath: vaultCandidate.path,
        targetAgentId,
      });
    }
    router.push(`${wikiUrl}#wiki-obsidian-import`);
  };

  const goGraph = () => {
    router.push(`/library?tab=graph&agentId=${encodeURIComponent(targetAgentId)}`);
  };

  const handleApplySecondBrain = async () => {
    try {
      const result = await applySecondBrainPreset();
      toast.success(result.message);
      router.push(wikiUrl);
    } catch {
      toast.error(t('applyFailed'));
    }
  };

  return (
    <div
      className="mx-auto w-full max-w-xl space-y-3 rounded-xl border border-primary/25 bg-primary/5 px-4 py-4 text-left"
      data-testid="codex-wiki-completion-lane"
    >
      <div className="space-y-1">
        <h3 className="text-sm font-semibold text-foreground">{t('title')}</h3>
        <p className="text-xs leading-relaxed text-muted-foreground">{t('description')}</p>
        {vaultCandidate ? (
          <div
            className="rounded-md border border-border/50 bg-background/70 px-3 py-2 text-xs text-muted-foreground"
            data-testid="codex-completion-vault-hint"
          >
            <div className="font-medium text-foreground/90">{vaultCandidate.label}</div>
            <div className="truncate">{vaultCandidate.path}</div>
            <p className="mt-1">{t('vaultHint')}</p>
          </div>
        ) : null}
        <ol className="list-decimal space-y-1 pl-4 text-xs text-muted-foreground">
          <li>{t('steps.importVault')}</li>
          <li>{t('steps.secondBrain')}</li>
          <li>{t('steps.graph')}</li>
        </ol>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="default" onClick={goWikiImport} data-testid="codex-completion-import-wiki">
          {t('actions.importWiki')}
        </Button>
        <Button size="sm" variant="outline" onClick={() => void handleApplySecondBrain()} data-testid="codex-completion-second-brain">
          {t('actions.secondBrain')}
        </Button>
        <Button size="sm" variant="outline" onClick={goGraph} data-testid="codex-completion-view-graph">
          {t('actions.viewGraph')}
        </Button>
      </div>
    </div>
  );
}
