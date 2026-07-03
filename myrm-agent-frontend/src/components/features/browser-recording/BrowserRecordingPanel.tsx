'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  Circle,
  Square,
  Pause,
  Play,
  Sparkles,
  X,
  AlertTriangle,
  CheckCircle2,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import useBrowserRecordingStore from '@/store/useBrowserRecordingStore';
import RecordingStepCard from './RecordingStepCard';

const BrowserRecordingPanel: React.FC = () => {
  const t = useTranslations('chat.browserRecording');
  const {
    isOpen,
    status,
    steps,
    error,
    generatedSkill,
    startRecording,
    stopRecording,
    pauseRecording,
    resumeRecording,
    deleteStep,
    generateSkill,
    reset,
    closePanel,
  } = useBrowserRecordingStore();

  const [skillName, setSkillName] = useState('');
  const [skillDesc, setSkillDesc] = useState('');
  const stepsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    stepsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [steps.length]);

  const handleStart = useCallback(() => {
    startRecording();
  }, [startRecording]);

  const handleGenerateSkill = useCallback(async () => {
    if (!skillName.trim()) return;
    await generateSkill(skillName.trim(), skillDesc.trim());
  }, [generateSkill, skillName, skillDesc]);

  if (!isOpen) return null;

  const isRecording = status === 'recording';
  const isPaused = status === 'paused';
  const isStopped = status === 'stopped';
  const isGenerating = status === 'generating';

  return (
    <div
      className={cn(
        'fixed right-4 bottom-36 w-80 max-h-[70vh] z-50',
        'bg-background border border-border rounded-xl shadow-2xl',
        'flex flex-col overflow-hidden',
        'max-sm:right-2 max-sm:bottom-28 max-sm:w-[calc(100vw-1rem)]',
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-muted border-b border-border">
        <div className="flex items-center gap-2">
          {isRecording && <span className="w-2 h-2 rounded-full bg-destructive animate-pulse" />}
          {isPaused && <span className="w-2 h-2 rounded-full bg-yellow-500" />}
          {!isRecording && !isPaused && <Circle size={8} className="text-muted-foreground" />}
          <span className="text-sm font-medium">
            {status === 'idle' && t('statusIdle')}
            {isRecording && t('statusRecording')}
            {isPaused && t('statusPaused')}
            {isStopped && t('statusComplete')}
            {isGenerating && t('statusGenerating')}
          </span>
          {steps.length > 0 && (
            <span className="text-xs text-muted-foreground bg-muted-foreground/10 px-1.5 py-0.5 rounded-full">
              {t('stepsCount', { count: steps.length })}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={closePanel}
          className="p-1 rounded hover:bg-accent text-muted-foreground"
          aria-label={t('closePanel')}
        >
          <X size={14} />
        </button>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-1.5 px-3 py-2 border-b border-border">
        {status === 'idle' && (
          <button
            type="button"
            onClick={handleStart}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium',
              'bg-destructive text-destructive-foreground hover:bg-destructive/90',
            )}
          >
            <Circle size={14} fill="currentColor" />
            {t('startRecording')}
          </button>
        )}

        {isRecording && (
          <>
            <button
              type="button"
              onClick={pauseRecording}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-sm bg-yellow-500/10 text-yellow-600 hover:bg-yellow-500/20"
            >
              <Pause size={14} />
              {t('pause')}
            </button>
            <button
              type="button"
              onClick={stopRecording}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-sm bg-accent text-foreground hover:bg-accent/80"
            >
              <Square size={14} />
              {t('stop')}
            </button>
          </>
        )}

        {isPaused && (
          <>
            <button
              type="button"
              onClick={resumeRecording}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-sm bg-chart-2/10 text-chart-2 hover:bg-chart-2/20"
            >
              <Play size={14} />
              {t('resume')}
            </button>
            <button
              type="button"
              onClick={stopRecording}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-sm bg-accent text-foreground hover:bg-accent/80"
            >
              <Square size={14} />
              {t('stop')}
            </button>
          </>
        )}

        {(isStopped || generatedSkill) && (
          <button
            type="button"
            onClick={reset}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-sm bg-accent text-foreground hover:bg-accent/80"
          >
            {t('newRecording')}
          </button>
        )}
      </div>

      {/* Steps List */}
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1.5 max-h-[40vh]">
        {steps.length === 0 && status !== 'idle' && (
          <p className="text-center text-xs text-muted-foreground py-4">
            {t('waitingForActions')}
          </p>
        )}
        {steps.length === 0 && status === 'idle' && (
          <p className="text-center text-xs text-muted-foreground py-4">
            {t('idleHint')}
          </p>
        )}
        {steps.map((step) => (
          <RecordingStepCard
            key={step.seq}
            step={step}
            onDelete={isRecording || isPaused ? deleteStep : undefined}
            readonly={isStopped || isGenerating}
          />
        ))}
        <div ref={stepsEndRef} />
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 px-3 py-2 bg-destructive/10 border-t border-destructive/20">
          <AlertTriangle size={14} className="text-destructive flex-shrink-0" />
          <span className="text-xs text-destructive">{error}</span>
        </div>
      )}

      {/* Skill Generation */}
      {isStopped && steps.length > 0 && !generatedSkill && (
        <div className="px-3 py-3 border-t border-border space-y-2">
          <input
            type="text"
            value={skillName}
            onChange={(e) => setSkillName(e.target.value)}
            placeholder={t('skillNamePlaceholder')}
            className={cn(
              'w-full px-2.5 py-1.5 rounded-lg text-sm',
              'bg-muted border border-border',
              'focus:outline-none focus:ring-1 focus:ring-primary',
            )}
            pattern="^[a-zA-Z][a-zA-Z0-9_-]*$"
          />
          <input
            type="text"
            value={skillDesc}
            onChange={(e) => setSkillDesc(e.target.value)}
            placeholder={t('descriptionPlaceholder')}
            className={cn(
              'w-full px-2.5 py-1.5 rounded-lg text-sm',
              'bg-muted border border-border',
              'focus:outline-none focus:ring-1 focus:ring-primary',
            )}
          />
          <button
            type="button"
            onClick={handleGenerateSkill}
            disabled={!skillName.trim() || isGenerating}
            className={cn(
              'w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium',
              'bg-primary text-primary-foreground hover:bg-primary/90',
              'disabled:opacity-50 disabled:cursor-not-allowed',
            )}
          >
            <Sparkles size={14} />
            {isGenerating ? t('generating') : t('generateSkill')}
          </button>
        </div>
      )}

      {/* Generated Skill Result */}
      {generatedSkill && (
        <div className="px-3 py-3 border-t border-border space-y-2">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={16} className="text-chart-2" />
            <span className="text-sm font-medium text-chart-2">{t('skillGenerated')}</span>
          </div>
          <div className="text-xs text-muted-foreground space-y-1">
            <p>
              <span className="font-medium">{t('labelName')}</span> {generatedSkill.skillName}
            </p>
            <p>
              <span className="font-medium">{t('labelSteps')}</span> {generatedSkill.stepCount}
            </p>
            {generatedSkill.credentialPlaceholders.length > 0 && (
              <p className="text-yellow-600">
                {t('credentialDetected', { count: generatedSkill.credentialPlaceholders.length })}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default React.memo(BrowserRecordingPanel);
