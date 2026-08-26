'use client';

import React, { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  X,
  Play,
  Square,
  Sparkles,
  Layers,
  CheckCircle2,
  AlertTriangle,
  Code2,
  Trash2,
  FileCode,
  Sliders,
} from 'lucide-react';
import { useDesktopRecordingStore } from '@/store/useDesktopRecordingStore';

export const DesktopRecordingDrawer: React.FC = () => {
  const t = useTranslations('skills.desktopRecording');
  const {
    isOpen,
    status,
    steps,
    draft,
    error,
    startRecording,
    stopRecording,
    synthesizeDraft,
    deleteStep,
    publishSkill,
    updateDraftMarkdown,
    closeDrawer,
    reset,
  } = useDesktopRecordingStore();

  const [skillName, setSkillName] = useState('');
  const [skillDesc, setSkillDesc] = useState('');
  const [isPublishing, setIsPublishing] = useState(false);

  const handleStart = useCallback(() => {
    startRecording('all');
  }, [startRecording]);

  const handleStop = useCallback(() => {
    stopRecording();
  }, [stopRecording]);

  const handleSynthesize = useCallback(async () => {
    const name = skillName.trim() || 'desktop_workflow_skill';
    await synthesizeDraft(name, skillDesc.trim());
  }, [skillName, skillDesc, synthesizeDraft]);

  const handlePublish = useCallback(async () => {
    const name = skillName.trim() || draft?.skill_name || 'desktop_workflow_skill';
    setIsPublishing(true);
    try {
      await publishSkill(name);
    } finally {
      setIsPublishing(false);
    }
  }, [skillName, draft, publishSkill]);

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t('drawerTitle')}
      className="fixed inset-y-0 right-0 z-50 w-full sm:w-[540px] bg-background border-l border-border shadow-2xl flex flex-col transition-all duration-300"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-muted/30">
        <div className="flex items-center gap-2">
          <Layers className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold text-foreground">{t('drawerTitle')}</h2>
        </div>
        <button
          onClick={closeDrawer}
          className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          aria-label={t('close')}
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Main Body */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {error && (
          <div className="p-3 bg-destructive/10 border border-destructive/30 rounded-lg flex items-center gap-2 text-destructive text-sm">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Status Tracker */}
        <div className="flex items-center justify-between p-4 rounded-xl bg-card border border-border shadow-sm">
          <div>
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              {t('currentStatus')}
            </div>
            <div className="text-base font-semibold text-foreground capitalize mt-0.5">
              {t(`status_${status}`)}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {status === 'idle' && (
              <button
                onClick={handleStart}
                className="px-4 py-2 rounded-lg bg-primary text-primary-foreground font-medium text-sm flex items-center gap-1.5 hover:bg-primary/90 shadow-sm transition-all"
              >
                <Play className="w-4 h-4 fill-current" />
                {t('btnStart')}
              </button>
            )}
            {status === 'recording' && (
              <button
                onClick={handleStop}
                className="px-4 py-2 rounded-lg bg-destructive text-destructive-foreground font-medium text-sm flex items-center gap-1.5 hover:bg-destructive/90 shadow-sm animate-pulse"
              >
                <Square className="w-4 h-4 fill-current" />
                {t('btnStop')}
              </button>
            )}
            {(status === 'stopped' || status === 'draft_ready') && (
              <button
                onClick={reset}
                className="px-3 py-1.5 rounded-lg border border-border text-muted-foreground hover:text-foreground hover:bg-muted text-xs transition-colors"
              >
                {t('btnReset')}
              </button>
            )}
          </div>
        </div>

        {/* Form Inputs (when stopped or synthesizing) */}
        {(status === 'stopped' || status === 'draft_ready') && (
          <div className="space-y-4 p-4 rounded-xl bg-card border border-border">
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                {t('skillNameLabel')}
              </label>
              <input
                type="text"
                value={skillName}
                onChange={(e) => setSkillName(e.target.value)}
                placeholder={t('skillNamePlaceholder')}
                className="w-full px-3 py-2 text-sm rounded-lg bg-background border border-input focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                {t('skillDescLabel')}
              </label>
              <textarea
                value={skillDesc}
                onChange={(e) => setSkillDesc(e.target.value)}
                placeholder={t('skillDescPlaceholder')}
                rows={2}
                className="w-full px-3 py-2 text-sm rounded-lg bg-background border border-input focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            {status === 'stopped' && (
              <button
                onClick={handleSynthesize}
                disabled={steps.length === 0}
                className="w-full py-2.5 rounded-lg bg-primary text-primary-foreground font-medium text-sm flex items-center justify-center gap-2 hover:bg-primary/90 disabled:opacity-50 transition-all"
              >
                <Sparkles className="w-4 h-4" />
                {t('btnSynthesize')}
              </button>
            )}
          </div>
        )}

        {/* Synthesized Draft Review Area */}
        {status === 'draft_ready' && draft && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                <Code2 className="w-4 h-4 text-primary" />
                {t('draftTitle')}
              </h3>
              {draft.tool_lifting_applied && (
                <span className="px-2 py-0.5 rounded-full text-xs bg-emerald-500/10 text-emerald-600 border border-emerald-500/30 flex items-center gap-1">
                  <Sparkles className="w-3 h-3" />
                  {t('toolLiftingActive')}
                </span>
              )}
            </div>

            {/* Variable Slots */}
            {draft.parameters.length > 0 && (
              <div className="p-3 rounded-lg bg-muted/40 border border-border text-xs space-y-1.5">
                <div className="font-medium text-foreground flex items-center gap-1">
                  <Sliders className="w-3.5 h-3.5 text-muted-foreground" />
                  {t('parameterSlots')}
                </div>
                {draft.parameters.map((p) => (
                  <div key={p.name} className="flex items-center justify-between text-muted-foreground">
                    <span className="font-mono text-primary">{`{{${p.name}}}`}</span>
                    <span className="truncate max-w-[200px]">{p.description}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Editable Markdown Area */}
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                {t('markdownEditorLabel')}
              </label>
              <textarea
                value={draft.markdown_content}
                onChange={(e) => updateDraftMarkdown(e.target.value)}
                rows={8}
                className="w-full font-mono text-xs px-3 py-2 rounded-lg bg-muted/50 border border-input focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>

            <button
              onClick={handlePublish}
              disabled={isPublishing}
              className="w-full py-2.5 rounded-lg bg-emerald-600 text-white font-medium text-sm flex items-center justify-center gap-2 hover:bg-emerald-700 shadow-md transition-all"
            >
              <CheckCircle2 className="w-4 h-4" />
              {isPublishing ? t('publishing') : t('btnPublish')}
            </button>
          </div>
        )}

        {/* Published Success Card */}
        {status === 'published' && (
          <div className="p-6 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-center space-y-3">
            <CheckCircle2 className="w-10 h-10 text-emerald-600 mx-auto" />
            <h4 className="text-base font-semibold text-foreground">{t('publishSuccessTitle')}</h4>
            <p className="text-xs text-muted-foreground">{t('publishSuccessDesc')}</p>
            <button
              onClick={reset}
              className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-medium"
            >
              {t('btnNewRecord')}
            </button>
          </div>
        )}

        {/* Steps List */}
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
            <span>{t('stepsHeading', { count: steps.length })}</span>
          </div>
          {steps.length === 0 ? (
            <div className="p-8 text-center border border-dashed border-border rounded-xl text-muted-foreground text-xs">
              <FileCode className="w-8 h-8 mx-auto mb-2 opacity-50" />
              {t('noStepsYet')}
            </div>
          ) : (
            <div className="space-y-2">
              {steps.map((step) => (
                <div
                  key={step.seq}
                  className="p-3 rounded-lg bg-card border border-border flex items-start justify-between gap-3 text-xs group"
                >
                  <div className="flex items-start gap-2.5">
                    <span className="w-5 h-5 rounded-full bg-primary/10 text-primary font-semibold flex items-center justify-center flex-shrink-0 mt-0.5">
                      {step.seq}
                    </span>
                    <div>
                      <div className="font-medium text-foreground">
                        {step.action} {step.element_title ? `"${step.element_title}"` : ''}
                      </div>
                      <div className="text-muted-foreground mt-0.5">
                        {step.app_name && <span className="mr-2 text-primary/80">[{step.app_name}]</span>}
                        {step.value && <span className="font-mono">value: {step.value}</span>}
                      </div>
                    </div>
                  </div>
                  {status !== 'recording' && (
                    <button
                      onClick={() => deleteStep(step.seq)}
                      className="p-1 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-opacity"
                      aria-label={t('deleteStep')}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
