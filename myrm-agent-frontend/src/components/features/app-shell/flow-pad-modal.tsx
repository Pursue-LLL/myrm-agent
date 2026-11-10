'use client';

/**
 * [INPUT]
 * - useFlowPadStore (POS: FlowPad 全局状态)
 * - useChatStore (POS: 当前会话 agent 路由)
 * - useFeatureGateStore (POS: Feature Gate 检查)
 * - useFlowPadInlineRoute / useFlowPadExpertTemplates / useFlowPadSend (POS: Inline 路由、专家召唤、发送三层)
 * - useFlowPadDraft (POS: 输入草稿与截图放大图，随会话重置)
 *
 * [OUTPUT]
 * - FlowPadModal: 全局居中 Dialog，整合截图预览 + 语音/文本输入 + Inline 专家召唤
 *
 * [POS]
 * Omni-FlowPad 核心 UI 组件。全局居中 Dialog，
 * 同时服务 Appshot 截屏、语音输入、deep link Quick Ask 和 Inline Input 场景。
 * 负责面板生命周期（开合时重置各层状态）、输入草稿与结果回写；路由/召唤/发送逻辑在各自 hook 中。
 */

import { useCallback, useEffect, useRef } from 'react';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { Dialog, DialogContent, DialogTitle } from '@/components/primitives/dialog';
import { useFlowPadStore } from '@/store/useFlowPadStore';
import useChatStore from '@/store/useChatStore';
import { useTranslations } from 'next-intl';
import { toast } from '@/lib/utils/toast';
import { isImeComposing } from '@/lib/utils/imeUtils';
import { X, Monitor, ClipboardPaste } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';

import { ImageLightbox } from './FlowPadModalParts';
import { FlowPadCapturesStrip } from './flow-pad-captures-strip';
import { FlowPadComposer } from './flow-pad-composer';
import { FlowPadInlineRouteSwitcher } from './flow-pad-inline-route-switcher';
import { FlowPadInlineResultPanel } from './flow-pad-inline-result-panel';
import { FlowPadQuickActions } from './flow-pad-quick-actions';
import { FlowPadSelectedTextChip } from './flow-pad-selected-text-chip';
import { useFlowPadDraft } from './useFlowPadDraft';
import { useFlowPadExpertTemplates } from './useFlowPadExpertTemplates';
import { useFlowPadInlineRoute } from './useFlowPadInlineRoute';
import { useFlowPadSend } from './useFlowPadSend';
import { useFlowPadSummonAttribution } from './useFlowPadSummonAttribution';

