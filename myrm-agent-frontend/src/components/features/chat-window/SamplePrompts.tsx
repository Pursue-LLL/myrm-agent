'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  BarChart3,
  BookMarked,
  Brain,
  CalendarDays,
  CheckCircle2,
  Clock,
  Compass,
  Cpu,
  FileSpreadsheet,
  FileText,
  GraduationCap,
  HeartPulse,
  Lightbulb,
  ListTodo,
  MapPin,
  Moon,
  Newspaper,
  PenLine,
  PenTool,
  Plane,
  Radar,
  Salad,
  Search,
  ShieldAlert,
  Sparkles,
  Sun,
  Sunrise,
  Sunset,
  Target,
  Timer,
  TrendingUp,
  Users,
  Workflow,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import useChatStore from '@/store/useChatStore';
import { useProgressionStore } from '@/store/useProgressionStore';
import type { ActionMode } from '@/store/chat/types';
import { cn } from '@/lib/utils/classnameUtils';

type TimeSlot = 'morning' | 'afternoon' | 'evening' | 'night';
type ActiveFilter = 'auto' | TimeSlot | 'all';

const POOL_SIZE = 12;
const TIME_POOL_SIZE = 4;
const DISPLAY_COUNT = 4;

const PROMPT_ICONS: Record<string, LucideIcon> = {
  fast_0: Search,
  fast_1: Salad,
  fast_2: Lightbulb,
  fast_3: Newspaper,
  fast_4: Compass,
  fast_5: GraduationCap,
  fast_6: HeartPulse,
  fast_7: BookMarked,
  fast_8: MapPin,
  fast_9: Timer,
  fast_10: Cpu,
  fast_11: FileText,
  agent_0: Workflow,
  agent_1: PenTool,
  agent_2: PenLine,
  agent_3: CalendarDays,
  agent_4: Zap,
  agent_5: BarChart3,
  agent_6: Target,
  agent_7: Plane,
  agent_8: FileSpreadsheet,
  agent_9: Radar,
  agent_10: TrendingUp,
  agent_11: Users,
  time_morning_0: Target,
  time_morning_1: ListTodo,
  time_morning_2: Newspaper,
  time_morning_3: Users,
  time_afternoon_0: ShieldAlert,
  time_afternoon_1: TrendingUp,
  time_afternoon_2: BarChart3,
  time_afternoon_3: Cpu,
  time_evening_0: CheckCircle2,
  time_evening_1: Brain,
  time_evening_2: CalendarDays,
  time_evening_3: BookMarked,
  time_night_0: Workflow,
  time_night_1: Timer,
  time_night_2: FileText,
  time_night_3: PenTool,
};

const PROMPT_LEVEL_AFFINITY: Record<string, number> = {
  agent_0: 2,
  agent_3: 3,
  agent_5: 2,
  agent_6: 4,
  agent_9: 2,
  agent_10: 3,
  agent_11: 4,
};

const SUPPORTED_MODES: ActionMode[] = ['fast', 'agent'];

function getCurrentTimeSlot(): TimeSlot {
  const hour = new Date().getHours();
  if (hour >= 6 && hour < 12) return 'morning';
  if (hour >= 12 && hour < 18) return 'afternoon';
  if (hour >= 18 && hour < 24) return 'evening';
  return 'night';
}

