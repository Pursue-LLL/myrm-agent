'use client';

import React, { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import useSWR from 'swr';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { listSkills } from '@/services/skill';
import type { CommandBindingConfig } from '@/services/agent';
import { cn } from '@/lib/utils';

interface CommandBindingsEditorProps {
  value: CommandBindingConfig[];
  onChange: (bindings: CommandBindingConfig[]) => void;
}

export function CommandBindingsEditor({ value, onChange }: CommandBindingsEditorProps) {
  const t = useTranslations('Agent.form');
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  const { data: skillsData } = useSWR('listSkillsForBindings', () => listSkills());
  const skills = skillsData?.skills ?? [];

  const addBinding = useCallback(() => {
    const newBinding: CommandBindingConfig = {
      command_name: '',
      skill_ids: [],
      description: '',
      aliases: [],
      instruction: '',
    };
    onChange([...value, newBinding]);
    setExpandedIndex(value.length);
  }, [value, onChange]);

  const removeBinding = useCallback(
    (index: number) => {
      const updated = value.filter((_, i) => i !== index);
      onChange(updated);
      setExpandedIndex(null);
    },
    [value, onChange],
  );

  const updateBinding = useCallback(
    (index: number, field: keyof CommandBindingConfig, fieldValue: string | string[]) => {
      const updated = value.map((binding, i) => (i === index ? { ...binding, [field]: fieldValue } : binding));
      onChange(updated);
    },
    [value, onChange],
  );

  const toggleSkill = useCallback(
    (index: number, skillId: string) => {
      const binding = value[index];
      const current = binding.skill_ids || [];
      const next = current.includes(skillId) ? current.filter((id) => id !== skillId) : [...current, skillId];
      updateBinding(index, 'skill_ids', next);
    },
    [value, updateBinding],
  );

  const getSkillNames = (ids: string[]): string => {
    if (!ids.length) return '';
    return ids
      .map((id) => skills.find((s) => s.id === id)?.name || id)
      .join(', ');
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <Label className="text-sm font-medium">{t('commandBindings')}</Label>
          <p className="text-xs text-muted-foreground mt-0.5">{t('commandBindingsHint')}</p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={addBinding} className="h-7 text-xs">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="mr-1"
          >
            <path d="M12 5v14" />
            <path d="M5 12h14" />
          </svg>
          {t('addCommandBinding')}
        </Button>
      </div>

      {value.length === 0 ? (
        <div className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
          {t('noCommandBindings')}
        </div>
      ) : (
        <div className="space-y-2">
          {value.map((binding, index) => {
            const isExpanded = expandedIndex === index;
            const skillIds = binding.skill_ids || [];
            const isBundle = skillIds.length > 1;
            return (
              <div
                key={index}
                className={cn(
                  'rounded-lg border bg-card transition-all',
                  isExpanded ? 'ring-1 ring-primary/30' : 'hover:border-primary/30',
                )}
              >
                <div
                  className="flex items-center gap-2 px-3 py-2 cursor-pointer select-none"
                  onClick={() => setExpandedIndex(isExpanded ? null : index)}
                >
                  <div className="flex-1 flex items-center gap-2 min-w-0">
                    <span className="text-xs font-mono text-primary shrink-0">
                      /{binding.command_name || '...'}
                    </span>
                    {skillIds.length > 0 && (
                      <>
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          width="12"
                          height="12"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          className="text-muted-foreground shrink-0"
                        >
                          <path d="M5 12h14" />
                          <path d="m12 5 7 7-7 7" />
                        </svg>
                        <span className="text-xs text-muted-foreground truncate">
                          {isBundle && (
                            <span className="inline-flex items-center rounded bg-primary/10 px-1 py-0.5 text-[10px] font-medium text-primary mr-1">
                              Bundle
                            </span>
                          )}
                          {getSkillNames(skillIds)}
                        </span>
                      </>
                    )}
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive shrink-0"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeBinding(index);
                    }}
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M18 6 6 18" />
                      <path d="m6 6 12 12" />
                    </svg>
                  </Button>
                </div>

                {isExpanded && (
                  <div className="px-3 pb-3 pt-1 border-t space-y-3">
                    <div className="space-y-1">
                      <Label className="text-xs">{t('commandName')}</Label>
                      <Input
                        value={binding.command_name}
                        onChange={(e) => {
                          const sanitized = e.target.value.replace(/[^a-zA-Z0-9_-]/g, '');
                          updateBinding(index, 'command_name', sanitized);
                        }}
                        placeholder={t('commandNamePlaceholder')}
                        className="h-8 text-sm font-mono"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">
                        {t('commandSkillId')}
                        {skillIds.length > 1 && (
                          <span className="ml-1 text-[10px] text-primary font-normal">
                            ({skillIds.length} skills)
                          </span>
                        )}
                      </Label>
                      <div className="flex flex-wrap gap-1.5 p-2 rounded-lg border bg-background min-h-[36px]">
                        {skills.map((skill) => {
                          const isSelected = skillIds.includes(skill.id);
                          return (
                            <button
                              key={skill.id}
                              type="button"
                              onClick={() => toggleSkill(index, skill.id)}
                              className={cn(
                                'inline-flex items-center rounded-md px-2 py-0.5 text-xs transition-colors',
                                isSelected
                                  ? 'bg-primary text-primary-foreground'
                                  : 'bg-muted text-muted-foreground hover:bg-muted/80',
                              )}
                            >
                              {skill.name}
                            </button>
                          );
                        })}
                        {skills.length === 0 && (
                          <span className="text-xs text-muted-foreground">{t('commandSkillIdPlaceholder')}</span>
                        )}
                      </div>
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">{t('commandDescription')}</Label>
                      <Input
                        value={binding.description || ''}
                        onChange={(e) => updateBinding(index, 'description', e.target.value)}
                        placeholder={t('commandDescriptionPlaceholder')}
                        className="h-8 text-sm"
                      />
                    </div>
                    {skillIds.length > 1 && (
                      <div className="space-y-1">
                        <Label className="text-xs">{t('commandInstruction') || 'Bundle Instruction'}</Label>
                        <Input
                          value={binding.instruction || ''}
                          onChange={(e) => updateBinding(index, 'instruction', e.target.value)}
                          placeholder={t('commandInstructionPlaceholder') || 'Optional guidance for combined skills...'}
                          className="h-8 text-sm"
                        />
                      </div>
                    )}
                    <div className="space-y-1">
                      <Label className="text-xs">{t('commandAliases')}</Label>
                      <Input
                        value={(binding.aliases || []).join(', ')}
                        onChange={(e) => {
                          const aliases = e.target.value
                            .split(',')
                            .map((s) => s.trim())
                            .filter(Boolean);
                          updateBinding(index, 'aliases', aliases);
                        }}
                        placeholder={t('commandAliasesPlaceholder')}
                        className="h-8 text-sm"
                      />
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