export function FlowPadModal() {
  const t = useTranslations('flowPad');
  const { isOpen, mode, captures, initialText, sourcePid, inlineResult, inlineGenerating, close, removeCapture } =
    useFlowPadStore();
  const agentConfig = useChatStore((state) => state.agentConfig);
  const isVoiceEnabled = useFeatureGateStore((s) => s.isEnabled('voice_interaction'));

  const { text, setText, lightboxSrc, setLightboxSrc } = useFlowPadDraft({ isOpen, mode, sourcePid, initialText });
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const {
    begin: beginSummon,
    clear: clearSummon,
    reportFirstMessage: reportSummonFirstMessage,
  } = useFlowPadSummonAttribution();
  const {
    inlineRouteSelection,
    inlineRouteSwitching,
    inlineRouteSwitchError,
    agentRouteMenuOpen,
    setAgentRouteMenuOpen,
    agentRouteMenuRef,
    agentListLoading,
    availableAgents,
    currentAgentLabel,
    effectiveInlineRouteLabel,
    effectiveInlineRouteAvatar,
    selectRouteAgent,
    dismissRouteSwitchError,
    fallbackToCurrentRoute,
    resetRoute,
  } = useFlowPadInlineRoute({ isOpen, mode, agentConfig, clearSummon });
  const { isSubmitting, handleSubmit, handleQuickAction, resetInlineRequest } = useFlowPadSend({
    isOpen,
    mode,
    captures,
    text,
    close,
    currentAgentLabel,
    inlineRouteSelection,
    inlineRouteSwitching,
    reportSummonFirstMessage,
  });
  const {
    templateSearchQuery,
    setTemplateSearchQuery,
    expertTemplatesLoading,
    expertTemplatesError,
    filteredExpertTemplates,
    instantiatingTemplateId,
    retryExpertTemplates,
    instantiateExpertTemplate,
    resetTemplates,
  } = useFlowPadExpertTemplates({
    mode,
    agentRouteMenuOpen,
    inlineRouteSwitching,
    isSubmitting,
    selectRouteAgent,
    dismissRouteSwitchError,
    beginSummon,
    setText,
  });

  const autoResizeTextarea = useCallback(() => {
    const el = inputRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = el.scrollHeight + 'px';
    }
  }, []);

  // Every open, close, new capture or mode change starts a fresh pad session: no route, template or request state
  // carries over (the draft resets itself in useFlowPadDraft).
  useEffect(() => {
    resetRoute();
    resetTemplates();
    resetInlineRequest();
  }, [isOpen, initialText, mode, sourcePid, resetRoute, resetTemplates, resetInlineRequest]);

  // Puts the cursor in the draft box whenever a session has opened.
  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const focusTimer = setTimeout(() => inputRef.current?.focus(), 100);
    return () => clearTimeout(focusTimer);
  }, [isOpen, initialText, mode, sourcePid]);

  useEffect(() => {
    autoResizeTextarea();
  }, [text, autoResizeTextarea]);

  const handleSpeechTranscript = useCallback(
    (transcript: string) => {
      setText((prev) => (prev ? `${prev} ${transcript}` : transcript));
      inputRef.current?.focus();
    },
    [setText],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (isImeComposing(e)) {
        return;
      }

      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const handlePasteBack = useCallback(async () => {
    if (!inlineResult.trim()) {
      return;
    }

    try {
      const { invoke } = await import('@tauri-apps/api/core');
      await invoke('inline_paste_back', { content: inlineResult });
      toast.success(t('pastedBack'), { duration: 2000 });
      close();
      if (isTauriRuntime()) {
        const { getCurrentWindow } = await import('@tauri-apps/api/window');
        await getCurrentWindow().hide();
      }
    } catch (err) {
      console.error('Paste back failed:', err);
      toast.error(t('pasteBackFailed'), { duration: 3000 });
    }
  }, [inlineResult, close, t]);

  const handleCopyResult = useCallback(async () => {
    if (!inlineResult.trim()) {
      return;
    }

    try {
      await navigator.clipboard.writeText(inlineResult);
      toast.success(t('copied'), { duration: 2000 });
    } catch {
      toast.error(t('copyFailed'), { duration: 3000 });
    }
  }, [inlineResult, t]);

  const hasCaptures = captures.length > 0;
  const selectedTextPreview = captures.find((c) => c.selectedText?.trim())?.selectedText?.trim();

  return (
    <>
      <Dialog open={isOpen} onOpenChange={(open) => !open && close()}>
        <DialogContent className="sm:max-w-[640px] p-0 overflow-hidden bg-background/90 backdrop-blur-xl border-border/50 shadow-2xl gap-0 [&>button.absolute]:hidden">
          <VisuallyHidden>
            <DialogTitle>{mode === 'inline' ? t('inlineTitle') : t('title')}</DialogTitle>
          </VisuallyHidden>

          <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/40 bg-muted/20">
            <div className="flex items-center gap-2">
              {mode === 'inline' ? (
                <ClipboardPaste className="w-3.5 h-3.5 text-blue-500" />
              ) : (
                <Monitor className="w-3.5 h-3.5 text-muted-foreground/70" />
              )}
              <span className="text-xs font-medium text-muted-foreground">
                {mode === 'inline' ? t('inlineTitle') : hasCaptures ? t('titleWithCapture') : t('title')}
              </span>
              {mode === 'inline' && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-600 font-medium">
                  Inline
                </span>
              )}
            </div>
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={close}>
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>

          {hasCaptures && (
            <FlowPadCapturesStrip
              captures={captures}
              collapseLabel={t('collapse')}
              onRemoveCapture={removeCapture}
              onOpenLightbox={setLightboxSrc}
            />
          )}

          {selectedTextPreview && <FlowPadSelectedTextChip selectedText={selectedTextPreview} />}

          <div className="px-4 py-1.5 border-b border-border/20 bg-muted/5">
            <FlowPadInlineRouteSwitcher
              isInlineMode={mode === 'inline'}
              isSubmitting={isSubmitting}
              inlineRouteSwitching={inlineRouteSwitching}
              inlineRouteSwitchError={inlineRouteSwitchError}
              currentAgentLabel={currentAgentLabel}
              currentAgentId={agentConfig?.agentId}
              effectiveInlineRouteLabel={effectiveInlineRouteLabel}
              effectiveInlineRouteAvatar={effectiveInlineRouteAvatar}
              inlineRouteSelection={inlineRouteSelection}
              agentRouteMenuOpen={agentRouteMenuOpen}
              setAgentRouteMenuOpen={setAgentRouteMenuOpen}
              agentRouteMenuRef={agentRouteMenuRef}
              agentListLoading={agentListLoading}
              availableAgents={availableAgents}
              templateSearchQuery={templateSearchQuery}
              setTemplateSearchQuery={setTemplateSearchQuery}
              expertTemplatesLoading={expertTemplatesLoading}
              expertTemplatesError={expertTemplatesError}
              filteredExpertTemplates={filteredExpertTemplates}
              instantiatingTemplateId={instantiatingTemplateId}
              onSelectInlineRouteAgent={selectRouteAgent}
              onFallbackToCurrentRoute={fallbackToCurrentRoute}
              onRetryExpertTemplates={retryExpertTemplates}
              onInstantiateExpertTemplate={instantiateExpertTemplate}
              t={t}
            />
          </div>

          {hasCaptures && (
            <FlowPadQuickActions
              disabled={isSubmitting || inlineRouteSwitching}
              onQuickAction={(key) => {
                void handleQuickAction(key);
              }}
              t={t}
            />
          )}

          <FlowPadInlineResultPanel
            mode={mode}
            inlineResult={inlineResult}
            inlineGenerating={inlineGenerating}
            onPasteBack={() => {
              void handlePasteBack();
            }}
            onCopyResult={() => {
              void handleCopyResult();
            }}
            t={t}
          />

          <FlowPadComposer
            mode={mode}
            hasCaptures={hasCaptures}
            text={text}
            isSubmitting={isSubmitting}
            inlineRouteSwitching={inlineRouteSwitching}
            isVoiceEnabled={isVoiceEnabled}
            inputRef={inputRef}
            onTextChange={setText}
            onKeyDown={handleKeyDown}
            onSpeechTranscript={handleSpeechTranscript}
            onSubmit={handleSubmit}
            t={t}
          />
        </DialogContent>
      </Dialog>

      {lightboxSrc && <ImageLightbox src={lightboxSrc} alt={t('appshotAlt')} onClose={() => setLightboxSrc(null)} />}
    </>
  );
}
