'use client';

/**
 * [INPUT]
 * @/services/skill::listSkills (POS: 技能列表 API)
 * @/lib/utils/agent-config::sanitizeCommandToken, parseAliasList, BindingIssue (POS: 命令绑定清洗/校验纯逻辑)
 *
 * [OUTPUT]
 * CommandBindingsEditor: 斜杠命令绑定的受控行列表编辑器
 *
 * [POS]
 * Settings Agent 能力页命令绑定卡片的编辑区：行内折叠/展开、技能多选、别名输入。
 * 校验结果由上层按下标传入；正在编辑且尚未补全的行不提示“未完成”，避免新增行立刻报错。
 */

import { useId, useState } from 'react';
import { useTranslations } from 'next-intl';
import useSWR from 'swr';
import { AlertCircle, ArrowRight, Plus, X } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { cn } from '@/lib/utils/classnameUtils';
import { parseAliasList, sanitizeCommandToken, type BindingIssue } from '@/lib/utils/agent-config';
import type { CommandBindingConfig } from '@/services/agent';
import { listSkills } from '@/services/skill';

interface SkillOption {
  id: string;
  name: string;
}

interface CommandBindingsEditorProps {
  value: CommandBindingConfig[];
  /** 与 `value` 按下标对齐。 */
  issues: (BindingIssue | null)[];
  onChange: (bindings: CommandBindingConfig[]) => void;
}

const EMPTY_BINDING: CommandBindingConfig = {
  command_name: '',
  skill_ids: [],
  description: '',
  aliases: [],
  instruction: '',
};

export function CommandBindingsEditor({ value, issues, onChange }: CommandBindingsEditorProps) {
  const t = useTranslations('agent.commandBindings');
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const { data: skillsData, isLoading: skillsLoading } = useSWR('listSkillsForBindings', () => listSkills());
  const skills: SkillOption[] = skillsData?.skills ?? [];

  const patchBinding = (index: number, patch: Partial<CommandBindingConfig>) => {
    onChange(value.map((binding, i) => (i === index ? { ...binding, ...patch } : binding)));
  };

  const addBinding = () => {
    onChange([...value, EMPTY_BINDING]);
    setExpandedIndex(value.length);
  };

  const removeBinding = (index: number) => {
    onChange(value.filter((_, i) => i !== index));
    setExpandedIndex(null);
  };

  return (
    <div className="space-y-2">
      {value.length === 0 && (
        <div className="rounded-lg border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
          {t('empty')}
        </div>
      )}
      {value.map((binding, index) => (
        <BindingRow
          key={index}
          binding={binding}
          issue={issues[index] ?? null}
          skills={skills}
          skillsLoading={skillsLoading}
          expanded={expandedIndex === index}
          onToggle={() => setExpandedIndex(expandedIndex === index ? null : index)}
          onRemove={() => removeBinding(index)}
          onPatch={(patch) => patchBinding(index, patch)}
        />
      ))}
      <Button type="button" variant="outline" size="sm" data-testid="command-binding-add" onClick={addBinding}>
        <Plus className="h-3.5 w-3.5" />
        {t('add')}
      </Button>
    </div>
  );
}

interface BindingRowProps {
  binding: CommandBindingConfig;
  issue: BindingIssue | null;
  skills: SkillOption[];
  skillsLoading: boolean;
  expanded: boolean;
  onToggle: () => void;
  onRemove: () => void;
  onPatch: (patch: Partial<CommandBindingConfig>) => void;
}

