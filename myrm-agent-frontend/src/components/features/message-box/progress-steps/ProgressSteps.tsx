/**
 * [INPUT]
 * - ./CollapsedStepSummary::CollapsedStepSummary (POS: 折叠摘要)
 * - ./StepTreeList::StepTreeList + ./ProgressStepNode::StepNodeContext (POS: 展开后的步骤树)
 * - ./StepTimeline::StepRail (POS: 步骤连接线)
 * - ./StepDetailModal::StepDetailModal (POS: 步骤详情弹窗)
 * - ./treeUtils::* + ./skillManageBatch::nodeHasSkillManageUndo (POS: 树构建、折叠规则与撤销入口判断)
 *
 * [OUTPUT]
 * - ProgressSteps: renders streamed Agent progress steps as collapsed status or expanded tree.
 *
 * [POS]
 * Chat progress-step shell. Owns the expand / collapse state, the panel chrome and its animations,
 * the expand event from the undo hint, auto-scroll while loading and the detail modal;
 * the collapsed summary and the step tree are rendered by their own components.
 */

import React, { useState, useRef, useEffect } from 'react';
import { ChevronUp, ClipboardList } from 'lucide-react';
import type { ProgressItem } from '@/store/chat/types';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { StepDetailModal } from './StepDetailModal';

import { useScrollbarStyles } from './useScrollbarStyles';
import { CollapsedStepSummary } from './CollapsedStepSummary';
import type { StepNodeContext } from './ProgressStepNode';
import { StepRail } from './StepTimeline';
import { StepTreeList } from './StepTreeList';
import { buildTree, foldRoots } from './treeUtils';
import { nodeHasSkillManageUndo } from './skillManageBatch';
import { EXPAND_PROGRESS_STEPS_EVENT, type ExpandProgressStepsDetail } from '@/lib/chat/progressStepsUi';

interface ProgressStepsProps {
  messageId: string;
  steps: ProgressItem[];
  loading: boolean;
}

/** A step whose full output was evicted to a file the user can open. */
const hasEvictedOutput = (step: ProgressItem): boolean =>
  (typeof step.evicted_file_ref === 'string' && step.evicted_file_ref.length > 0) ||
  (typeof step.evicted_stderr_file_ref === 'string' && step.evicted_stderr_file_ref.length > 0);

const ProgressSteps: React.FC<ProgressStepsProps> = React.memo(({ messageId, steps, loading }) => {
  const t = useTranslations('progressSteps');
  const tHumanize = useTranslations('humanize');
  const [isExpanded, setIsExpanded] = useState(false);
  const [selectedStepForModal, setSelectedStepForModal] = useState<ProgressItem | null>(null);
  const [showAllIntermediateSteps, setShowAllIntermediateSteps] = useState(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  useScrollbarStyles();

  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<ExpandProgressStepsDetail>;
      const targetId = custom.detail?.messageId?.trim();
      if (targetId && targetId === messageId) {
        setIsExpanded(true);
        // The undo hint sends the user here for the undo control; unfold the stretch it may be folded into.
        if (foldRoots(buildTree(steps))?.folded.some(nodeHasSkillManageUndo)) {
          setShowAllIntermediateSteps(true);
        }
      }
    };
    window.addEventListener(EXPAND_PROGRESS_STEPS_EVENT, handler);
    return () => window.removeEventListener(EXPAND_PROGRESS_STEPS_EVENT, handler);
  }, [messageId, steps]);

  useEffect(() => {
    if (scrollContainerRef.current && isExpanded && loading) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    }
  }, [steps.length, isExpanded, loading]);

  useEffect(() => {
    if (steps.some(hasEvictedOutput)) {
      setIsExpanded(true);
    }
  }, [messageId, steps]);

  const handleExpand = () => {
    if (!isExpanded) {
      setIsExpanded(true);
    }
  };

  const toggleExpanded = () => setIsExpanded(!isExpanded);

  if (steps.length === 0) {
    return null;
  }

  const nodeContext: StepNodeContext = {
    messageId,
    lastIndex: steps.length - 1,
    loading,
    t,
    tHumanize,
    onViewDetail: setSelectedStepForModal,
  };
  // The collapsed summary shows the latest step, unless an image analysis ran: its latest step takes that place.
  const collapsedStep = steps.findLast((step) => step.step_key === 'analyzing_image') ?? steps[steps.length - 1];

  return (
    <>
      <div
        data-message-id={messageId}
        data-testid="progress-steps-toggle"
        data-expanded={isExpanded ? 'true' : 'false'}
        className="flex items-center justify-between mt-6 cursor-pointer group hover:opacity-90 transition-opacity duration-200"
        onClick={toggleExpanded}
        role="presentation"
      >
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <div className="absolute inset-0 bg-gradient-to-r from-blue-500/20 to-purple-500/20 dark:from-blue-400/20 dark:to-purple-400/20 blur-xl rounded-full" />
            <ClipboardList size={22} className="relative text-gray-700 dark:text-gray-200" />
          </div>
          <h3 data-testid="progress-steps-title" className="text-gray-800 dark:text-gray-100 font-medium text-lg">
            {t('task')}
          </h3>
        </div>
        <button className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-all duration-200">
          <div className={cn('transition-transform duration-300', isExpanded ? 'rotate-0' : 'rotate-180')}>
            <ChevronUp size={18} className="text-gray-500 dark:text-gray-400" />
          </div>
        </button>
      </div>

      <div
        data-testid="progress-steps-panel"
        className={cn(
          'relative bg-card border border-border/60 rounded-2xl mt-1 mb-6 transition-all duration-300 hover:shadow-lg',
          isExpanded ? 'p-4 sm:p-6' : 'p-3 sm:p-4 cursor-pointer',
        )}
        onClick={handleExpand}
        role="presentation"
      >
        {/* The child components use these animation classes, so they are global rather than scoped to this file. */}
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
          :global(.slide-up) {
            animation: slideUp 0.3s ease-out;
          }
        `}</style>

        {!isExpanded && (
          <CollapsedStepSummary
            step={collapsedStep}
            evictedStep={steps.findLast(hasEvictedOutput) ?? null}
            loading={loading}
            t={t}
          />
        )}

        {isExpanded && (
          <div ref={scrollContainerRef} className="relative space-y-4 sm:space-y-6">
            <StepRail>
              {loading && (
                <div
                  className="absolute top-0 left-0 w-full h-[30%] bg-gradient-to-b from-transparent via-primary/70 to-transparent"
                  style={{ animation: 'progressFlow 3s ease-in-out infinite' }}
                />
              )}
            </StepRail>

            <StepTreeList
              roots={buildTree(steps)}
              showAll={showAllIntermediateSteps}
              onShowAllChange={setShowAllIntermediateSteps}
              ctx={nodeContext}
            />
          </div>
        )}
      </div>

      <StepDetailModal
        step={selectedStepForModal}
        open={Boolean(selectedStepForModal)}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedStepForModal(null);
          }
        }}
      />
    </>
  );
});

ProgressSteps.displayName = 'ProgressSteps';

export default ProgressSteps;
