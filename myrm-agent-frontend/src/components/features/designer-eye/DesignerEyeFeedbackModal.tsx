'use client';

/**
 * [INPUT]
 * - InspectedElementContext, SourceLocation from @/services/selfEvolution
 * - createSelfEvolutionTask, recoverSelfEvolution from @/services/selfEvolution
 * - Translation strings from 'designerEye' namespace
 *
 * [OUTPUT]
 * - DesignerEyeFeedbackModal: Semantic dialog modal for submitting visual feedback and triggering self-evolution / rollback
 *
 * [POS]
 * Feedback capture dialog in the Designer's Eye UI Element Inspector pipeline.
 * Strict typing: Zero `any`. File length < 350 lines. Accessible <dialog> structure.
 */

import { useState, useCallback, useId, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconCheck,
  IconRefresh,
  IconSparkles,
  IconX,
} from '@/components/features/icons/PremiumIcons';
import type {
  InspectedElementContext,
  SelfEvolutionTaskResponse,
  SourceLocation,
} from '@/services/selfEvolution';
import {
  createSelfEvolutionTask,
  recoverSelfEvolution,
} from '@/services/selfEvolution';

export interface DesignerEyeFeedbackModalProps {
  isOpen: boolean;
  onClose: () => void;
  target: InspectedElementContext | null;
  onTaskCreated?: (task: SelfEvolutionTaskResponse) => void;
}

const PRESET_TAG_OPTIONS = [
  'spacing',
  'dark_mode',
  'typography',
  'border_radius',
  'responsive',
  'contrast',
  'glassmorphism',
] as const;

