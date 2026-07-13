'use client';

/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: 聊天 Zustand store 的业务分层)
 *
 * [OUTPUT]
 * - GoalModeToggle: 目标模式开关与多维预算/保护配置弹层。
 *
 * [POS]
 * 聊天目标模式入口。负责在消息输入区启停长期目标并收集 4 维预算、文件保护、
 * 验收条件、约束条件及高级控制参数。
 */
import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import useChatStore from '@/store/useChatStore';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import { useShallow } from 'zustand/react/shallow';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { Input } from '@/components/primitives/input';
import { Button } from '@/components/primitives/button';

// Custom SVG Icons
const TargetIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <circle cx="12" cy="12" r="10" />
    <circle cx="12" cy="12" r="6" />
    <circle cx="12" cy="12" r="2" />
  </svg>
);

const XIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M18 6 6 18" />
    <path d="m6 6 12 12" />
  </svg>
);

const parseIntOrNull = (v: string): number | null => (v ? parseInt(v, 10) || null : null);
const parseFloatOrNull = (v: string): number | null => (v ? parseFloat(v) || null : null);

export default function GoalModeToggle() {
  const t = useTranslations('Goal');
  const initialized = useFeatureGateStore((s) => s.initialized);
  const isGoalsEnabled = useFeatureGateStore((s) => s.enabledFeatures.has('goals_system'));
  const [showAdvanced, setShowAdvanced] = useState(false);

  const {
    actionMode,
    isGoalMode,
    setIsGoalMode,
    goalBudgetTokens,
    setGoalBudgetTokens,
    goalBudgetUsd,
    setGoalBudgetUsd,
    goalMaxTimeSeconds,
    setGoalMaxTimeSeconds,
    goalMaxTurns,
    setGoalMaxTurns,
    goalProtectedPaths,
    setGoalProtectedPaths,
    goalLoopOnPause,
    setGoalLoopOnPause,
    goalConvergenceWindow,
    setGoalConvergenceWindow,
    goalAcceptanceCriteria,
    setGoalAcceptanceCriteria,
    goalConstraints,
    setGoalConstraints,
  } = useChatStore(
    useShallow((state) => ({
      actionMode: state.actionMode,
      isGoalMode: state.isGoalMode,
      setIsGoalMode: state.setIsGoalMode,
      goalBudgetTokens: state.goalBudgetTokens,
      setGoalBudgetTokens: state.setGoalBudgetTokens,
      goalBudgetUsd: state.goalBudgetUsd,
      setGoalBudgetUsd: state.setGoalBudgetUsd,
      goalMaxTimeSeconds: state.goalMaxTimeSeconds,
      setGoalMaxTimeSeconds: state.setGoalMaxTimeSeconds,
      goalMaxTurns: state.goalMaxTurns,
      setGoalMaxTurns: state.setGoalMaxTurns,
      goalProtectedPaths: state.goalProtectedPaths,
      setGoalProtectedPaths: state.setGoalProtectedPaths,
      goalLoopOnPause: state.goalLoopOnPause,
      setGoalLoopOnPause: state.setGoalLoopOnPause,
      goalConvergenceWindow: state.goalConvergenceWindow,
      setGoalConvergenceWindow: state.setGoalConvergenceWindow,
      goalAcceptanceCriteria: state.goalAcceptanceCriteria,
      setGoalAcceptanceCriteria: state.setGoalAcceptanceCriteria,
      goalConstraints: state.goalConstraints,
      setGoalConstraints: state.setGoalConstraints,
    })),
  );

  if (initialized && !isGoalsEnabled) return null;

  const criteriaList = goalAcceptanceCriteria || [];
  const constraintsList = goalConstraints || [];
  const protectedPathsList = goalProtectedPaths || [];

  const addShell = () =>
    setGoalAcceptanceCriteria([...criteriaList, { type: 'shell', command: '', timeout_seconds: 60 }]);
  const addSemantic = () => setGoalAcceptanceCriteria([...criteriaList, { type: 'semantic', criteria: '' }]);
  const updateCriteriaField = (idx: number, field: string, val: string | number) => {
    const next = [...criteriaList];
    next[idx] = { ...next[idx], [field]: val };
    setGoalAcceptanceCriteria(next);
  };
  const removeCriteria = (idx: number) => {
    const next = criteriaList.filter((_, i) => i !== idx);
    setGoalAcceptanceCriteria(next.length ? next : null);
  };

  const addConstraint = () => setGoalConstraints([...constraintsList, '']);
  const updateConstraint = (idx: number, val: string) => {
    const next = [...constraintsList];
    next[idx] = val;
    setGoalConstraints(next);
  };
  const removeConstraint = (idx: number) => {
    const next = constraintsList.filter((_, i) => i !== idx);
    setGoalConstraints(next.length ? next : null);
  };

  const addProtectedPath = () => setGoalProtectedPaths([...protectedPathsList, '']);
  const updateProtectedPath = (idx: number, val: string) => {
    const next = [...protectedPathsList];
    next[idx] = val;
    setGoalProtectedPaths(next);
  };
  const removeProtectedPath = (idx: number) => {
    const next = protectedPathsList.filter((_, i) => i !== idx);
    setGoalProtectedPaths(next.length ? next : null);
  };

  if (actionMode !== 'agent') {
    return null;
  }

  return (
    <Popover>
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <PopoverTrigger asChild>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label={t('enableGoalMode')}
                className={cn(
                  'flex items-center justify-center p-2 rounded-lg transition-all duration-200',
                  isGoalMode
                    ? 'bg-primary/10 text-primary hover:bg-primary/20'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                )}
              >
                <TargetIcon className={cn('w-[18px] h-[18px]', isGoalMode && 'animate-pulse')} />
              </button>
            </TooltipTrigger>
          </PopoverTrigger>
          <TooltipContent side="top">
            <p>{t('enableGoalMode')}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <PopoverContent className="w-72 p-3 max-h-[70vh] overflow-y-auto" align="start" sideOffset={8}>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="font-medium leading-none">{t('enableGoalMode')}</h4>
            <button
              type="button"
              aria-label={t('enableGoalMode')}
              className={cn(
                'relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center justify-center rounded-full transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
                isGoalMode ? 'bg-accent-warm' : 'bg-muted',
              )}
              onClick={() => setIsGoalMode(!isGoalMode)}
            >
              <span
                className={cn(
                  'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out',
                  isGoalMode ? 'translate-x-4' : 'translate-x-0',
                )}
              />
            </button>
          </div>

          {isGoalMode && (
            <div className="space-y-4 pt-2 border-t">
              {/* Budget Limits */}
              <div className="space-y-2">
                <label className="text-xs font-medium text-muted-foreground">{t('budgetSection')}</label>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-[10px] text-muted-foreground">{t('goalBudgetPlaceholder')}</label>
                    <Input
                      type="number"
                      min={1}
                      placeholder="e.g. 50000"
                      value={goalBudgetTokens ?? ''}
                      onChange={(e) => setGoalBudgetTokens(parseIntOrNull(e.target.value))}
                      className="h-7 text-xs"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-muted-foreground">{t('maxUsdLabel')}</label>
                    <Input
                      type="number"
                      min={0.01}
                      step="0.1"
                      placeholder={t('maxUsdPlaceholder')}
                      value={goalBudgetUsd ?? ''}
                      onChange={(e) => setGoalBudgetUsd(parseFloatOrNull(e.target.value))}
                      className="h-7 text-xs"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-muted-foreground">{t('maxTimeLabel')}</label>
                    <Input
                      type="number"
                      min={1}
                      placeholder={t('maxTimePlaceholder')}
                      value={goalMaxTimeSeconds != null ? Math.round(goalMaxTimeSeconds / 60) : ''}
                      onChange={(e) => {
                        const minutes = parseIntOrNull(e.target.value);
                        setGoalMaxTimeSeconds(minutes != null ? minutes * 60 : null);
                      }}
                      className="h-7 text-xs"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-muted-foreground">{t('maxTurnsLabel')}</label>
                    <Input
                      type="number"
                      min={1}
                      placeholder={t('maxTurnsPlaceholder')}
                      value={goalMaxTurns ?? ''}
                      onChange={(e) => setGoalMaxTurns(parseIntOrNull(e.target.value))}
                      className="h-7 text-xs"
                    />
                  </div>
                </div>
              </div>

              {/* Protected Paths */}
              <div className="space-y-2">
                <div className="text-xs text-muted-foreground flex justify-between items-center">
                  <span>{t('protectedPathsLabel')}</span>
                  <Button size="sm" variant="ghost" className="h-6 px-2 text-[10px]" onClick={addProtectedPath}>
                    {t('addProtectedPath')}
                  </Button>
                </div>
                {protectedPathsList.length === 0 && (
                  <div className="text-[10px] text-muted-foreground/60 text-center py-2 border border-dashed rounded">
                    {t('noProtectedPathsHint')}
                  </div>
                )}
                <div className="space-y-2 max-h-24 overflow-y-auto">
                  {protectedPathsList.map((p, i) => (
                    <div key={i} className="flex items-center gap-1 relative group">
                      <Input
                        value={p}
                        onChange={(e) => updateProtectedPath(i, e.target.value)}
                        placeholder={t('protectedPathPlaceholder')}
                        className="h-6 text-xs px-2 flex-1"
                      />
                      <button
                        onClick={() => removeProtectedPath(i)}
                        className="text-muted-foreground hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <XIcon className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Acceptance Criteria */}
              <div className="space-y-2">
                <div className="text-xs text-muted-foreground flex justify-between items-center">
                  <span>{t('acceptanceCriteria')}</span>
                  <div className="flex gap-1">
                    <Button size="sm" variant="ghost" className="h-6 px-2 text-[10px]" onClick={addShell}>
                      {t('addShellCriteria')}
                    </Button>
                    <Button size="sm" variant="ghost" className="h-6 px-2 text-[10px]" onClick={addSemantic}>
                      {t('addSemanticCriteria')}
                    </Button>
                  </div>
                </div>
                {criteriaList.length === 0 && (
                  <div className="text-[10px] text-muted-foreground/60 text-center py-2 border border-dashed rounded">
                    {t('noCriteriaHint')}
                  </div>
                )}
                <div className="space-y-2 max-h-40 overflow-y-auto">
                  {criteriaList.map((c, i) => (
                    <div key={i} className="flex flex-col gap-1 p-2 border rounded-lg bg-muted/10 relative group">
                      <button
                        onClick={() => removeCriteria(i)}
                        className="absolute right-1 top-1 text-muted-foreground hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <XIcon className="w-3 h-3" />
                      </button>
                      <span className="text-[10px] font-semibold uppercase text-primary">
                        {c.type === 'shell' ? t('shellCriteriaLabel') : t('semanticCriteriaLabel')}
                      </span>
                      <Input
                        value={(c.command as string) || (c.criteria as string) || (c.expected as string) || ''}
                        onChange={(e) =>
                          updateCriteriaField(i, c.type === 'shell' ? 'command' : 'criteria', e.target.value)
                        }
                        placeholder={c.type === 'shell' ? t('shellPlaceholder') : t('semanticPlaceholder')}
                        className="h-6 text-xs px-2"
                      />
                      {c.type === 'shell' && (
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                            {t('timeoutLabel')}
                          </span>
                          <Input
                            type="number"
                            min={1}
                            value={(c.timeout_seconds as number) || 60}
                            onChange={(e) =>
                              updateCriteriaField(i, 'timeout_seconds', parseInt(e.target.value, 10) || 60)
                            }
                            className="h-6 text-xs px-2 w-16"
                          />
                        </div>
                      )}
                      {c.type === 'semantic' && (
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                            {t('targetFileLabel')}
                          </span>
                          <Input
                            value={(c.target_file as string) || ''}
                            onChange={(e) => updateCriteriaField(i, 'target_file', e.target.value)}
                            placeholder={t('targetFilePlaceholder')}
                            className="h-6 text-xs px-2 flex-1"
                          />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Constraints */}
              <div className="space-y-2">
                <div className="text-xs text-muted-foreground flex justify-between items-center">
                  <span>{t('constraints')}</span>
                  <Button size="sm" variant="ghost" className="h-6 px-2 text-[10px]" onClick={addConstraint}>
                    {t('addConstraint')}
                  </Button>
                </div>
                {constraintsList.length === 0 && (
                  <div className="text-[10px] text-muted-foreground/60 text-center py-2 border border-dashed rounded">
                    {t('noConstraintsHint')}
                  </div>
                )}
                <div className="space-y-2 max-h-32 overflow-y-auto">
                  {constraintsList.map((c, i) => (
                    <div key={i} className="flex items-center gap-1 relative group">
                      <Input
                        value={c}
                        onChange={(e) => updateConstraint(i, e.target.value)}
                        placeholder={t('constraintPlaceholder')}
                        className="h-6 text-xs px-2 flex-1"
                      />
                      <button
                        onClick={() => removeConstraint(i)}
                        className="text-muted-foreground hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <XIcon className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Advanced Settings (collapsed) */}
              <div className="border-t pt-2">
                <button
                  type="button"
                  onClick={() => setShowAdvanced(!showAdvanced)}
                  className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
                >
                  <span className={cn('transition-transform', showAdvanced && 'rotate-90')}>▸</span>
                  {t('advancedSettings')}
                </button>
                {showAdvanced && (
                  <div className="space-y-3 mt-2">
                    <div className="flex items-center justify-between">
                      <label className="text-[10px] text-muted-foreground">{t('loopOnPauseLabel')}</label>
                      <button
                        type="button"
                        className={cn(
                          'relative inline-flex h-4 w-7 shrink-0 cursor-pointer items-center rounded-full transition-colors',
                          goalLoopOnPause ? 'bg-accent-warm' : 'bg-muted',
                        )}
                        onClick={() => setGoalLoopOnPause(!goalLoopOnPause)}
                      >
                        <span
                          className={cn(
                            'pointer-events-none inline-block h-3 w-3 transform rounded-full bg-white shadow transition',
                            goalLoopOnPause ? 'translate-x-3.5' : 'translate-x-0.5',
                          )}
                        />
                      </button>
                    </div>
                    <div>
                      <label className="text-[10px] text-muted-foreground">{t('convergenceWindowLabel')}</label>
                      <Input
                        type="number"
                        min={2}
                        placeholder={t('convergenceWindowPlaceholder')}
                        value={goalConvergenceWindow ?? ''}
                        onChange={(e) => setGoalConvergenceWindow(parseIntOrNull(e.target.value))}
                        className="h-7 text-xs mt-1"
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
