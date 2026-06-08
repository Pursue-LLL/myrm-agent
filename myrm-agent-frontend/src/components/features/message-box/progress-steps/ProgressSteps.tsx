/**
 * [INPUT]
 * - ./ArchiveRestoreStepAction::ArchiveRestoreStepAction (POS: Progress-step archive restore action view. Bridges a typed restore action array into direct send, busy-state input preparation, and retry-safe pending action restoration.)
 * - ./renderers::* (POS: Progress step polymorphic renderers)
 * - ./toolIcons::* (POS: Progress step icon and agent theme mapping)
 *
 * [OUTPUT]
 * - ProgressSteps: renders streamed Agent progress steps as collapsed status or expanded tree.
 *
 * [POS]
 * Chat progress-step renderer. Owns layout, tree traversal, step chrome, error actions and
 * polymorphic item rendering for streamed Agent execution state.
 */

import React, { useState, useRef, useEffect } from 'react';
import { ChevronUp, ChevronDown, ClipboardList } from 'lucide-react';
import type { ProgressItem, RecoveryAction } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { isUrl } from '@/lib/utils/urlUtils';
import { Badge } from '@/components/primitives/badge';

import { useScrollbarStyles } from './useScrollbarStyles';
import {
  getStepTitle,
  isTextItems,
  isQueryItems,
  isUrlItems,
  isTextString,
  isSourceItems,
  isSkillSelectItems,
  isFilePathItems,
  isCodeItems,
  inferStageLabel,
  linkifyErrorText,
} from './utils';
import {
  TextItemsRenderer,
  QueryItemsRenderer,
  TextRenderer,
  URLItemsRenderer,
  SourcesRenderer,
  SkillSelectRenderer,
  FilePathRenderer,
  CodeRenderer,
  LiveTerminal,
} from './renderers';
import {
  StepIcon,
  isSystemStep,
  formatAgentHandle,
  getAgentColor,
  AGENT_COLOR_CLASSES,
  type AgentThemeColor,
} from './toolIcons';
import { buildTree, TreeNode } from './treeUtils';
import { ArchiveRestoreStepAction } from './ArchiveRestoreStepAction';
import { ArchiveRestoreResultChip } from './ArchiveRestoreResultChip';

interface ProgressStepsProps {
  messageId: string;
  steps: ProgressItem[];
  loading: boolean;
}