export function DesignerEyeFeedbackModal({
  isOpen,
  onClose,
  target,
  onTaskCreated,
}: DesignerEyeFeedbackModalProps) {
  const t = useTranslations('designerEye');
  const titleId = useId();
  const descId = useId();

  const [userPrompt, setUserPrompt] = useState<string>('');
  const [selectedTags, setSelectedTags] = useState<string[]>(['spacing']);
  const [selectedSource, setSelectedSource] = useState<SourceLocation | undefined>(undefined);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [isRecovering, setIsRecovering] = useState<boolean>(false);
  const [lastTask, setLastTask] = useState<SelfEvolutionTaskResponse | null>(null);
  const [rollbackNotice, setRollbackNotice] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Sync selectedSource with target's primary source whenever target opens
  useEffect(() => {
    if (target) {
      setSelectedSource(target.primarySource || target.candidates?.[0]);
      setLastTask(null);
      setRollbackNotice(null);
      setErrorMessage(null);
    }
  }, [target]);

  const toggleTag = useCallback((tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((tItem) => tItem !== tag) : [...prev, tag],
    );
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!target || !userPrompt.trim()) {
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setRollbackNotice(null);

    try {
      const task = await createSelfEvolutionTask({
        dom_selector: target.domSelector,
        tag_name: target.tagName,
        classes: target.classes,
        component_hint: selectedSource?.componentName || target.componentHint,
        component_hierarchy: target.componentHierarchy,
        primary_source: selectedSource,
        candidates: target.candidates,
        text_snippet: target.textSnippet,
        user_prompt: userPrompt.trim(),
        preset_tags: selectedTags,
        computed_style_summary: target.computedStyleSummary,
      });
      setLastTask(task);
      if (onTaskCreated) {
        onTaskCreated(task);
      }
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : 'Failed to submit self-evolution task',
      );
    } finally {
      setIsSubmitting(false);
    }
  }, [target, selectedSource, userPrompt, selectedTags, onTaskCreated]);

  const handleRollback = useCallback(async () => {
    setIsRecovering(true);
    setErrorMessage(null);
    setRollbackNotice(null);

    try {
      const res = await recoverSelfEvolution({
        checkpoint_id: lastTask?.recoverable_checkpoint_id,
        task_id: lastTask?.task_id,
      });
      setRollbackNotice(res.message);
      setLastTask(null);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : 'Failed to rollback checkpoint',
      );
    } finally {
      setIsRecovering(false);
    }
  }, [lastTask]);

  if (!isOpen || !target) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <dialog
        open
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="w-full max-w-lg rounded-2xl bg-card border border-border shadow-2xl p-6 text-foreground flex flex-col gap-4 m-0 max-h-[90vh] overflow-y-auto"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border/60 pb-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center font-bold">
              <IconSparkles className="w-4 h-4" />
            </div>
            <div>
              <h2 id={titleId} className="text-base font-semibold">
                {t('modalTitle')}
              </h2>
              <p id={descId} className="text-xs text-muted-foreground">
                {t('modalSubtitle')}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            aria-label={t('closeAriaLabel')}
          >
            <IconX className="w-5 h-5" />
          </button>
        </div>

        {/* Inspected Element & Fiber Source Snapshot */}
        <div className="rounded-xl bg-muted/50 p-3 text-xs flex flex-col gap-2 border border-border/40 font-mono">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-primary">
              &lt;{target.tagName}&gt;
            </span>
            <span className="text-[10px] text-muted-foreground px-2 py-0.5 rounded bg-background/80 border border-border/40">
              {target.componentHint || 'GenericElement'}
            </span>
          </div>

          <div className="truncate text-muted-foreground text-[11px]" title={target.domSelector}>
            {target.domSelector}
          </div>

          {/* Reverse-mapped Source Location */}
          {selectedSource && (
            <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-primary/10 border border-primary/20 text-primary text-[11px]">
              <span className="font-semibold shrink-0">Source:</span>
              <span className="truncate" title={selectedSource.fileName}>
                {selectedSource.fileName}
                {selectedSource.lineNumber ? `:${selectedSource.lineNumber}` : ''}
              </span>
              <span className="ml-auto text-[9px] uppercase px-1 py-0.2 rounded bg-primary/20 shrink-0">
                {selectedSource.confidence}
              </span>
            </div>
          )}

          {/* Candidate selector if multiple matches exist */}
          {target.candidates && target.candidates.length > 1 && (
            <div className="flex items-center gap-1 mt-1 text-[10px]">
              <span className="text-muted-foreground shrink-0">Candidates:</span>
              <div className="flex flex-wrap gap-1">
                {target.candidates.map((cand) => {
                  const isSelected = selectedSource?.fileName === cand.fileName;
                  return (
                    <button
                      key={cand.fileName}
                      type="button"
                      onClick={() => setSelectedSource(cand)}
                      className={`px-1.5 py-0.5 rounded transition-colors ${
                        isSelected
                          ? 'bg-primary text-primary-foreground font-semibold'
                          : 'bg-background text-muted-foreground hover:bg-muted border border-border/40'
                      }`}
                    >
                      {cand.componentName || cand.fileName.split('/').pop()}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {target.classes.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-0.5">
              {target.classes.slice(0, 5).map((cls) => (
                <span
                  key={cls}
                  className="px-1.5 py-0.5 rounded text-[10px] bg-background text-muted-foreground border border-border/30"
                >
                  .{cls}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Preset Tags */}
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">
            {t('quickTagsLabel')}
          </span>
          <div className="flex flex-wrap gap-1.5">
            {PRESET_TAG_OPTIONS.map((tag) => {
              const active = selectedTags.includes(tag);
              return (
                <button
                  key={tag}
                  type="button"
                  onClick={() => toggleTag(tag)}
                  className={`px-2.5 py-1 rounded-full text-xs transition-colors border ${
                    active
                      ? 'bg-primary text-primary-foreground border-primary font-medium'
                      : 'bg-muted/40 text-muted-foreground border-border/60 hover:bg-muted'
                  }`}
                >
                  #{tag}
                </button>
              );
            })}
          </div>
        </div>

        {/* User Prompt Textarea */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="designer-eye-prompt" className="text-xs font-medium text-foreground">
            {t('promptLabel')}
          </label>
          <textarea
            id="designer-eye-prompt"
            rows={3}
            value={userPrompt}
            onChange={(e) => setUserPrompt(e.target.value)}
            placeholder={t('promptPlaceholder')}
            className="w-full rounded-xl bg-background border border-border p-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 resize-none"
          />
        </div>

        {/* Status / Feedback notices */}
        {errorMessage && (
          <div className="rounded-lg bg-destructive/10 text-destructive text-xs p-2.5 border border-destructive/20">
            {errorMessage}
          </div>
        )}

        {rollbackNotice && (
          <div className="rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-xs p-2.5 border border-emerald-500/20 flex items-center gap-1.5">
            <IconCheck className="w-3.5 h-3.5 shrink-0" />
            <span>{rollbackNotice}</span>
          </div>
        )}

        {lastTask && (
          <div className="rounded-lg bg-primary/10 text-primary text-xs p-2.5 border border-primary/20 flex flex-col gap-1">
            <div className="flex items-center justify-between font-semibold">
              <span>{t('taskCreatedTitle')}: {lastTask.task_id}</span>
              <span className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-primary/20">
                {lastTask.status}
              </span>
            </div>
            {lastTask.target_component_file && (
              <span className="text-[11px] font-mono text-muted-foreground">
                Target: {lastTask.target_component_file}
                {lastTask.target_line_number ? `:${lastTask.target_line_number}` : ''}
              </span>
            )}
          </div>
        )}

        {/* Footer Actions */}
        <div className="flex items-center justify-between pt-2 border-t border-border/60">
          <button
            type="button"
            onClick={handleRollback}
            disabled={isRecovering}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted border border-border/60 transition-colors disabled:opacity-50"
          >
            <IconRefresh className={`w-3.5 h-3.5 ${isRecovering ? 'animate-spin' : ''}`} />
            <span>{t('rollbackAction')}</span>
          </button>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 rounded-lg text-xs text-muted-foreground hover:bg-muted transition-colors"
            >
              {t('cancelAction')}
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={isSubmitting || !userPrompt.trim()}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              <IconSparkles className="w-3.5 h-3.5" />
              <span>{isSubmitting ? t('submittingAction') : t('submitEvolutionAction')}</span>
            </button>
          </div>
        </div>
      </dialog>
    </div>
  );
}
