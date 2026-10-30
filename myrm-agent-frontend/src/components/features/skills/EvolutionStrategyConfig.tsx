import { useId } from 'react';
import { useTranslations } from 'next-intl';
import { useSkillStore } from '@/store/skill';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Label } from '@/components/primitives/label';

const STRATEGIES = ['balanced', 'innovate'] as const;
type Strategy = (typeof STRATEGIES)[number];

// The server reads any stored value other than "innovate" as "balanced"; the UI mirrors that.
function toStrategy(value: string): Strategy {
  return value === 'innovate' ? 'innovate' : 'balanced';
}

export function EvolutionStrategyConfig() {
  const t = useTranslations('skills.evolution_strategy');
  const { evolutionStrategy, updateEvolutionStrategy } = useSkillStore();
  const hintId = useId();
  const strategy = toStrategy(evolutionStrategy);

  return (
    <div className="flex flex-col space-y-4 p-4 border rounded-md bg-card/50">
      <div className="space-y-1">
        <Label className="text-base font-semibold">{t('title')}</Label>
        <p className="text-sm text-muted-foreground">{t('description')}</p>
      </div>
      <div className="space-y-2">
        <Select value={strategy} onValueChange={updateEvolutionStrategy}>
          <SelectTrigger className="w-full sm:w-60" aria-label={t('title')} aria-describedby={hintId}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STRATEGIES.map((option) => (
              <SelectItem key={option} value={option}>
                {t(option)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p id={hintId} className="text-xs text-muted-foreground">
          {t(`${strategy}_hint`)}
        </p>
      </div>
    </div>
  );
}
