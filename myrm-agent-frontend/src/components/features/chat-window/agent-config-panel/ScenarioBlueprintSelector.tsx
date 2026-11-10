'use client';

import { memo, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { AiNetworkIcon } from 'hugeicons-react';
import { cn } from '@/lib/utils/classnameUtils';
import useChatStore from '@/store/useChatStore';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Switch } from '@/components/primitives/switch';
import { BLUEPRINT_TEMPLATES } from './blueprintTemplates';

/**
 * 场景化蓝图选择器 (JIT 一键编队)
 */
const ScenarioBlueprintSelector = memo(() => {
  const t = useTranslations('agent.configPanel');
  const agentConfig = useChatStore((state) => state.agentConfig);
  const updateAgentConfig = useChatStore((state) => state.updateAgentConfig);

  // 这里的 selected 用 ID 匹配 ephemeralSubagents
  const selected =
    agentConfig?.ephemeralSubagents && Object.keys(agentConfig.ephemeralSubagents).length > 0
      ? Object.keys(agentConfig.ephemeralSubagents).includes('web_researcher')
        ? 'research_squad'
        : Object.keys(agentConfig.ephemeralSubagents).includes('security_expert')
          ? 'code_audit_squad'
          : '__custom__'
      : '__off__';

  const [inheritMemory, setInheritMemory] = useState(true);

  const handleChange = useCallback(
    (value: string) => {
      if (value === '__off__') {
        updateAgentConfig({ ephemeralSubagents: {} });
        return;
      }
      const template = BLUEPRINT_TEMPLATES.find((t) => t.id === value);
      if (template) {
        // Apply current inheritMemory preference to the template
        const subagents = JSON.parse(JSON.stringify(template.subagents));
        Object.keys(subagents).forEach((key) => {
          subagents[key].context_mode = inheritMemory ? 'fork' : 'isolated';
        });
        updateAgentConfig({ ephemeralSubagents: subagents });
      }
    },
    [updateAgentConfig, inheritMemory],
  );

  const handleToggleInherit = useCallback(
    (checked: boolean) => {
      setInheritMemory(checked);
      if (selected !== '__off__' && agentConfig?.ephemeralSubagents) {
        const subagents = JSON.parse(JSON.stringify(agentConfig.ephemeralSubagents));
        Object.keys(subagents).forEach((key) => {
          subagents[key].context_mode = checked ? 'fork' : 'isolated';
        });
        updateAgentConfig({ ephemeralSubagents: subagents });
      }
    },
    [selected, agentConfig, updateAgentConfig],
  );

  return (
    <div className="flex flex-col gap-2 mt-3">
      <div className="flex items-center gap-2">
        <AiNetworkIcon size={14} className="text-blue-500 flex-shrink-0" />
        <span className="text-xs text-muted-foreground whitespace-nowrap">{t('jitTeam')}</span>
        <Select value={selected} onValueChange={handleChange}>
          <SelectTrigger
            className={cn(
              'flex-1 min-w-0 h-7 text-xs px-2 rounded-full border-border/50',
              selected !== '__off__' && 'border-blue-400/50 bg-blue-50/30 dark:bg-blue-950/20',
            )}
          >
            <SelectValue placeholder={t('jitTeamPlaceholder')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__off__">{t('jitTeamOff')}</SelectItem>
            {BLUEPRINT_TEMPLATES.map((a) => (
              <SelectItem key={a.id} value={a.id}>
                {t(`blueprints.${a.id}` as 'blueprints.research_squad' | 'blueprints.code_audit_squad')}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {selected !== '__off__' && (
        <div className="flex items-center gap-2 mt-1 ml-1 pl-5">
          <Switch
            checked={inheritMemory}
            onCheckedChange={handleToggleInherit}
            aria-label={t('jitInheritMemory')}
            className="scale-75 origin-left"
          />
          <span className="text-xs text-muted-foreground">{t('jitInheritMemory')}</span>
        </div>
      )}
    </div>
  );
});
ScenarioBlueprintSelector.displayName = 'ScenarioBlueprintSelector';

export default ScenarioBlueprintSelector;