function BindingRow({ binding, issue, skills, skillsLoading, expanded, onToggle, onRemove, onPatch }: BindingRowProps) {
  const t = useTranslations('agent.commandBindings');
  const idPrefix = useId();
  const skillIds = binding.skill_ids ?? [];
  const skillNames = skillIds.map((id) => skills.find((skill) => skill.id === id)?.name ?? id).join(', ');
  const visibleIssue = issue === 'incomplete' && expanded ? null : issue;

  const toggleSkill = (skillId: string) => {
    onPatch({
      skill_ids: skillIds.includes(skillId) ? skillIds.filter((id) => id !== skillId) : [...skillIds, skillId],
    });
  };

  // 已被删除的技能仍留在绑定里时，以选中态展示，便于用户取消。
  const orphanSkillIds = skillIds.filter((id) => !skills.some((skill) => skill.id === id));

  return (
    <div
      data-testid="command-binding-row"
      className={cn(
        'rounded-xl border bg-card/60 transition-colors',
        visibleIssue ? 'border-destructive/40' : expanded ? 'border-primary/40' : 'border-border/50',
      )}
    >
      <div className="flex items-center gap-1 pr-2">
        <button
          type="button"
          aria-expanded={expanded}
          onClick={onToggle}
          className="flex min-w-0 flex-1 items-center gap-2 rounded-xl px-3 py-2.5 text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        >
          <span className="min-w-0 shrink-[2] truncate font-mono text-xs text-primary">
            /{binding.command_name || '…'}
          </span>
          {skillIds.length > 0 && (
            <>
              <ArrowRight className="h-3 w-3 shrink-0 text-muted-foreground" />
              <span className="min-w-0 truncate text-xs text-muted-foreground">
                {skillIds.length > 1 && (
                  <span className="mr-1.5 inline-flex rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                    {t('bundle')}
                  </span>
                )}
                {skillNames}
              </span>
            </>
          )}
        </button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={t('remove')}
          data-testid="command-binding-remove"
          className="h-7 w-7 shrink-0 text-muted-foreground hover:text-destructive-text"
          onClick={onRemove}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      {visibleIssue && (
        <p className="flex items-center gap-1.5 px-3 pb-2.5 text-xs text-destructive-text">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          {t(visibleIssue === 'duplicate' ? 'issueDuplicate' : 'issueIncomplete')}
        </p>
      )}

      {expanded && (
        <div className="space-y-3 border-t border-border/40 px-3 pb-3 pt-3">
          <div className="space-y-1">
            <Label htmlFor={`${idPrefix}-name`} className="text-xs">
              {t('nameLabel')}
            </Label>
            <Input
              id={`${idPrefix}-name`}
              data-testid="command-binding-name"
              value={binding.command_name}
              onChange={(e) => onPatch({ command_name: sanitizeCommandToken(e.target.value) })}
              placeholder={t('namePlaceholder')}
              className="h-8 font-mono text-sm"
            />
          </div>

          <fieldset className="min-w-0 space-y-1">
            <legend className="text-xs font-medium leading-none">{t('skillsLabel')}</legend>
            <div className="flex max-h-40 min-h-9 flex-wrap gap-1.5 overflow-y-auto rounded-lg border border-border/50 bg-background p-2">
              {skills.map((skill) => (
                <SkillChip
                  key={skill.id}
                  label={skill.name}
                  selected={skillIds.includes(skill.id)}
                  onClick={() => toggleSkill(skill.id)}
                />
              ))}
              {orphanSkillIds.map((id) => (
                <SkillChip key={id} label={id} selected onClick={() => toggleSkill(id)} />
              ))}
              {skills.length === 0 && orphanSkillIds.length === 0 && (
                <span className="text-xs text-muted-foreground">{skillsLoading ? t('loading') : t('skillsEmpty')}</span>
              )}
            </div>
          </fieldset>

          <div className="space-y-1">
            <Label htmlFor={`${idPrefix}-description`} className="text-xs">
              {t('descriptionLabel')}
            </Label>
            <Input
              id={`${idPrefix}-description`}
              value={binding.description ?? ''}
              onChange={(e) => onPatch({ description: e.target.value })}
              placeholder={t('descriptionPlaceholder')}
              className="h-8 text-sm"
            />
          </div>

          {skillIds.length > 1 && (
            <div className="space-y-1">
              <Label htmlFor={`${idPrefix}-instruction`} className="text-xs">
                {t('instructionLabel')}
              </Label>
              <Input
                id={`${idPrefix}-instruction`}
                value={binding.instruction ?? ''}
                onChange={(e) => onPatch({ instruction: e.target.value })}
                placeholder={t('instructionPlaceholder')}
                className="h-8 text-sm"
              />
            </div>
          )}

          <AliasesInput
            id={`${idPrefix}-aliases`}
            aliases={binding.aliases ?? []}
            onChange={(aliases) => onPatch({ aliases })}
          />
        </div>
      )}
    </div>
  );
}

function SkillChip({ label, selected, onClick }: { label: string; selected: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      data-testid="command-binding-skill"
      onClick={onClick}
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-1 text-xs transition-colors',
        selected ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:bg-muted/80',
      )}
    >
      {label}
    </button>
  );
}

/** 输入框保留原始文本（含逗号与空格），仅向上提交清洗后的别名列表，失焦后回到规范写法；同一时刻只有一行展开，行切换即重新挂载。 */
function AliasesInput({
  id,
  aliases,
  onChange,
}: {
  id: string;
  aliases: string[];
  onChange: (aliases: string[]) => void;
}) {
  const t = useTranslations('agent.commandBindings');
  const [text, setText] = useState(() => aliases.join(', '));

  return (
    <div className="space-y-1">
      <Label htmlFor={id} className="text-xs">
        {t('aliasesLabel')}
      </Label>
      <Input
        id={id}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          onChange(parseAliasList(e.target.value));
        }}
        onBlur={() => setText(aliases.join(', '))}
        placeholder={t('aliasesPlaceholder')}
        className="h-8 text-sm"
      />
    </div>
  );
}
