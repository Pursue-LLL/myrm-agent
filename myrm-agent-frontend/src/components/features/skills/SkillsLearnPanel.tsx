'use client';

/**
 * [INPUT]
 * @/store/useChatStore::sendMessage (POS: Active chat state manager)
 * @/lib/skills/composeLearnSlashMessage (POS: raw /learn composition)
 * @/lib/skills/submitLearnMessage (POS: learn submit helper)
 *
 * [OUTPUT]
 * SkillsLearnPanel: Settings installed-tab learn wizard (directory · URL · text + scenario chips).
 *
 * [POS]
 * GUI-first /learn entry on Skills settings; sends raw slash for server learn_handler SSOT rewrite.
 */

import { memo, useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { ChevronDown } from 'lucide-react';
import { IconGlow } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/primitives/collapsible';
import { toast } from 'sonner';
import useChatStore from '@/store/useChatStore';
import { composeLearnSlashMessage } from '@/lib/skills/composeLearnSlashMessage';
import { submitLearnMessage } from '@/lib/skills/submitLearnMessage';
import { cn } from '@/lib/utils/classnameUtils';

type LearnScenarioId = 'sdk' | 'deploy' | 'debug' | 'writing' | 'release' | 'book';

const SCENARIO_IDS: LearnScenarioId[] = ['sdk', 'deploy', 'debug', 'writing', 'release', 'book'];

const SCENARIO_REQUIRES_CHAT: ReadonlySet<LearnScenarioId> = new Set(['deploy']);

interface SkillsLearnPanelProps {
  className?: string;
}

const SkillsLearnPanel = memo(({ className }: SkillsLearnPanelProps) => {
  const t = useTranslations('settings.skills.learn');
  const tChat = useTranslations('chat');
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [learnDir, setLearnDir] = useState('');
  const [learnUrl, setLearnUrl] = useState('');
  const [learnText, setLearnText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeScenario, setActiveScenario] = useState<LearnScenarioId | null>(null);

  const canSubmit = Boolean(learnDir.trim() || learnUrl.trim() || learnText.trim());

  const applyScenario = useCallback(
    (scenarioId: LearnScenarioId) => {
      if (SCENARIO_REQUIRES_CHAT.has(scenarioId)) {
        const { chatId } = useChatStore.getState();
        if (!chatId) {
          toast.warning(t('noActiveChat'));
          return;
        }
      }

      setActiveScenario(scenarioId);
      setLearnText(t(`scenarios.${scenarioId}.text`));
    },
    [t],
  );

  const handleSubmit = useCallback(async () => {
    const message = composeLearnSlashMessage({
      directory: learnDir,
      url: learnUrl,
      text: learnText,
    });
    if (!message) {
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await submitLearnMessage({ input: message });
      if (result.ok) {
        toast.info(tChat('extractToSkill.started'));
        router.push(`/${result.chatId}`);
        setLearnDir('');
        setLearnUrl('');
        setLearnText('');
        setActiveScenario(null);
        setIsOpen(false);
      } else if (result.reason === 'no_chat') {
        toast.warning(t('noActiveChat'));
      } else if (result.reason === 'busy') {
        toast.warning(tChat('extractToSkill.busy'));
      } else if (result.reason === 'error') {
        toast.error(tChat('extractToSkill.error'));
      }
    } finally {
      setIsSubmitting(false);
    }
  }, [learnDir, learnUrl, learnText, router, t, tChat]);

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} className={className}>
      <CollapsibleTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2 w-full justify-start">
          <IconGlow className="h-4 w-4 text-purple-500" />
          {t('panelTitle')}
          <ChevronDown className={cn('h-4 w-4 transition-transform ml-auto', isOpen && 'rotate-180')} />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-3 space-y-4 rounded-lg border bg-card p-4 shadow-sm">
          <p className="text-sm text-muted-foreground">{t('description')}</p>

          <div className="flex flex-wrap gap-2">
            {SCENARIO_IDS.map((scenarioId) => (
              <Button
                key={scenarioId}
                type="button"
                variant={activeScenario === scenarioId ? 'default' : 'secondary'}
                size="sm"
                className="h-8 text-xs shrink-0"
                onClick={() => applyScenario(scenarioId)}
              >
                {t(`scenarios.${scenarioId}.label`)}
              </Button>
            ))}
          </div>

          <div className="grid gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="skills-learn-dir" className="text-xs text-muted-foreground">
                {t('directoryLabel')}
              </Label>
              <Input
                id="skills-learn-dir"
                placeholder={t('directoryPlaceholder')}
                value={learnDir}
                onChange={(e) => setLearnDir(e.target.value)}
                className="text-sm"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="skills-learn-url" className="text-xs text-muted-foreground">
                {t('urlLabel')}
              </Label>
              <Input
                id="skills-learn-url"
                placeholder={t('urlPlaceholder')}
                value={learnUrl}
                onChange={(e) => setLearnUrl(e.target.value)}
                className="text-sm"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="skills-learn-text" className="text-xs text-muted-foreground">
                {t('textLabel')}
              </Label>
              <textarea
                id="skills-learn-text"
                className="min-h-[90px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                placeholder={t('textPlaceholder')}
                value={learnText}
                onChange={(e) => setLearnText(e.target.value)}
              />
            </div>
          </div>

          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="ghost" size="sm" onClick={() => setIsOpen(false)}>
              {t('cancel')}
            </Button>
            <Button
              type="button"
              size="sm"
              className="gap-2"
              disabled={!canSubmit || isSubmitting}
              onClick={() => void handleSubmit()}
            >
              <IconGlow className="h-4 w-4" />
              {t('submit')}
            </Button>
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
});

SkillsLearnPanel.displayName = 'SkillsLearnPanel';

export default SkillsLearnPanel;