function hashSeed(seed: string): number {
  let hash = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    hash ^= seed.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function stablePick<T>(items: T[], count: number, seed: string): T[] {
  const shuffled = [...items];
  let state = hashSeed(seed);
  for (let i = shuffled.length - 1; i > 0; i--) {
    state = (Math.imul(state, 1103515245) + 12345) >>> 0;
    const j = state % (i + 1);
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled.slice(0, count);
}

const SamplePrompts = React.memo(() => {
  const t = useTranslations('chat');
  const actionMode = useChatStore((state) => state.actionMode);
  const setInputMessage = useChatStore((state) => state.setInputMessage);
  const agentConfig = useChatStore((state) => state.agentConfig);
  const currentLevel = useProgressionStore((state) => state.currentLevel);

  const [currentTimeSlot, setCurrentTimeSlot] = useState<TimeSlot>('morning');
  const [selectedSlot, setSelectedSlot] = useState<ActiveFilter>('auto');

  useEffect(() => {
    setCurrentTimeSlot(getCurrentTimeSlot());
    const timer = setInterval(() => {
      setCurrentTimeSlot(getCurrentTimeSlot());
    }, 60000);
    return () => clearInterval(timer);
  }, []);

  const effectiveSlot: TimeSlot | 'all' = selectedSlot === 'auto' ? currentTimeSlot : selectedSlot;
  const mode = SUPPORTED_MODES.includes(actionMode) ? actionMode : 'agent';

  const prompts = useMemo(() => {
    const pickSeed = `${mode}:${agentConfig?.agentId ?? agentConfig?.presetId ?? 'default'}:${effectiveSlot}:L${currentLevel}`;

    if (agentConfig?.suggestionPrompts && agentConfig.suggestionPrompts.length > 0) {
      const agentPrompts = agentConfig.suggestionPrompts.map((text, i) => ({
        key: `agent_custom_${i}`,
        text,
        Icon: PROMPT_ICONS[`agent_${i % POOL_SIZE}`] ?? Brain,
      }));
      return stablePick(agentPrompts, DISPLAY_COUNT, `${pickSeed}:custom`);
    }

    if (effectiveSlot !== 'all') {
      const timePool = Array.from({ length: TIME_POOL_SIZE }, (_, i) => {
        const key = `time_${effectiveSlot}_${i}`;
        return {
          key,
          text: t(`samplePrompts.${key}`),
          Icon: PROMPT_ICONS[key] ?? Sparkles,
        };
      });
      return timePool;
    }

    const pool = Array.from({ length: POOL_SIZE }, (_, i) => {
      const key = `${mode}_${i}`;
      return {
        key,
        text: t(`samplePrompts.${key}`),
        Icon: PROMPT_ICONS[key] ?? Search,
      };
    });

    if (currentLevel >= 3 && mode === 'agent') {
      pool.sort((a, b) => {
        const aAffinity = PROMPT_LEVEL_AFFINITY[a.key] ?? 1;
        const bAffinity = PROMPT_LEVEL_AFFINITY[b.key] ?? 1;
        const aMatch = aAffinity <= currentLevel ? 1 : 0;
        const bMatch = bAffinity <= currentLevel ? 1 : 0;
        return bMatch - aMatch;
      });
    }

    return stablePick(pool, DISPLAY_COUNT, pickSeed);
  }, [mode, t, agentConfig?.agentId, agentConfig?.presetId, agentConfig?.suggestionPrompts, currentLevel, effectiveSlot]);

  const handleSelectSlot = useCallback((slot: ActiveFilter) => {
    setSelectedSlot(slot);
  }, []);

  const slotTabs: Array<{ id: ActiveFilter; label: string; Icon: LucideIcon }> = [
    { id: 'morning', label: t('lifeOperator.morning'), Icon: Sunrise },
    { id: 'afternoon', label: t('lifeOperator.afternoon'), Icon: Sun },
    { id: 'evening', label: t('lifeOperator.evening'), Icon: Sunset },
    { id: 'night', label: t('lifeOperator.night'), Icon: Moon },
    { id: 'all', label: t('lifeOperator.all'), Icon: Compass },
  ];

  return (
    <div className="w-full space-y-3 animate-in fade-in duration-500">
      {/* Context-Aware Life/Work Operator Selector Bar */}
      {(!agentConfig?.suggestionPrompts || agentConfig.suggestionPrompts.length === 0) && (
        <div className="flex items-center justify-center gap-1.5 flex-wrap">
          {slotTabs.map(({ id, label, Icon }) => {
            const isActive = (selectedSlot === 'auto' && id === currentTimeSlot) || selectedSlot === id;
            return (
              <button
                key={id}
                onClick={() => handleSelectSlot(id === currentTimeSlot && selectedSlot !== 'auto' ? 'auto' : id)}
                className={cn(
                  'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all duration-200 cursor-pointer select-none',
                  isActive
                    ? 'bg-primary/15 text-primary border border-primary/30 shadow-xs'
                    : 'text-muted-foreground hover:text-foreground hover:bg-secondary/60 border border-transparent',
                )}
              >
                <Icon className={cn('w-3.5 h-3.5', isActive ? 'text-primary' : 'text-muted-foreground')} />
                <span>{label}</span>
                {id === currentTimeSlot && (
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Prompts Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 w-full">
        {prompts.map(({ key, text, Icon }) => (
          <button
            key={key}
            onClick={() => setInputMessage(text)}
            className="group flex items-start gap-3 p-3.5 rounded-xl border border-border/60 bg-secondary/40
                       hover:bg-secondary hover:border-border hover:shadow-sm
                       transition-all duration-200 text-left cursor-pointer"
          >
            <Icon className="w-4 h-4 mt-0.5 shrink-0 text-muted-foreground group-hover:text-primary transition-colors" />
            <span className="text-sm text-muted-foreground group-hover:text-foreground transition-colors line-clamp-2">
              {text}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
});

SamplePrompts.displayName = 'SamplePrompts';

export default SamplePrompts;
