'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Video,
  Square,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  FileCode,
  ArrowRight,
  Plus,
  Trash2,
  Loader2,
  X,
} from 'lucide-react';
import {
  WorkflowIntentPlan,
  WorkflowPlanStep,
  startDesktopRecording,
  stopDesktopRecording,
  recordDesktopEvent,
  analyzeDesktopPlan,
  compileDesktopPlan,
  publishDesktopSkill,
} from '@/services/skill/core';

interface WorkflowRecorderModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPublished?: (skillName: string) => void;
}

export const WorkflowRecorderModal: React.FC<WorkflowRecorderModalProps> = ({ isOpen, onClose, onPublished }) => {
  const t = useTranslations('skills.workflowRecorder');
  const [step, setStep] = useState<'idle' | 'recording' | 'review' | 'preview' | 'published'>('idle');
  const [sessionId, setSessionId] = useState<string>('');
  const [skillName, setSkillName] = useState<string>('Custom Desktop Workflow');
  const [intentHint, setIntentHint] = useState<string>('');
  const [eventCount, setEventCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<WorkflowIntentPlan | null>(null);
  const [compiledMarkdown, setCompiledMarkdown] = useState<string>('');

  const handleStart = async () => {
    setError(null);
    setLoading(true);
    try {
      const newSessionId = `rec-${Date.now()}`;
      setSessionId(newSessionId);
      await startDesktopRecording(newSessionId);
      setEventCount(0);
      setStep('recording');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start recording');
    } finally {
      setLoading(false);
    }
  };

  const handleSimulateEvent = async (action: string, app: string, detail: string) => {
    if (!sessionId) return;
    const nextSeq = eventCount + 1;
    await recordDesktopEvent({
      session_id: sessionId,
      seq: nextSeq,
      action,
      app_name: app,
      element_title: detail,
      value: action === 'type' ? 'PARAM_VALUE' : undefined,
    });
    setEventCount(nextSeq);
  };

  const handleStopAndAnalyze = async () => {
    if (!sessionId) return;
    setError(null);
    setLoading(true);
    try {
      await stopDesktopRecording(sessionId);
      const res = await analyzeDesktopPlan(sessionId, skillName, intentHint);
      setPlan(res.plan);
      setStep('review');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to analyze recording');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateStepTitle = (idx: number, newTitle: string) => {
    if (!plan) return;
    const updated = [...plan.steps];
    updated[idx] = { ...updated[idx], title: newTitle };
    setPlan({ ...plan, steps: updated });
  };

  const handleUpdateStepDesc = (idx: number, newDesc: string) => {
    if (!plan) return;
    const updated = [...plan.steps];
    updated[idx] = { ...updated[idx], description: newDesc };
    setPlan({ ...plan, steps: updated });
  };

  const handleDeleteStep = (idx: number) => {
    if (!plan) return;
    const updated = plan.steps.filter((_, i) => i !== idx);
    setPlan({ ...plan, steps: updated });
  };

  const handleAddStep = () => {
    if (!plan) return;
    const newStep: WorkflowPlanStep = {
      step_id: `step-${plan.steps.length + 1}`,
      title: 'New Custom Action',
      description: 'Execute intermediate validation or transformation',
      tool_hint: 'shell_execute',
    };
    setPlan({ ...plan, steps: [...plan.steps, newStep] });
  };

  const handleCompileAndPreview = async () => {
    if (!plan) return;
    setError(null);
    setLoading(true);
    try {
      const res = await compileDesktopPlan(plan);
      setCompiledMarkdown(res.markdown_content);
      setStep('preview');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to compile plan');
    } finally {
      setLoading(false);
    }
  };

  const handlePublish = async () => {
    if (!sessionId || !compiledMarkdown || !plan) return;
    setError(null);
    setLoading(true);
    try {
      await publishDesktopSkill(sessionId, plan.name, compiledMarkdown, plan.description || '');
      setStep('published');
      onPublished?.(plan.name);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to publish skill');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-3xl rounded-xl border border-border bg-card shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4 bg-muted/30">
          <div className="flex items-center gap-2">
            <Video className="h-5 w-5 text-primary" />
            <h3 className="font-semibold text-lg text-foreground">{t('title')}</h3>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {step === 'idle' && (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground leading-relaxed">{t('idleDesc')}</p>
              <div className="space-y-3">
                <label className="text-xs font-medium text-foreground">{t('workflowNameLabel')}</label>
                <input
                  type="text"
                  value={skillName}
                  onChange={(e) => setSkillName(e.target.value)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                  placeholder="e.g. Monthly Tax Filing Pipeline"
                />
              </div>
              <div className="space-y-3">
                <label className="text-xs font-medium text-foreground">{t('intentHintLabel')}</label>
                <input
                  type="text"
                  value={intentHint}
                  onChange={(e) => setIntentHint(e.target.value)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                  placeholder="e.g. Read Excel and sync to tax portal"
                />
              </div>
            </div>
          )}

          {step === 'recording' && (
            <div className="space-y-4 text-center py-6">
              <div className="inline-flex p-4 rounded-full bg-red-500/10 text-red-500 animate-pulse">
                <Video className="h-8 w-8" />
              </div>
              <div>
                <h4 className="font-medium text-foreground">{t('recordingActive')}</h4>
                <p className="text-xs text-muted-foreground mt-1">{t('eventsCaptured', { count: eventCount })}</p>
              </div>
              {/* Quick simulation helper buttons for GUI testing */}
              <div className="flex flex-wrap gap-2 justify-center pt-2">
                <button
                  type="button"
                  onClick={() => handleSimulateEvent('app_switch', 'Microsoft Excel', 'Spreadsheet')}
                  className="text-xs px-2.5 py-1 rounded border border-border bg-muted/40 hover:bg-muted"
                >
                  + Excel Switch
                </button>
                <button
                  type="button"
                  onClick={() => handleSimulateEvent('click', 'Chrome Browser', 'Submit Button')}
                  className="text-xs px-2.5 py-1 rounded border border-border bg-muted/40 hover:bg-muted"
                >
                  + Click Submit
                </button>
                <button
                  type="button"
                  onClick={() => handleSimulateEvent('type', 'Chrome Browser', 'Tax Account')}
                  className="text-xs px-2.5 py-1 rounded border border-border bg-muted/40 hover:bg-muted"
                >
                  + Type Account
                </button>
              </div>
            </div>
          )}

          {step === 'review' && plan && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-semibold text-foreground flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-primary" />
                  {t('reviewStepsTitle')}
                </h4>
                <button
                  type="button"
                  onClick={handleAddStep}
                  className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-md bg-primary/10 text-primary hover:bg-primary/20 transition"
                >
                  <Plus className="h-3.5 w-3.5" />
                  {t('addStep')}
                </button>
              </div>

              <div className="space-y-3">
                {plan.steps.map((s, idx) => (
                  <div key={s.step_id} className="p-3 rounded-lg border border-border bg-muted/20 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-mono font-bold text-muted-foreground">#{idx + 1}</span>
                      <input
                        type="text"
                        value={s.title}
                        onChange={(e) => handleUpdateStepTitle(idx, e.target.value)}
                        className="flex-1 rounded border border-border bg-background px-2.5 py-1 text-xs font-medium focus:outline-none focus:ring-1 focus:ring-primary"
                      />
                      <button
                        type="button"
                        onClick={() => handleDeleteStep(idx)}
                        className="text-muted-foreground hover:text-destructive p-1 rounded transition"
                        aria-label="Delete step"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    <textarea
                      value={s.description}
                      onChange={(e) => handleUpdateStepDesc(idx, e.target.value)}
                      rows={2}
                      className="w-full rounded border border-border bg-background px-2.5 py-1 text-xs text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary resize-none"
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          {step === 'preview' && (
            <div className="space-y-3">
              <h4 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <FileCode className="h-4 w-4 text-primary" />
                {t('previewTitle')}
              </h4>
              <pre className="p-4 rounded-lg border border-border bg-muted/40 text-xs font-mono text-foreground overflow-x-auto max-h-60 leading-relaxed">
                {compiledMarkdown}
              </pre>
            </div>
          )}

          {step === 'published' && (
            <div className="text-center py-8 space-y-3">
              <CheckCircle2 className="h-10 w-10 text-emerald-500 mx-auto" />
              <h4 className="font-semibold text-foreground">{t('publishSuccessTitle')}</h4>
              <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                {t('publishSuccessDesc', { name: plan?.name || skillName })}
              </p>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between border-t border-border px-6 py-4 bg-muted/30">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm text-muted-foreground hover:bg-muted transition"
          >
            {step === 'published' ? t('close') : t('cancel')}
          </button>

          <div className="flex items-center gap-3">
            {step === 'idle' && (
              <button
                type="button"
                onClick={handleStart}
                disabled={loading}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition disabled:opacity-50"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Video className="h-4 w-4" />}
                {t('startRecording')}
              </button>
            )}

            {step === 'recording' && (
              <button
                type="button"
                onClick={handleStopAndAnalyze}
                disabled={loading}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-red-600 text-white text-sm font-medium hover:bg-red-700 transition disabled:opacity-50"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4" />}
                {t('stopAndAnalyze')}
              </button>
            )}

            {step === 'review' && (
              <button
                type="button"
                onClick={handleCompileAndPreview}
                disabled={loading}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition disabled:opacity-50"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                {t('compilePreview')}
              </button>
            )}

            {step === 'preview' && (
              <button
                type="button"
                onClick={handlePublish}
                disabled={loading}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 transition disabled:opacity-50"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                {t('publishSkill')}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default WorkflowRecorderModal;
