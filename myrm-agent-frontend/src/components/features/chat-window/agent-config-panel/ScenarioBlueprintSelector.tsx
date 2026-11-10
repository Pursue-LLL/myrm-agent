'use client';

import { memo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { AiNetworkIcon } from 'hugeicons-react';
import { cn } from '@/lib/utils/classnameUtils';
import useChatStore from '@/store/useChatStore';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Switch } from '@/components/primitives/switch';
import {
  BLUEPRINT_TEMPLATES,
  type BlueprintSubagent,
  type BlueprintTemplate,
  type ContextMode,
} from './blueprintTemplates';

const OFF = '__off__';
const CUSTOM = '__custom__';

type Team = Record<string, unknown> | undefined;

/** 当前团队对应的选项：以蓝图首个成员识别蓝图，有成员却不属于任何蓝图就是自定义团队。 */
function selectedOption(team: Team): string {
  const members = Object.keys(team ?? {});
  if (members.length === 0) {
    return OFF;
  }
  const blueprint = BLUEPRINT_TEMPLATES.find((template) => members.includes(Object.keys(template.subagents)[0]));
  return blueprint?.id ?? CUSTOM;
}

/** 成员缺省 context_mode 时智能体按 isolated 运行，所以只有每个成员都是 fork 才算继承对话记忆；没有团队时按默认继承。 */
function inheritsMemory(team: Team): boolean {
  return Object.values(team ?? {}).every(
    (member) =>
      typeof member === 'object' && member !== null && 'context_mode' in member && member.context_mode === 'fork',
  );
}

/** 按蓝图组建团队：成员与工具清单都是副本，不会改到共享的蓝图。 */
function formTeam(template: BlueprintTemplate, mode: ContextMode): Record<string, BlueprintSubagent> {
  return Object.fromEntries(
    Object.entries(template.subagents).map(([name, member]) => [
      name,
      { ...member, tools: [...member.tools], context_mode: mode },
    ]),
  );
}

function withContextMode(team: Record<string, unknown>, mode: ContextMode): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(team).map(([name, member]) => [
      name,
      { ...(typeof member === 'object' ? member : {}), context_mode: mode },
    ]),
  );
}

/**
 * 场景化蓝图选择器 (JIT 一键编队)
 *
 * 记忆开关读自团队成员本身，所以面板折叠再展开、切换会话后都与实际配置一致。
 */
const ScenarioBlueprintSelector = memo(() => {
  const t = useTranslations('agent.configPanel');
  const team = useChatStore((state) => state.agentConfig?.ephemeralSubagents);
  const updateAgentConfig = useChatStore((state) => state.updateAgentConfig);

  const selected = selectedOption(team);
  const inherit = inheritsMemory(team);

  const handleChange = useCallback(
    (value: string) => {
      if (value === OFF) {
        updateAgentConfig({ ephemeralSubagents: {} });
        return;
      }
      const template = BLUEPRINT_TEMPLATES.find((candidate) => candidate.id === value);
      if (template) {
        updateAgentConfig({ ephemeralSubagents: formTeam(template, inherit ? 'fork' : 'isolated') });
      }
    },
    [updateAgentConfig, inherit],
  );

  const handleToggleInherit = useCallback(
    (checked: boolean) => {
      if (team) {
        updateAgentConfig({ ephemeralSubagents: withContextMode(team, checked ? 'fork' : 'isolated') });
      }
    },
    [team, updateAgentConfig],
  );

  return (
    <div className="flex flex-col gap-2 mt-3">
      <div className="flex items-center gap-2">
        <AiNetworkIcon size={14} className="text-blue-500 flex-shrink-0" />
        <span className="text-xs text-muted-foreground whitespace-nowrap">{t('jitTeam')}</span>
        {/* 自定义团队不是列表里的选项：清空选中值，让触发器显示占位文案 */}
        <Select value={selected === CUSTOM ? '' : selected} onValueChange={handleChange}>
          <SelectTrigger
            className={cn(
              'flex-1 min-w-0 h-7 text-xs px-2 rounded-full border-border/50',
              selected !== OFF && 'border-blue-400/50 bg-blue-50/30 dark:bg-blue-950/20',
            )}
          >
            <SelectValue placeholder={t('jitTeamCustom')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={OFF}>{t('jitTeamOff')}</SelectItem>
            {BLUEPRINT_TEMPLATES.map((template) => (
              <SelectItem key={template.id} value={template.id}>
                {t(`blueprints.${template.id}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {selected !== OFF && (
        <div className="flex items-center gap-2 mt-1 ml-1 pl-5">
          <Switch
            checked={inherit}
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
