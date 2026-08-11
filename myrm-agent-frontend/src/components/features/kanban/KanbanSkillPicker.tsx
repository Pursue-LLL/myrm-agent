'use client';

import { useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Check, ChevronsUpDown, X } from 'lucide-react';
import { useSkillStore } from '@/store/skill';
import { cn } from '@/lib/utils/classnameUtils';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
} from '@/components/primitives/command';

interface KanbanSkillPickerProps {
  /** Comma-separated skill ids, e.g. `web-search, code-review` */
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

const splitSkillIds = (value: string): string[] =>
  value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

/**
 * Multi-select skill picker for Kanban task skills.
 *
 * Keeps the comma-separated string contract so create/edit forms and persisted
 * task state remain unchanged. Skills already saved but no longer discoverable
 * are preserved and marked as unknown instead of being silently dropped.
 */
export function KanbanSkillPicker({ value, onChange, placeholder }: KanbanSkillPickerProps) {
  const t = useTranslations('kanban');
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const marketSkills = useSkillStore((s) => s.marketSkills);
  const localSkills = useSkillStore((s) => s.localSkills);
  const fetchMarketSkills = useSkillStore((s) => s.fetchMarketSkills);
  const fetchLocalSkills = useSkillStore((s) => s.fetchLocalSkills);

  useEffect(() => {
    if (marketSkills.length === 0) void fetchMarketSkills();
    if (localSkills.length === 0) void fetchLocalSkills();
  }, [marketSkills.length, localSkills.length, fetchMarketSkills, fetchLocalSkills]);

  const selectedIds = useMemo(() => splitSkillIds(value), [value]);
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  const allSkills = useMemo(() => [...marketSkills, ...localSkills], [marketSkills, localSkills]);
  const skillById = useMemo(() => new Map(allSkills.map((s) => [s.id, s])), [allSkills]);

  const visibleSkills = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q
      ? allSkills.filter(
          (s) =>
            s.id.toLowerCase().includes(q) ||
            s.name.toLowerCase().includes(q) ||
            s.description.toLowerCase().includes(q),
        )
      : allSkills;
    return [...list].sort((a, b) => {
      const aSel = selectedSet.has(a.id) ? 1 : 0;
      const bSel = selectedSet.has(b.id) ? 1 : 0;
      return bSel - aSel || a.name.localeCompare(b.name);
    });
  }, [allSkills, query, selectedSet]);

  const commit = (ids: string[]) => onChange(Array.from(new Set(ids)).sort().join(', '));

  const toggleSkill = (skillId: string) => {
    const next = new Set(selectedIds);
    if (next.has(skillId)) {
      next.delete(skillId);
    } else {
      next.add(skillId);
    }
    commit(Array.from(next));
  };

  const removeSkill = toggleSkill;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <div className="space-y-1">
        {selectedIds.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {selectedIds.map((sid) => {
              const known = skillById.get(sid);
              return (
                <span
                  key={sid}
                  className="inline-flex max-w-full items-center gap-1 rounded-full border border-chart-3/20 bg-chart-3/10 px-1.5 py-0.5 text-chart-3"
                >
                  <span className="max-w-[160px] truncate">{known?.name ?? sid}</span>
                  {!known && <span className="shrink-0 text-[9px] opacity-70">{t('skillsUnknown')}</span>}
                  <button
                    type="button"
                    onClick={() => removeSkill(sid)}
                    className="shrink-0 hover:opacity-70"
                    aria-label={t('skillsRemove')}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              );
            })}
          </div>
        )}
            <PopoverTrigger asChild>
              <button
                type="button"
                data-testid="kanban-skill-picker-trigger"
                className={cn(
              'flex w-full items-center gap-1.5 rounded border bg-background px-2 py-1 text-left text-xs focus:outline-none focus:ring-1 focus:ring-chart-3',
              selectedIds.length === 0 && 'text-muted-foreground',
            )}
          >
            {selectedIds.length === 0 ? (
              <span className="truncate">{placeholder}</span>
            ) : (
              <span className="truncate">
                {selectedIds.length} {t('skillsCount')}
              </span>
            )}
            <ChevronsUpDown className="ml-auto h-3.5 w-3.5 shrink-0 opacity-50" />
          </button>
        </PopoverTrigger>
      </div>
      <PopoverContent className="w-80 max-w-[calc(100vw-2rem)] p-0" align="start">
        <Command>
          <CommandInput placeholder={t('skillsSearch')} value={query} onValueChange={setQuery} />
          <CommandEmpty>{t('skillsEmpty')}</CommandEmpty>
          <CommandGroup className="max-h-56 overflow-y-auto">
            {visibleSkills.map((skill) => {
              const selected = selectedSet.has(skill.id);
              return (
                <CommandItem
                  key={skill.id}
                  value={`${skill.name} ${skill.id} ${skill.description}`}
                  onSelect={() => toggleSkill(skill.id)}
                >
                  <span
                    className={cn(
                      'mr-2 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border',
                      selected ? 'border-chart-3 bg-chart-3 text-white' : 'border-border',
                    )}
                  >
                    {selected && <Check className="h-2.5 w-2.5" />}
                  </span>
                  <span className="truncate">{skill.name}</span>
                  <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">{skill.id}</span>
                </CommandItem>
              );
            })}
          </CommandGroup>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
