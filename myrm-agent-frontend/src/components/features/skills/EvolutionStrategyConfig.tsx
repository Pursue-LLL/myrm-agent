import { useTranslations } from 'next-intl';
import { useSkillStore } from '@/store/skill';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Label } from '@/components/primitives/label';

export function EvolutionStrategyConfig() {
  const t = useTranslations('skills.evolution_strategy');
  const { evolutionStrategy, updateEvolutionStrategy } = useSkillStore();

  return (
    <div className="flex flex-col space-y-4 p-4 border rounded-md bg-card/50">
      <div className="space-y-1">
        <Label className="text-base font-semibold">{t('title')}</Label>
        <p className="text-sm text-muted-foreground">{t('description')}</p>
      </div>
      <Select value={evolutionStrategy} onValueChange={updateEvolutionStrategy}>
        <SelectTrigger className="w-full sm:w-[400px]">
          <SelectValue placeholder={t('balanced')} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="balanced">{t('balanced')}</SelectItem>
          <SelectItem value="innovate">{t('innovate')}</SelectItem>
          <SelectItem value="harden">{t('harden')}</SelectItem>
          <SelectItem value="repair-only">{t('repair_only')}</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}
