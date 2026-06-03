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
      skill_id: '',
      description: '',
      aliases: [],
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
                    <span className="text-xs font-mono text-primary shrink-0">/{binding.command_name || '...'}</span>
                    {binding.skill_id && (
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
                          {skills.find((s) => s.id === binding.skill_id)?.name || binding.skill_id}
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
                    <div className="grid grid-cols-2 gap-3">
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
                        <Label className="text-xs">{t('commandSkillId')}</Label>
                        <select
                          value={binding.skill_id}
                          onChange={(e) => updateBinding(index, 'skill_id', e.target.value)}
                          className="flex h-8 w-full rounded-full border border-input bg-transparent px-2 py-1 text-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                        >
                          <option value="">{t('commandSkillIdPlaceholder')}</option>
                          {skills.map((skill) => (
                            <option key={skill.id} value={skill.id}>
                              {skill.name}
                            </option>
                          ))}
                        </select>
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