const ProgressSteps: React.FC<ProgressStepsProps> = React.memo(({ messageId, steps, loading }) => {
  const t = useTranslations('progressSteps');
  const [isExpanded, setIsExpanded] = useState(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  useScrollbarStyles();

  useEffect(() => {
    if (scrollContainerRef.current && isExpanded && loading) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    }
  }, [steps.length, isExpanded, loading]);

  const handleLinkClick = (text: string) => {
    if (!isUrl(text)) return;
    let url = text;
    if (text.startsWith('www.')) {
      url = `https://${text}`;
    }
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const handleActionClick = (action: RecoveryAction) => {
    if (action.url?.startsWith('command://')) {
      const command = action.url.replace('command://', '');
      useChatStore.getState().sendMessage(command);
    } else if (action.url?.startsWith('/')) {
      window.location.href = action.url;
    } else if (action.url) {
      window.open(action.url, '_blank', 'noopener,noreferrer');
    }
  };

  const handleExpand = () => {
    if (!isExpanded) {
      setIsExpanded(true);
    }
  };

  const toggleExpanded = () => setIsExpanded(!isExpanded);

  if (steps.length === 0) return null;

  const latestStep = steps[steps.length - 1];
  const collapsedStep = (() => {
    for (let index = steps.length - 1; index >= 0; index -= 1) {
      if (steps[index].step_key === 'analyzing_image') {
        return steps[index];
      }
    }
    return latestStep;
  })();
  const isCollapsedStepCurrent = loading;
  const isCollapsedCompleted = !collapsedStep.error && !isCollapsedStepCurrent;
  const isCollapsedWarning = collapsedStep.status === 'warning';
  const isCollapsedError = collapsedStep.error && !isCollapsedWarning;

  const renderTreeNode = (node: TreeNode, depth: number = 0) => {
    const { step, originalIndex: index, children } = node;
    const isCurrentStep = index === steps.length - 1 && loading;
    const isCompletedStep = !step.error && !isCurrentStep;
    const isWarningStep = step.status === 'warning';
    const isErrorStep = step.error && !isWarningStep;
    const systemStep = isSystemStep(step.tool_name);

    // Determine if this is a plan node
    const isPlanNode = step.is_plan;

    return (
      <div
        key={`${messageId}-step-${index}`}
        className={cn('relative group flex items-start gap-3', depth === 0 ? '-ml-1 pl-1' : 'ml-4 mt-2')}
      >
        <div className="flex-shrink-0 relative z-10 p-1 -m-1">
          <div
            className={cn(
              'relative w-[16px] sm:w-[20px] h-[16px] sm:h-[20px] rounded-full bg-background border-2 sm:border-3 transition-all duration-300',
              isWarningStep
                ? 'border-amber-500 shadow-lg shadow-amber-500/20'
                : isErrorStep
                  ? 'border-destructive shadow-lg shadow-destructive/20'
                  : isCurrentStep
                    ? 'border-primary shadow-lg shadow-primary/20 animate-rotate-step'
                    : isCompletedStep
                      ? 'border-primary/70 shadow-lg shadow-primary/15'
                      : 'border-muted-foreground/40 shadow-lg shadow-muted/10',
            )}
          >
            <div
              className={cn(
                'absolute inset-[3px] sm:inset-[4px] rounded-full transition-all duration-300',
                isWarningStep
                  ? 'bg-amber-500'
                  : isErrorStep
                    ? 'bg-destructive'
                    : isCurrentStep
                      ? 'bg-primary animate-rotate-step'
                      : isCompletedStep
                        ? 'bg-primary/70'
                        : 'bg-muted-foreground/40',
              )}
            />
          </div>
        </div>

        <div className="flex flex-col space-y-2 sm:space-y-3 flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <StepIcon
              step_key={step.step_key}
              tool_name={step.tool_name}
              size={16}
              className={cn(
                'flex-shrink-0 transition-colors duration-200',
                isWarningStep
                  ? 'text-amber-600 dark:text-amber-500'
                  : isErrorStep
                    ? 'text-destructive'
                    : systemStep
                      ? 'text-primary/70'
                      : 'text-foreground/70',
              )}
            />
            <h4
              className={cn(
                'text-sm font-normal transition-colors duration-200',
                isWarningStep
                  ? 'text-amber-600 dark:text-amber-400'
                  : isErrorStep
                    ? 'text-destructive'
                    : 'text-foreground group-hover:text-foreground/90',
                isPlanNode && 'font-semibold',
              )}
            >
              {step.agent_instance && (
                <Badge
                  variant="outline"
                  className={cn(
                    'mr-1.5 h-5 px-2 text-[10px] font-bold border hidden sm:inline-flex',
                    step.theme_color
                      ? AGENT_COLOR_CLASSES[step.theme_color as AgentThemeColor]?.badge ||
                          AGENT_COLOR_CLASSES[getAgentColor(step.agent_instance)].badge
                      : AGENT_COLOR_CLASSES[getAgentColor(step.agent_instance)].badge,
                  )}
                >
                  {formatAgentHandle(step.agent_instance, step.display_name)}
                </Badge>
              )}
              {getStepTitle(step, t)}
              {step.step_key === 'safety_fallback_active' && (
                <Badge
                  variant="outline"
                  className="ml-2 bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400 text-[10px] uppercase tracking-wider font-bold"
                >
                  Smart Fallback
                </Badge>
              )}
            </h4>
            {step.error_category && (
              <Badge
                variant="destructive"
                className="ml-1 h-4 px-1.5 text-[9px] uppercase tracking-wider font-bold shrink-0"
              >
                {t(`errorCategories.${step.error_category}`)}
              </Badge>
            )}
            {step.duration_ms != null && step.duration_ms > 0 && (
              <span className="ml-2 text-xs tabular-nums text-muted-foreground/60 flex-shrink-0">
                {step.duration_ms < 1000 ? `${step.duration_ms}ms` : `${(step.duration_ms / 1000).toFixed(1)}s`}
              </span>
            )}
            {step.progress_percent != null && (
              <span
                className={`ml-auto text-xs tabular-nums flex-shrink-0 ${
                  step.notify_level === 'alert'
                    ? 'text-destructive'
                    : step.notify_level === 'warn'
                      ? 'text-amber-600 dark:text-amber-400'
                      : 'text-muted-foreground/60'
                }`}
              >
                {step.progress_percent}%
              </span>
            )}
          </div>
          {step.progress_percent != null && (
            <div
              className={`h-1 w-full rounded-full overflow-hidden ${
                step.notify_level === 'alert'
                  ? 'bg-destructive/15'
                  : step.notify_level === 'warn'
                    ? 'bg-amber-500/15 dark:bg-amber-400/15'
                    : 'bg-muted/50'
              }`}
            >
              <div
                className={`h-full rounded-full transition-all duration-500 ease-out ${
                  step.notify_level === 'alert'
                    ? 'bg-destructive'
                    : step.notify_level === 'warn'
                      ? 'bg-amber-500 dark:bg-amber-400'
                      : 'bg-primary/70'
                }`}
                style={{ width: `${Math.min(step.progress_percent, 100)}%` }}
              />
            </div>
          )}

          {(!isPlanNode || children.length === 0) && (
            <>
              {step.reason && (
                <p className="text-xs text-muted-foreground italic leading-relaxed whitespace-pre-wrap">
                  {step.reason}
                </p>
              )}

              {step.error && typeof step.error === 'string' && (
                <div
                  className={cn(
                    'mt-2 p-2.5 rounded-lg border',
                    isWarningStep
                      ? 'bg-amber-50 dark:bg-amber-950/20 border-amber-300 dark:border-amber-800/40'
                      : 'bg-destructive/5 dark:bg-destructive/10 border-destructive/20',
                  )}
                >
                  <div
                    className={cn(
                      'text-xs break-all leading-relaxed whitespace-pre-wrap',
                      isWarningStep ? 'text-amber-700 dark:text-amber-400' : 'text-destructive',
                    )}
                  >
                    {linkifyErrorText(step.error)}
                  </div>
                  {step.error_hint && (
                    <div className="mt-2 text-[11px] opacity-80 border-t border-destructive/10 pt-2 flex items-start gap-1.5 leading-relaxed">
                      <span className="font-bold shrink-0 text-destructive">{t('diagnosticHint')}:</span>
                      <span className="italic text-foreground/80">{step.error_hint}</span>
                    </div>
                  )}

                  {step.recovery_actions && step.recovery_actions.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {step.recovery_actions.map((action, idx) => {
                        const isPrimary =
                          action.id === 'top_up' ||
                          action.id === 'retry' ||
                          action.id.includes('install') ||
                          action.id.includes('mock');

                        return (
                          <button
                            key={idx}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleActionClick(action);
                            }}
                            className={cn(
                              'inline-flex items-center justify-center rounded-full text-[11px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 h-6 px-2.5',
                              isPrimary
                                ? 'bg-primary text-primary-foreground shadow hover:bg-primary/90'
                                : 'border border-input bg-background hover:bg-accent hover:text-accent-foreground',
                            )}
                          >
                            {action.label}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {step.items && !isPlanNode && (
                <div>
                  {isSkillSelectItems(step.items) && (
                    <SkillSelectRenderer items={step.items} messageId={messageId} stepIndex={index} />
                  )}
                  {isFilePathItems(step.items) && (
                    <FilePathRenderer items={step.items} messageId={messageId} stepIndex={index} />
                  )}
                  {isCodeItems(step.items) && (
                    <CodeRenderer items={step.items} messageId={messageId} stepIndex={index} />
                  )}
                  {isTextItems(step.items) && (
                    <TextItemsRenderer
                      items={step.items}
                      messageId={messageId}
                      stepIndex={index}
                      handleLinkClick={handleLinkClick}
                    />
                  )}
                  {isQueryItems(step.items) && (
                    <QueryItemsRenderer items={step.items} messageId={messageId} stepIndex={index} />
                  )}
                  {isTextString(step.items) && <TextRenderer text={step.items} />}
                  {isSourceItems(step.items) ? (
                    <SourcesRenderer
                      items={step.items}
                      messageId={messageId}
                      stepIndex={index}
                      isCurrentStep={isCurrentStep}
                    />
                  ) : (
                    isUrlItems(step.items) && (
                      <URLItemsRenderer
                        items={step.items}
                        messageId={messageId}
                        stepIndex={index}
                        isCurrentStep={isCurrentStep}
                        handleLinkClick={handleLinkClick}
                      />
                    )
                  )}
                </div>
              )}

              {step.archive_restore_actions && step.archive_restore_actions.length > 0 && (
                <ArchiveRestoreStepAction actions={step.archive_restore_actions} block={step.archive_restore_block} />
              )}

              {step.archive_restore_result && <ArchiveRestoreResultChip result={step.archive_restore_result} />}

              <LiveTerminal stdout={step.stdout} evictedFileRef={step.evicted_file_ref} />
            </>
          )}

          {children.length > 0 && (
            <div className="relative space-y-4 sm:space-y-6 mt-2">
              <div
                className="absolute left-[7px] sm:left-[9px] w-[2px] sm:w-[2px] bg-gradient-to-b from-primary/15 via-primary/25 to-primary/10 dark:from-primary/20 dark:via-primary/30 dark:to-primary/15 rounded-full"
                style={{
                  top: '0.5rem',
                  bottom: '0.5rem',
                }}
              />
              {children.map((child) => renderTreeNode(child, depth + 1))}
            </div>
          )}
        </div>
      </div>
    );
  };

  const treeRoots = buildTree(steps);

  return (
    <>
      <div
        className="flex items-center justify-between mt-6 cursor-pointer group hover:opacity-90 transition-opacity duration-200"
        onClick={toggleExpanded}
      >
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <div className="absolute inset-0 bg-gradient-to-r from-blue-500/20 to-purple-500/20 dark:from-blue-400/20 dark:to-purple-400/20 blur-xl rounded-full" />
            <ClipboardList size={22} className="relative text-gray-700 dark:text-gray-200" />
          </div>
          <h3 className="text-gray-800 dark:text-gray-100 font-medium text-lg">{t('task')}</h3>
        </div>
        <button className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-all duration-200">
          <div className={cn('transition-transform duration-300', isExpanded ? 'rotate-0' : 'rotate-180')}>
            <ChevronUp size={18} className="text-gray-500 dark:text-gray-400" />
          </div>
        </button>
      </div>

      <div
        className={cn(
          'relative bg-card backdrop-blur-xl border border-border/60 rounded-2xl mt-1 mb-6 transition-all duration-300 hover:shadow-lg',
          isExpanded ? 'p-4 sm:p-6' : 'p-3 sm:p-4 cursor-pointer',
        )}
        onClick={handleExpand}
      >
        <style jsx>{`
          @keyframes progressFlow {
            0% {
              transform: translateY(-100%);
              opacity: 0;
            }
            50% {
              opacity: 1;
            }
            100% {
              transform: translateY(350%);
              opacity: 0;
            }
          }
          @keyframes rotateStep {
            0% {
              transform: rotate(0deg);
            }
            100% {
              transform: rotate(360deg);
            }
          }
          :global(.animate-rotate-step) {
            animation: rotateStep 1s ease-in-out infinite;
          }
          @keyframes slideUp {
            from {
              opacity: 0;
              transform: translateY(10px);
            }
            to {
              opacity: 1;
              transform: translateY(0);
            }
          }
          .slide-up {
            animation: slideUp 0.3s ease-out;
          }
        `}</style>

        {!isExpanded && (
          <div className="flex items-center gap-3 slide-up group/collapsed -m-1 p-1">
            <div className="flex-shrink-0 p-1 -m-1">
              <div
                className={cn(
                  'relative w-[16px] sm:w-[20px] h-[16px] sm:h-[20px] rounded-full bg-background border-2 sm:border-3 z-10 transition-all duration-300',
                  isCollapsedWarning
                    ? 'border-amber-500 shadow-lg shadow-amber-500/20'
                    : isCollapsedError
                      ? 'border-destructive shadow-lg shadow-destructive/20'
                      : isCollapsedStepCurrent
                        ? 'border-primary shadow-lg shadow-primary/20 animate-rotate-step'
                        : isCollapsedCompleted
                          ? 'border-primary/70 shadow-lg shadow-primary/15'
                          : 'border-muted-foreground/40 shadow-lg shadow-muted/10',
                )}
              >
                <div
                  className={cn(
                    'absolute inset-[3px] sm:inset-[4px] rounded-full transition-all duration-300',
                    isCollapsedWarning
                      ? 'bg-amber-500'
                      : isCollapsedError
                        ? 'bg-destructive'
                        : isCollapsedStepCurrent
                          ? 'bg-primary animate-rotate-step'
                          : isCollapsedCompleted
                            ? 'bg-primary/70'
                            : 'bg-muted-foreground/40',
                  )}
                />
              </div>
            </div>

            <StepIcon
              step_key={collapsedStep.step_key}
              tool_name={collapsedStep.tool_name}
              size={16}
              className={cn(
                'flex-shrink-0 transition-colors duration-200',
                isCollapsedWarning
                  ? 'text-amber-600 dark:text-amber-500'
                  : isCollapsedError
                    ? 'text-destructive'
                    : isSystemStep(collapsedStep.tool_name)
                      ? 'text-primary/70'
                      : 'text-foreground/70',
              )}
            />

            <h4
              className={cn(
                'text-sm font-normal transition-colors duration-200 line-clamp-1 flex-1',
                isCollapsedWarning
                  ? 'text-amber-600 dark:text-amber-400'
                  : isCollapsedError
                    ? 'text-destructive'
                    : 'text-foreground',
              )}
            >
              {collapsedStep.agent_instance && (
                <Badge
                  variant="outline"
                  className={cn(
                    'mr-1.5 h-5 px-2 text-[10px] font-bold border hidden sm:inline-flex',
                    collapsedStep.theme_color
                      ? AGENT_COLOR_CLASSES[collapsedStep.theme_color as AgentThemeColor]?.badge ||
                          AGENT_COLOR_CLASSES[getAgentColor(collapsedStep.agent_instance)].badge
                      : AGENT_COLOR_CLASSES[getAgentColor(collapsedStep.agent_instance)].badge,
                  )}
                >
                  {formatAgentHandle(collapsedStep.agent_instance, collapsedStep.display_name)}
                </Badge>
              )}
              {/* 折叠状态：显示宏观阶段而非具体工具 */}
              {inferStageLabel(collapsedStep, t)}
              {collapsedStep.step_key === 'safety_fallback_active' && (
                <Badge
                  variant="outline"
                  className="ml-2 bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400 text-[10px] uppercase tracking-wider font-bold"
                >
                  Smart Fallback
                </Badge>
              )}
            </h4>

            {collapsedStep.error_category && (
              <Badge
                variant="destructive"
                className="ml-1 h-4 px-1.2 text-[8px] uppercase tracking-wider font-bold shrink-0"
              >
                {t(`errorCategories.${collapsedStep.error_category}`)}
              </Badge>
            )}

            {collapsedStep.progress_percent != null && (
              <span
                className={`flex-shrink-0 text-xs tabular-nums ${
                  collapsedStep.notify_level === 'alert'
                    ? 'text-destructive'
                    : collapsedStep.notify_level === 'warn'
                      ? 'text-amber-600 dark:text-amber-400'
                      : 'text-muted-foreground/60'
                }`}
              >
                {collapsedStep.progress_percent}%
              </span>
            )}

            <div className="flex-shrink-0 opacity-0 group-hover/collapsed:opacity-100 transition-opacity duration-200">
              <ChevronDown size={16} className="text-muted-foreground" />
            </div>
          </div>
        )}

        {!isExpanded && isCollapsedStepCurrent && collapsedStep.stdout && (
          <div className="mt-2 ml-7 slide-up">
            <LiveTerminal stdout={collapsedStep.stdout} evictedFileRef={collapsedStep.evicted_file_ref} />
          </div>
        )}

        {isExpanded && (
          <div ref={scrollContainerRef} className="relative space-y-4 sm:space-y-6">
            <div
              className="absolute left-[7px] sm:left-[9px] w-[2px] sm:w-[2px] bg-gradient-to-b from-primary/15 via-primary/25 to-primary/10 dark:from-primary/20 dark:via-primary/30 dark:to-primary/15 rounded-full"
              style={{
                top: '0.5rem',
                bottom: '0.5rem',
              }}
            >
              {loading && (
                <div
                  className="absolute top-0 left-0 w-full h-[30%] bg-gradient-to-b from-transparent via-primary/70 to-transparent"
                  style={{ animation: 'progressFlow 3s ease-in-out infinite' }}
                />
              )}
            </div>

            {treeRoots.map((root) => renderTreeNode(root, 0))}
          </div>
        )}
      </div>
    </>
  );
});

ProgressSteps.displayName = 'ProgressSteps';

export default ProgressSteps;
