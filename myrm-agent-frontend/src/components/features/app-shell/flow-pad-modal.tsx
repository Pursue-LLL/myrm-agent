'use client';

/**
 * [INPUT]
 * - useFlowPadStore (POS: FlowPad 全局状态)
 * - useChatStore (POS: 消息发送)
 * - useFeatureGateStore (POS: Feature Gate 检查)
 *
 * [OUTPUT]
 * - FlowPadModal: 全局居中 Dialog，整合截图预览 + 语音/文本输入
 *
 * [POS]
 * Omni-FlowPad 核心 UI 组件。全局居中 Dialog，
 * 同时服务 Appshot 截屏、语音输入、deep link Quick Ask 和 Inline Input 场景。
 * Inline Mode 下 AI 结果局部流式显示，支持一键 Paste 回写原应用。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { Dialog, DialogContent, DialogTitle } from '@/components/primitives/dialog';
import { useFlowPadStore } from '@/store/useFlowPadStore';
import useChatStore from '@/store/useChatStore';
import { useTranslations } from 'next-intl';
import { toast } from '@/lib/utils/toast';
import { cn } from '@/lib/utils/classnameUtils';
import {
  Send,
  X,
  Monitor,
  MessageSquareReply,
  FileText,
  Languages,
  Lightbulb,
  ClipboardPaste,
  Copy,
  Loader2,
  TextSelect,
  ChevronDown,
  Check,
} from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import SpeechInputButton from '@/components/features/message-input-actions/SpeechInputButton';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import { AgentAvatar } from '@/components/agent/AgentAvatar';
import useAgentStore from '@/store/useAgentStore';
import { buildAgentConfig } from '@/lib/utils/agentConfigMapper';
import type { AgentConfig } from '@/store/chat/types';

import { formatAppshotMessage, CapturePreview, ImageLightbox } from './FlowPadModalParts';

interface InlineRouteSelection {
  id: string;
  name: string;
  avatarUrl?: string;
  config: AgentConfig;
}

function getAgentDisplayName(config: AgentConfig | null): string | null {
  if (!config) {
    return null;
  }
  if (typeof config.agentName === 'string' && config.agentName.trim()) {
    return config.agentName.trim();
  }
  const legacyName = (config as AgentConfig & { name?: string }).name;
  if (typeof legacyName === 'string' && legacyName.trim()) {
    return legacyName.trim();
  }
  return null;
}

function createFallbackRouteConfig(agentId: string): AgentConfig {
  return {
    agentId,
    selectedSkillIds: [],
    skillConfigs: {},
    selectedMcpNames: [],
    systemPrompt: '',
    useGlobalInstruction: true,
    autoRestoreDomains: [],
  };
}

export function FlowPadModal() {
  const t = useTranslations('flowPad');
  const {
    isOpen,
    mode,
    captures,
    initialText,
    inlineResult,
    inlineGenerating,
    close,
    removeCapture,
  } = useFlowPadStore();
  const { agentConfig, sendMessage, setFiles } = useChatStore();
  const availableAgents = useAgentStore((state) => state.agents);
  const fetchAgents = useAgentStore((state) => state.fetchAgents);
  const fetchAgent = useAgentStore((state) => state.fetchAgent);
  const agentListLoading = useAgentStore((state) => state.loading);

  const isVoiceEnabled = useFeatureGateStore((s) => s.isEnabled('voice_interaction'));

  const [text, setText] = useState('');
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [inlineRouteSelection, setInlineRouteSelection] = useState<InlineRouteSelection | null>(null);
  const [agentRouteMenuOpen, setAgentRouteMenuOpen] = useState(false);
  const [inlineRouteSwitching, setInlineRouteSwitching] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const agentRouteMenuRef = useRef<HTMLDivElement>(null);

  const currentAgentLabel = getAgentDisplayName(agentConfig) ?? t('defaultAgent');
  const currentAgentAvatar = agentConfig?.avatarUrl;
  const effectiveInlineRouteLabel = inlineRouteSelection?.name ?? currentAgentLabel;
  const effectiveInlineRouteAvatar = inlineRouteSelection?.avatarUrl ?? currentAgentAvatar;

  const autoResizeTextarea = useCallback(() => {
    const el = inputRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = el.scrollHeight + 'px';
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      setText(initialText);
      setLightboxSrc(null);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen, initialText]);

  useEffect(() => {
    autoResizeTextarea();
  }, [text, autoResizeTextarea]);

  useEffect(() => {
    if (!isOpen || mode !== 'inline') return;
    void fetchAgents(1, 100, true);
  }, [isOpen, mode, fetchAgents]);

  useEffect(() => {
    if (!inlineRouteSelection) return;
    const stillExists = availableAgents.some((agent) => agent.id === inlineRouteSelection.id);
    if (!stillExists) {
      setInlineRouteSelection(null);
    }
  }, [availableAgents, inlineRouteSelection]);

  useEffect(() => {
    if (!agentRouteMenuOpen) return;
    const onMouseDown = (event: MouseEvent) => {
      const target = event.target;
      if (target instanceof Node && !agentRouteMenuRef.current?.contains(target)) {
        setAgentRouteMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, [agentRouteMenuOpen]);

  // Inline Mode: bridge streaming messages to inlineResult
  useEffect(() => {
    if (mode !== 'inline' || !isOpen) return;

    const unsub = useChatStore.subscribe((state, prev) => {
      if (!state.loading && !prev.loading) return;

      const lastMsg = state.messages.findLast((m) => m.role === 'assistant');
      if (lastMsg?.content) {
        useFlowPadStore.setState({ inlineResult: lastMsg.content, inlineGenerating: state.loading });
      }
      if (prev.loading && !state.loading) {
        useFlowPadStore.setState({ inlineGenerating: false });
      }
    });

    return () => unsub();
  }, [mode, isOpen]);

  const attachScreenshots = useCallback(() => {
    const screenshotFiles = captures
      .filter((c) => c.screenshot)
      .map((c, idx) => ({
        fileName: `appshot_${idx + 1}.jpg`,
        fileExtension: 'jpg',
        fileUrl: `data:image/jpeg;base64,${c.screenshot}`,
        fileType: 'uploaded' as const,
      }));

    if (screenshotFiles.length > 0) {
      const currentFiles = useChatStore.getState().files;
      setFiles([...currentFiles, ...screenshotFiles]);
    }
  }, [captures, setFiles]);

  const handleSelectInlineRouteAgent = useCallback(
    async (agentId: string | null) => {
      setAgentRouteMenuOpen(false);
      if (agentId === null) {
        setInlineRouteSelection(null);
        return;
      }
      if (inlineRouteSelection?.id === agentId) {
        return;
      }

      setInlineRouteSwitching(true);
      try {
        const listItem = availableAgents.find((agent) => agent.id === agentId);
        const fullAgent = await fetchAgent(agentId);
        const nextName = listItem?.name ?? fullAgent?.name ?? agentId;
        const nextAvatar = listItem?.avatar_url ?? fullAgent?.avatar_url;
        const nextConfig = fullAgent ? buildAgentConfig(fullAgent) : createFallbackRouteConfig(agentId);
        setInlineRouteSelection({
          id: agentId,
          name: nextName,
          avatarUrl: nextAvatar,
          config: nextConfig,
        });
        toast.success(t('inlineRouteApplied', { agent: nextName }), { duration: 2000 });
      } catch (err) {
        console.error('FlowPad inline route switch failed:', err);
        toast.error(t('inlineRouteApplyFailed'), { duration: 3000 });
      } finally {
        setInlineRouteSwitching(false);
      }
    },
    [availableAgents, fetchAgent, inlineRouteSelection?.id, t],
  );

  const sendWithInlineRoute = useCallback(
    async (message: string) => {
      if (mode === 'inline' && inlineRouteSelection) {
        await sendMessage(message, undefined, undefined, undefined, undefined, inlineRouteSelection.config);
        return;
      }
      await sendMessage(message);
    },
    [mode, inlineRouteSelection, sendMessage],
  );

  const handleSubmit = useCallback(async () => {
    const hasCaptures = captures.length > 0;
    const hasText = text.trim().length > 0;

    if (!hasCaptures && !hasText) return;
    if (isSubmitting) return;

    setIsSubmitting(true);
    try {
      if (hasCaptures) {
        attachScreenshots();
      }

      const parts: string[] = [];
      if (hasCaptures) {
        parts.push(formatAppshotMessage(captures));
      }
      if (hasText) {
        parts.push(text.trim());
      }

      const message = parts.join('\n\n');
      if (message) {
        await sendWithInlineRoute(message);
      }

      if (mode === 'inline') {
        toast.success(t('inlineSubmitted'), { duration: 2000 });
      } else {
        const agentLabel = currentAgentLabel;
        toast.success(t('submitted', { agent: agentLabel }), { duration: 3000 });
        close();
      }
    } catch (err) {
      console.error('FlowPad submit failed:', err);
      toast.error(t('submitFailed'), { duration: 3000 });
    } finally {
      setIsSubmitting(false);
    }
  }, [captures, text, attachScreenshots, sendWithInlineRoute, close, currentAgentLabel, t, isSubmitting, mode]);

  const handleSpeechTranscript = useCallback(
    (transcript: string) => {
      setText((prev) => (prev ? `${prev} ${transcript}` : transcript));
      inputRef.current?.focus();
    },
    [],
  );

  const handleQuickAction = useCallback(
    async (promptKey: 'replyPrompt' | 'summarizePrompt' | 'translatePrompt' | 'explainPrompt') => {
      if (isSubmitting || captures.length === 0) return;

      setIsSubmitting(true);
      try {
        attachScreenshots();

        const prompt = t(promptKey);
        const message = `${formatAppshotMessage(captures)}\n\n${prompt}`;
        await sendWithInlineRoute(message);

        if (mode === 'inline') {
          toast.success(t('inlineSubmitted'), { duration: 2000 });
        } else {
          const agentLabel = currentAgentLabel;
          toast.success(t('submitted', { agent: agentLabel }), { duration: 3000 });
          close();
        }
      } catch (err) {
        console.error('FlowPad quick action failed:', err);
        toast.error(t('submitFailed'), { duration: 3000 });
      } finally {
        setIsSubmitting(false);
      }
    },
    [isSubmitting, captures, attachScreenshots, sendWithInlineRoute, close, currentAgentLabel, t, mode],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.nativeEvent.isComposing) return;

      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const handlePasteBack = useCallback(async () => {
    if (!inlineResult.trim()) return;

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
    if (!inlineResult.trim()) return;

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

          {/* Header */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-border/40 bg-muted/20">
            <div className="flex items-center gap-2">
              {mode === 'inline' ? (
                <ClipboardPaste className="w-3.5 h-3.5 text-blue-500" />
              ) : (
                <Monitor className="w-3.5 h-3.5 text-muted-foreground/70" />
              )}
              <span className="text-xs font-medium text-muted-foreground">
                {mode === 'inline'
                  ? t('inlineTitle')
                  : hasCaptures
                    ? t('titleWithCapture')
                    : t('title')}
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

          {/* Captures Preview */}
          {hasCaptures && (
            <div className="px-4 py-3 border-b border-border/30 bg-muted/10">
              <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-thin">
                {captures.map((capture, idx) => (
                  <CapturePreview
                    key={capture.timestamp + idx}
                    capture={capture}
                    collapseLabel={t('collapse')}
                    onRemove={() => removeCapture(idx)}
                    onImageClick={() =>
                      capture.screenshot && setLightboxSrc(`data:image/jpeg;base64,${capture.screenshot}`)
                    }
                  />
                ))}
              </div>
            </div>
          )}

          {/* Selected Text Chip */}
          {selectedTextPreview && (
            <div className="px-4 py-2 border-b border-border/30">
              <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-primary/8 border border-primary/15">
                <TextSelect className="w-3.5 h-3.5 text-primary shrink-0" />
                <span className="text-xs font-medium text-primary/80 truncate">
                  {selectedTextPreview.length > 80
                    ? `${selectedTextPreview.slice(0, 80)}...`
                    : selectedTextPreview}
                </span>
              </div>
            </div>
          )}

          {/* Agent route indicator / switcher */}
          <div className="px-4 py-1.5 border-b border-border/20 bg-muted/5">
            {mode === 'inline' ? (
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] text-muted-foreground/60">{t('sendTo')}</span>
                <div className="relative" ref={agentRouteMenuRef}>
                  <button
                    type="button"
                    data-testid="flowpad-inline-route-trigger"
                    disabled={isSubmitting || inlineRouteSwitching}
                    className="inline-flex max-w-[320px] items-center gap-2 rounded-md border border-border/60 px-2 py-1 text-xs text-foreground transition-colors hover:bg-accent/40 disabled:opacity-60"
                    onClick={() => setAgentRouteMenuOpen((open) => !open)}
                  >
                    <AgentAvatar
                      url={effectiveInlineRouteAvatar}
                      name={effectiveInlineRouteLabel}
                      agentId={inlineRouteSelection?.id ?? agentConfig?.agentId}
                      className="h-4 w-4"
                      size="sm"
                    />
                    <span className="truncate">{effectiveInlineRouteLabel}</span>
                    <span className="rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground">
                      {inlineRouteSelection ? t('inlineRouteProfile') : t('inlineRouteCurrent')}
                    </span>
                    {inlineRouteSwitching ? (
                      <Loader2 className="h-3 w-3 shrink-0 animate-spin text-muted-foreground" />
                    ) : (
                      <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
                    )}
                  </button>
                  {agentRouteMenuOpen && (
                    <div className="absolute right-0 top-[calc(100%+6px)] z-50 w-[300px] rounded-md border border-border/60 bg-background p-1 shadow-xl">
                      <div className="max-h-64 overflow-y-auto">
                        <button
                          type="button"
                          data-testid="flowpad-inline-route-follow-current"
                          className="flex w-full items-center justify-between rounded-sm px-2 py-1.5 text-left text-xs hover:bg-accent/50"
                          onClick={() => void handleSelectInlineRouteAgent(null)}
                        >
                          <span className="truncate">{t('inlineRouteFollowCurrent', { agent: currentAgentLabel })}</span>
                          {!inlineRouteSelection && <Check className="h-3.5 w-3.5 text-primary" />}
                        </button>
                        {agentListLoading ? (
                          <p className="px-2 py-2 text-[11px] text-muted-foreground">{t('inlineRouteLoadingAgents')}</p>
                        ) : availableAgents.length > 0 ? (
                          availableAgents.map((agent) => {
                            const selected = inlineRouteSelection?.id === agent.id;
                            return (
                              <button
                                key={agent.id}
                                type="button"
                                data-testid={`flowpad-inline-route-agent-${agent.id}`}
                                className="flex w-full items-center justify-between gap-2 rounded-sm px-2 py-1.5 text-left text-xs hover:bg-accent/50"
                                onClick={() => void handleSelectInlineRouteAgent(agent.id)}
                              >
                                <span className="flex min-w-0 items-center gap-2">
                                  <AgentAvatar
                                    url={agent.avatar_url}
                                    name={agent.name}
                                    agentId={agent.id}
                                    className="h-4 w-4"
                                    size="sm"
                                  />
                                  <span className="truncate">{agent.name}</span>
                                </span>
                                {selected && <Check className="h-3.5 w-3.5 text-primary" />}
                              </button>
                            );
                          })
                        ) : (
                          <p className="px-2 py-2 text-[11px] text-muted-foreground">{t('inlineRouteNoAgents')}</p>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <span className="text-[10px] text-muted-foreground/60">
                {t('sendTo')} <span className="font-medium text-muted-foreground">{currentAgentLabel}</span>
              </span>
            )}
          </div>

          {/* Quick Actions */}
          {hasCaptures && (
            <div className="px-4 py-2 border-b border-border/20 flex flex-wrap gap-1.5">
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => handleQuickAction('replyPrompt')}
                className="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-full border border-border/50 bg-background hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50 disabled:pointer-events-none"
              >
                <MessageSquareReply className="w-3 h-3" />
                {t('quickReply')}
              </button>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => handleQuickAction('summarizePrompt')}
                className="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-full border border-border/50 bg-background hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50 disabled:pointer-events-none"
              >
                <FileText className="w-3 h-3" />
                {t('quickSummarize')}
              </button>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => handleQuickAction('translatePrompt')}
                className="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-full border border-border/50 bg-background hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50 disabled:pointer-events-none"
              >
                <Languages className="w-3 h-3" />
                {t('quickTranslate')}
              </button>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => handleQuickAction('explainPrompt')}
                className="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-full border border-border/50 bg-background hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50 disabled:pointer-events-none"
              >
                <Lightbulb className="w-3 h-3" />
                {t('quickExplain')}
              </button>
            </div>
          )}

          {/* Inline Result Display */}
          {mode === 'inline' && inlineResult && (
            <div className="px-4 py-3 border-b border-border/30 bg-muted/5 max-h-[200px] overflow-y-auto">
              <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">
                {inlineResult}
              </p>
              {inlineGenerating && (
                <span className="inline-flex items-center gap-1 mt-1 text-xs text-muted-foreground">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  {t('generating')}
                </span>
              )}
            </div>
          )}

          {/* Inline Paste/Copy Actions */}
          {mode === 'inline' && inlineResult && !inlineGenerating && (
            <div className="px-4 py-2.5 border-b border-border/20 flex items-center gap-2">
              <Button
                size="sm"
                className="h-7 gap-1.5 text-xs"
                onClick={handlePasteBack}
              >
                <ClipboardPaste className="w-3 h-3" />
                {t('pasteBack')}
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-7 gap-1.5 text-xs"
                onClick={handleCopyResult}
              >
                <Copy className="w-3 h-3" />
                {t('copyResult')}
              </Button>
            </div>
          )}

          {/* Input */}
          <div className="p-4 relative">
            <textarea
              ref={inputRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                mode === 'inline'
                  ? t('inlinePlaceholder')
                  : hasCaptures
                    ? t('placeholderWithCapture')
                    : t('placeholder')
              }
              className={cn(
                'w-full resize-none border-0 focus:outline-none focus-visible:ring-0',
                'text-base bg-transparent placeholder:text-muted-foreground/40',
                'min-h-[80px] max-h-[200px]',
              )}
              rows={3}
            />
            <div className="flex items-center justify-end gap-2 mt-2">
              <span className="text-[10px] text-muted-foreground/40">
                Enter {t('toSend')} · Esc {t('toCancel')}
              </span>
              {isVoiceEnabled && (
                <SpeechInputButton
                  onTranscript={handleSpeechTranscript}
                  disabled={isSubmitting}
                />
              )}
              <Button
                size="icon"
                className="h-8 w-8 rounded-full"
                onClick={handleSubmit}
                disabled={isSubmitting || (!text.trim() && !hasCaptures)}
              >
                {isSubmitting ? (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {lightboxSrc && (
        <ImageLightbox src={lightboxSrc} alt="Appshot" onClose={() => setLightboxSrc(null)} />
      )}
    </>
  );
}
