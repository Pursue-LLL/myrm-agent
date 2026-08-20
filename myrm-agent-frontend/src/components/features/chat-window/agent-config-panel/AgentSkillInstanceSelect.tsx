'use client';

import { memo, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Button } from '@/components/primitives/button';

const AUTO_VALUE = '__auto__';

interface AgentSkillInstanceSelectProps {
  skillName: string;
  value?: string | null;
  onChange: (instanceName: string | null) => void;
  instances?: string[];
  disabled?: boolean;
}

export const AgentSkillInstanceSelect = memo<AgentSkillInstanceSelectProps>(
  ({ skillName, value, onChange, instances: preloadedInstances, disabled = false }) => {
    const t = useTranslations('agent.configPanel.skillInstance');
    const [instances, setInstances] = useState<string[]>(preloadedInstances ?? []);
    const [loading, setLoading] = useState(preloadedInstances === undefined);

    useEffect(() => {
      if (preloadedInstances !== undefined) {
        setInstances(preloadedInstances);
        setLoading(false);
        return;
      }

      let cancelled = false;
      const load = async () => {
        setLoading(true);
        try {
          const response = await fetch(`/api/v1/skills/${encodeURIComponent(skillName)}/instances`);
          if (!response.ok) {
            if (!cancelled) {
              setInstances([]);
            }
            return;
          }
          const data = (await response.json()) as { instances?: string[] };
          if (!cancelled) {
            setInstances(Array.isArray(data.instances) ? data.instances : []);
          }
        } catch {
          if (!cancelled) {
            setInstances([]);
          }
        } finally {
          if (!cancelled) {
            setLoading(false);
          }
        }
      };
      void load();
      return () => {
        cancelled = true;
      };
    }, [skillName, preloadedInstances]);

    if (loading) {
      return null;
    }

    const boundName = value?.trim() ?? '';
    const isStaleBinding = boundName.length > 0 && !instances.includes(boundName);

    if (isStaleBinding) {
      return (
        <div
          className="flex flex-col gap-1.5 px-2 py-1.5 bg-amber-500/10 rounded-lg border border-amber-500/30 no-card-click min-w-[140px] max-w-[220px]"
          onClick={(e) => e.stopPropagation()}
        >
          <p className="text-[10px] leading-snug text-amber-700 dark:text-amber-400">
            {t('staleWarning', { name: boundName })}
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-6 px-2 text-[10px] border-amber-500/40 text-amber-800 dark:text-amber-300"
            disabled={disabled}
            onClick={() => onChange(null)}
          >
            {t('staleClear')}
          </Button>
        </div>
      );
    }

    if (instances.length <= 1) {
      return null;
    }

    const selectValue = boundName && instances.includes(boundName) ? boundName : AUTO_VALUE;

    return (
      <div
        className="flex items-center gap-2 px-2 py-1 bg-background/50 rounded-lg border border-border/50 no-card-click min-w-[140px]"
        onClick={(e) => e.stopPropagation()}
      >
        <span className="text-[10px] font-medium text-muted-foreground shrink-0">{t('label')}</span>
        <Select
          value={selectValue}
          onValueChange={(next) => {
            onChange(next === AUTO_VALUE ? null : next);
          }}
          disabled={disabled}
        >
          <SelectTrigger className="h-7 text-xs border-0 bg-transparent shadow-none px-1 min-w-[96px]">
            <SelectValue placeholder={t('placeholder')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={AUTO_VALUE}>{t('auto')}</SelectItem>
            {instances.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    );
  },
);

AgentSkillInstanceSelect.displayName = 'AgentSkillInstanceSelect';
