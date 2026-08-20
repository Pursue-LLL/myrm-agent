'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { getDocsUrl } from '@/lib/deploy-mode';
import useChatStore from '@/store/useChatStore';

const TEAM_KB_SCENARIO_KEYS = ['opsSop', 'onboardingGuide', 'projectRetro', 'customerFaq', 'inspectionMaint'] as const;

type TeamKbScenarioKey = (typeof TEAM_KB_SCENARIO_KEYS)[number];

interface SecondBrainPitfallGuardrailsProps {
  agentId?: string | null;
  onUseAgent?: () => void;
  onGoToImport?: () => void;
}

export default function SecondBrainPitfallGuardrails({
  agentId,
  onUseAgent,
  onGoToImport,
}: SecondBrainPitfallGuardrailsProps) {
  const t = useTranslations('settings.wiki.secondBrain.pitfalls');
  const router = useRouter();

  const handleTeamScenario = (key: TeamKbScenarioKey) => {
    const prompt = t(`teamKb.scenarios.${key}.prompt`);
    useChatStore.getState().setInputMessage(prompt);
    if (agentId && onUseAgent) {
      onUseAgent();
    }
    router.push('/');
  };

  return (
    <div
      className="space-y-4 rounded-lg border border-border/60 bg-muted/20 p-4"
      data-testid="second-brain-pitfall-panel"
    >
      <div className="space-y-1">
        <h4 className="text-sm font-semibold text-foreground">{t('syncExpectation.title')}</h4>
        <p className="text-xs leading-relaxed text-muted-foreground">{t('syncExpectation.body')}</p>
      </div>

      <div className="space-y-2" data-testid="second-brain-obsidian-pitfall">
        <h4 className="text-sm font-semibold text-foreground">{t('obsidianGit.title')}</h4>
        <p className="text-xs leading-relaxed text-muted-foreground">{t('obsidianGit.body')}</p>
        {onGoToImport ? (
          <Button type="button" variant="link" size="sm" className="h-auto p-0 text-xs" onClick={onGoToImport}>
            {t('obsidianGit.cta')}
          </Button>
        ) : null}
      </div>

      <div className="space-y-2" data-testid="second-brain-troubleshooting-ladder">
        <h4 className="text-sm font-semibold text-foreground">{t('ladder.title')}</h4>
        <ol className="list-decimal space-y-1.5 pl-4 text-xs text-muted-foreground">
          <li>
            <Link href={getDocsUrl('/core-concepts/wiki')} className="text-primary underline-offset-2 hover:underline">
              {t('ladder.stepDocs')}
            </Link>
          </li>
          <li>{t('ladder.stepAgent')}</li>
          <li>{t('ladder.stepCoach')}</li>
        </ol>
      </div>

      <div className="space-y-2" data-testid="second-brain-team-kb-scenarios">
        <h4 className="text-sm font-semibold text-foreground">{t('teamKb.title')}</h4>
        <p className="text-xs text-muted-foreground">{t('teamKb.description')}</p>
        <div className="flex flex-wrap gap-2">
          {TEAM_KB_SCENARIO_KEYS.map((key) => (
            <Button
              key={key}
              type="button"
              variant="outline"
              size="sm"
              className="h-auto whitespace-normal py-1.5 text-left text-xs"
              data-testid={`second-brain-team-kb-${key}`}
              onClick={() => handleTeamScenario(key)}
            >
              {t(`teamKb.scenarios.${key}.label`)}
            </Button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">{t('teamKb.wikiLinkTip')}</p>
      </div>

      <div className="space-y-1" data-testid="second-brain-extract-taxonomy">
        <h4 className="text-sm font-semibold text-foreground">{t('extractFailures.title')}</h4>
        <p className="text-xs leading-relaxed text-muted-foreground">{t('extractFailures.body')}</p>
      </div>
    </div>
  );
}
