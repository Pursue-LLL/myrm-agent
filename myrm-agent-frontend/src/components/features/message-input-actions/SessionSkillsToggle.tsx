'use client';

import { useState, useMemo, useCallback } from 'react';
import { Sparkles } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import { cn } from '@/lib/utils/classnameUtils';
import useChatStore from '@/store/useChatStore';
import useSkillStore from '@/store/skill/useSkillStore';
import { useShallow } from 'zustand/react/shallow';
import { updateSessionSkills } from '@/services/chat';
import { toast } from '@/lib/utils/toast';

export default function SessionSkillsToggle() {
  const t = useTranslations('chat.sessionSkills');
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const { chatId, sessionSkillOverrides, setSessionSkillOverrides, actionMode } = useChatStore(
    useShallow((s) => ({
      chatId: s.chatId,
      sessionSkillOverrides: s.sessionSkillOverrides,
      setSessionSkillOverrides: s.setSessionSkillOverrides,
      actionMode: s.actionMode,
    })),
  );

  const { marketSkills, localSkills, isSkillEnabled } = useSkillStore(
    useShallow((s) => ({
      marketSkills: s.marketSkills,
      localSkills: s.localSkills,
      isSkillEnabled: s.isSkillEnabled,
    })),
  );

  const enabledSkills = useMemo(() => {
    const all = [...marketSkills, ...localSkills].filter((s) => s.user_invocable !== false);
    return all.filter((skill) => isSkillEnabled(skill.id));
  }, [marketSkills, localSkills, isSkillEnabled]);

  const hasOverride = sessionSkillOverrides !== null && sessionSkillOverrides !== undefined;
  const overrideCount = sessionSkillOverrides?.length ?? 0;

  const isSkillActive = useCallback(
    (skillName: string) => {
      if (!hasOverride) return true;
      return sessionSkillOverrides!.includes(skillName);
    },
    [hasOverride, sessionSkillOverrides],
  );

  const persistOverrides = useCallback(
    async (names: string[] | null) => {
      if (!chatId) return;
      setSaving(true);
      try {
        await updateSessionSkills(chatId, names);
        setSessionSkillOverrides(names);
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Failed to update session skills';
        toast.error(msg);
      } finally {
        setSaving(false);
      }
    },
    [chatId, setSessionSkillOverrides],
  );

  const toggleSkill = useCallback(
    (skillName: string) => {
      const currentActive = hasOverride
        ? sessionSkillOverrides!
        : enabledSkills.map((s) => s.name);

      const isActive = currentActive.includes(skillName);
      const next = isActive
        ? currentActive.filter((n) => n !== skillName)
        : [...currentActive, skillName];

      const allNames = enabledSkills.map((s) => s.name);
      const isAllSelected = next.length >= allNames.length && allNames.every((n) => next.includes(n));
      const normalized = isAllSelected || next.length === 0 ? null : next;
      persistOverrides(normalized);
    },
    [hasOverride, sessionSkillOverrides, enabledSkills, persistOverrides],
  );

  const clearOverride = useCallback(() => {
    persistOverrides(null);
  }, [persistOverrides]);

  if (actionMode !== 'agent' || enabledSkills.length === 0) {
    return null;
  }

  return (
    <TooltipProvider delayDuration={300}>
      <Popover open={open} onOpenChange={setOpen}>
        <Tooltip>
          <TooltipTrigger asChild>
            <PopoverTrigger asChild>
              <button
                type="button"
                className={cn(
                  'flex items-center gap-1 px-2 py-1 rounded-md text-xs transition-colors',
                  hasOverride
                    ? 'bg-primary/10 text-primary hover:bg-primary/20'
                    : 'text-muted-foreground/70 hover:text-muted-foreground hover:bg-muted/50',
                )}
              >
                <Sparkles size={14} />
                {hasOverride && <span className="font-medium">{overrideCount}</span>}
              </button>
            </PopoverTrigger>
          </TooltipTrigger>
          <TooltipContent side="top">
            <p>{hasOverride ? t('activeCount', { count: overrideCount }) : t('tooltip')}</p>
          </TooltipContent>
        </Tooltip>

        <PopoverContent
          className="w-64 max-w-[calc(100vw-2rem)] p-0"
          side="top"
          align="start"
          sideOffset={8}
        >
          <div className="px-3 py-2.5 border-b border-border/50 flex items-center justify-between">
            <span className="text-sm font-medium">{t('popoverTitle')}</span>
            {hasOverride && (
              <button
                type="button"
                onClick={clearOverride}
                disabled={saving}
                className="text-xs text-primary hover:underline disabled:opacity-50"
              >
                {t('clearOverride')}
              </button>
            )}
          </div>

          <div className="max-h-[240px] overflow-y-auto py-1">
            {enabledSkills.map((skill) => {
              const active = isSkillActive(skill.name);
              return (
                <button
                  key={skill.id}
                  type="button"
                  disabled={saving}
                  onClick={() => toggleSkill(skill.name)}
                  className={cn(
                    'w-full flex items-center gap-2 px-3 py-1.5 text-left text-sm transition-colors',
                    'hover:bg-muted/50 disabled:opacity-50',
                    !active && 'opacity-50',
                  )}
                >
                  <div
                    className={cn(
                      'w-3.5 h-3.5 rounded-sm border flex-shrink-0 flex items-center justify-center transition-colors',
                      active ? 'bg-primary border-primary' : 'border-border',
                    )}
                  >
                    {active && (
                      <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                        <path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    )}
                  </div>
                  <span className="truncate">{skill.name}</span>
                </button>
              );
            })}
          </div>

          {!hasOverride && (
            <div className="px-3 py-2 border-t border-border/50">
              <span className="text-xs text-muted-foreground">{t('usingAll')}</span>
            </div>
          )}
        </PopoverContent>
      </Popover>
    </TooltipProvider>
  );
}
