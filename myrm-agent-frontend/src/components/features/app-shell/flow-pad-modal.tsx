'use client';

/**
 * [INPUT]
 * - useFlowPadStore (POS: FlowPad 全局状态)
 * - useChatStore (POS: 消息发送)
 * - useFeatureGateStore (POS: Feature Gate 检查)
 * - useAgentStore (POS: 可用 agent 列表与详情加载)
 * - getTemplates / instantiateTemplateWithMetrics (POS: 专家模板发现与召唤)
 *
 * [OUTPUT]
 * - FlowPadModal: 全局居中 Dialog，整合截图预览 + 语音/文本输入 + Inline 专家召唤
 *
 * [POS]
 * Omni-FlowPad 核心 UI 组件。全局居中 Dialog，
 * 同时服务 Appshot 截屏、语音输入、deep link Quick Ask 和 Inline Input 场景。
 * Inline Mode 下支持请求级路由切换、专家模板召唤与结果回写。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { Dialog, DialogContent, DialogTitle } from '@/components/primitives/dialog';
import { useFlowPadStore } from '@/store/useFlowPadStore';
import useChatStore from '@/store/useChatStore';
import { useLocale, useTranslations } from 'next-intl';
import { toast } from '@/lib/utils/toast';
import {
  X,
  Monitor,
  ClipboardPaste,
} from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import useAgentStore from '@/store/useAgentStore';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import { buildAgentConfig } from '@/lib/utils/agentConfigMapper';
import type { AgentConfig } from '@/store/chat/types';
import { getTemplates, type TemplateListItem } from '@/services/agent';
import {
  recordExpertSummonFirstMessageSent,
  recordExpertSummonRouteApplied,
  recordExpertSummonRouteApplyFailed,
  recordExpertSummonSearchUsed,
  recordExpertSummonSurfaceViewed,
} from '@/services/expertSummonMetrics';
import {
  normalizeTemplateSearchText,
  resolveTemplateKind,
  templateMatchesSearchQuery,
} from '@/services/templateDiscovery';
import { instantiateTemplateWithMetrics } from '@/services/templateSummon';

import { formatAppshotMessage, ImageLightbox } from './FlowPadModalParts';
import { FlowPadCapturesStrip } from './flow-pad-captures-strip';
import { FlowPadComposer } from './flow-pad-composer';
import { FlowPadInlineRouteSwitcher } from './flow-pad-inline-route-switcher';
import { FlowPadInlineResultPanel } from './flow-pad-inline-result-panel';
import { FlowPadQuickActions } from './flow-pad-quick-actions';
import { FlowPadSelectedTextChip } from './flow-pad-selected-text-chip';

interface InlineRouteSelection {
  id: string;
  name: string;
  avatarUrl?: string;
  config: AgentConfig;
}

interface SummonedRouteConversionState {
  agentId: string;
  trigger: 'template_card' | 'use_case_chip';
  templateKind: 'team' | 'individual';
  fromSearch: boolean;
  usedUseCase: boolean;
  firstMessageSent: boolean;
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
    sourcePid,
    inlineResult,
    inlineGenerating,
    close,
    removeCapture,
  } = useFlowPadStore();
  const { agentConfig, sendMessage, setFiles, getCurrentSessionMessageId } = useChatStore();
  const agents = useAgentStore((state) => state.agents);
  const fetchAgents = useAgentStore((state) => state.fetchAgents);
  const fetchAgent = useAgentStore((state) => state.fetchAgent);
  const agentListLoading = useAgentStore((state) => state.loading);

  const locale = useLocale();

  const availableAgents = useMemo(
    () =>
      agents.map((agent) => ({
        id: agent.id,
        name: getBuiltinAgentName(agent.id, agent.name, locale),
        avatar_url: agent.avatar_url,
      })),
    [agents, locale],
  );

  const isVoiceEnabled = useFeatureGateStore((s) => s.isEnabled('voice_interaction'));

  const [text, setText] = useState('');
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [inlineRouteSelection, setInlineRouteSelection] = useState<InlineRouteSelection | null>(null);
  const [agentRouteMenuOpen, setAgentRouteMenuOpen] = useState(false);
  const [inlineRouteSwitching, setInlineRouteSwitching] = useState(false);
  const [inlineRouteSwitchError, setInlineRouteSwitchError] = useState<string | null>(null);
  const [templateSearchQuery, setTemplateSearchQuery] = useState('');
  const [expertTemplates, setExpertTemplates] = useState<TemplateListItem[]>([]);
  const [expertTemplatesLoading, setExpertTemplatesLoading] = useState(false);
  const [expertTemplatesLoaded, setExpertTemplatesLoaded] = useState(false);
  const [expertTemplatesError, setExpertTemplatesError] = useState(false);
  const [instantiatingTemplateId, setInstantiatingTemplateId] = useState<string | null>(null);
  const inlineActiveRequestIdRef = useRef<string | null>(null);
  const inlineRouteSwitchNonceRef = useRef(0);
  const inlineRouteSwitchAbortRef = useRef<AbortController | null>(null);
  const hasReportedInlineTemplateSurfaceViewRef = useRef(false);
  const hasReportedInlineTemplateSearchRef = useRef(false);
  const summonedRouteRef = useRef<SummonedRouteConversionState | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const agentRouteMenuRef = useRef<HTMLDivElement>(null);

  const currentAgentLabel = useMemo(() => {
    const displayName = getAgentDisplayName(agentConfig);
    if (displayName === null) {
      return t('defaultAgent');
    }
    return agentConfig?.agentId
      ? getBuiltinAgentName(agentConfig.agentId, displayName, locale)
      : displayName;
  }, [agentConfig, locale, t]);
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
      inlineRouteSwitchAbortRef.current?.abort();
      inlineRouteSwitchAbortRef.current = null;
      inlineRouteSwitchNonceRef.current += 1;
      setText(initialText);
      setLightboxSrc(null);
      setInlineRouteSelection(null);
      setInlineRouteSwitchError(null);
      setInlineRouteSwitching(false);
      setAgentRouteMenuOpen(false);
      setTemplateSearchQuery('');
      setInstantiatingTemplateId(null);
      inlineActiveRequestIdRef.current = null;
      hasReportedInlineTemplateSurfaceViewRef.current = false;
      hasReportedInlineTemplateSearchRef.current = false;
      summonedRouteRef.current = null;
      setTimeout(() => inputRef.current?.focus(), 100);
    } else {
      inlineRouteSwitchAbortRef.current?.abort();
      inlineRouteSwitchAbortRef.current = null;
      inlineRouteSwitchNonceRef.current += 1;
      setAgentRouteMenuOpen(false);
      setTemplateSearchQuery('');
      setInstantiatingTemplateId(null);
      inlineActiveRequestIdRef.current = null;
      hasReportedInlineTemplateSurfaceViewRef.current = false;
      hasReportedInlineTemplateSearchRef.current = false;
      summonedRouteRef.current = null;
    }
  }, [isOpen, initialText, mode, sourcePid]);

  useEffect(() => {
    autoResizeTextarea();
  }, [text, autoResizeTextarea]);

  useEffect(() => {
    if (!isOpen || mode !== 'inline') {return;}
    void fetchAgents(1, 100, true);
  }, [isOpen, mode, fetchAgents]);

  useEffect(() => {
    if (!inlineRouteSelection) {return;}
    const stillExists = availableAgents.some((agent) => agent.id === inlineRouteSelection.id);
    if (!stillExists) {
      setInlineRouteSelection(null);
      setInlineRouteSwitchError(null);
      summonedRouteRef.current = null;
    }
  }, [availableAgents, inlineRouteSelection]);

  useEffect(() => {
    if (!agentRouteMenuOpen) {return;}
    const onMouseDown = (event: MouseEvent) => {
      const target = event.target;
      if (target instanceof Node && !agentRouteMenuRef.current?.contains(target)) {
        setAgentRouteMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, [agentRouteMenuOpen]);

  const loadExpertTemplates = useCallback(async () => {
    setExpertTemplatesLoading(true);
    setExpertTemplatesError(false);
    try {
      const templates = await getTemplates();
      const teamTemplates = templates.filter((item) => item.agent_type === 'team');
      setExpertTemplates(teamTemplates);
      setExpertTemplatesLoaded(true);
    } catch (error) {
      console.error('FlowPad template list fetch failed:', error);
      setExpertTemplatesError(true);
    } finally {
      setExpertTemplatesLoading(false);
    }
  }, []);

  useEffect(() => {
    if (mode !== 'inline' || !agentRouteMenuOpen) {
      return;
    }
    if (expertTemplatesLoaded || expertTemplatesLoading) {
      return;
    }
    void loadExpertTemplates();
  }, [mode, agentRouteMenuOpen, expertTemplatesLoaded, expertTemplatesLoading, loadExpertTemplates]);

  useEffect(() => {
    if (mode !== 'inline' || !agentRouteMenuOpen || hasReportedInlineTemplateSurfaceViewRef.current) {
      return;
    }
    hasReportedInlineTemplateSurfaceViewRef.current = true;
    recordExpertSummonSurfaceViewed('flow_pad_inline', 'flowpad:inline');
  }, [mode, agentRouteMenuOpen]);

  useEffect(() => {
    if (mode !== 'inline' || !agentRouteMenuOpen || hasReportedInlineTemplateSearchRef.current) {
      return;
    }
    const normalizedQuery = normalizeTemplateSearchText(templateSearchQuery);
    if (!normalizedQuery) {
      return;
    }
    hasReportedInlineTemplateSearchRef.current = true;
    recordExpertSummonSearchUsed('flow_pad_inline', normalizedQuery.length, 'flowpad:inline');
  }, [mode, agentRouteMenuOpen, templateSearchQuery]);

  const filteredExpertTemplates = useMemo(() => {
    return expertTemplates.filter((template) => templateMatchesSearchQuery(template, templateSearchQuery));
  }, [expertTemplates, templateSearchQuery]);

  // Inline Mode: bridge streaming messages to inlineResult
  useEffect(() => {
    if (mode !== 'inline' || !isOpen) {return;}

    const unsub = useChatStore.subscribe((state, prev) => {
      if (!state.loading && !prev.loading) {return;}

      const inlineRequestId = inlineActiveRequestIdRef.current;
      if (!inlineRequestId) {
        if (prev.loading && !state.loading) {
          useFlowPadStore.setState({ inlineGenerating: false });
        }
        return;
      }

      const lastMsg = state.messages.findLast(
        (m) => m.role === 'assistant' && m.messageId === inlineRequestId,
      );
      if (lastMsg?.content) {
        useFlowPadStore.setState({ inlineResult: lastMsg.content, inlineGenerating: state.loading });
      }
      if (prev.loading && !state.loading) {
        if (inlineRequestId) {
          inlineActiveRequestIdRef.current = null;
        }
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
    async (
      agentId: string | null,
      options?: { fromTemplate?: boolean },
    ): Promise<boolean> => {
      setAgentRouteMenuOpen(false);
      if (agentId === null) {
        inlineRouteSwitchAbortRef.current?.abort();
        inlineRouteSwitchAbortRef.current = null;
        inlineRouteSwitchNonceRef.current += 1;
        setInlineRouteSelection(null);
        setInlineRouteSwitchError(null);
        setInlineRouteSwitching(false);
        summonedRouteRef.current = null;
        return true;
      }
      if (!options?.fromTemplate) {
        summonedRouteRef.current = null;
      }
      if (inlineRouteSelection?.id === agentId) {
        return true;
      }

      const switchNonce = inlineRouteSwitchNonceRef.current + 1;
      inlineRouteSwitchNonceRef.current = switchNonce;
      inlineRouteSwitchAbortRef.current?.abort();
      const abortController = new AbortController();
      inlineRouteSwitchAbortRef.current = abortController;
      setInlineRouteSwitchError(null);
      setInlineRouteSwitching(true);
      try {
        const listItem = availableAgents.find((agent) => agent.id === agentId);
        const fullAgent = await fetchAgent(agentId, abortController.signal);
        if (abortController.signal.aborted) {
          return false;
        }
        if (!fullAgent) {
          throw new Error('Failed to load target agent profile');
        }
        if (inlineRouteSwitchNonceRef.current !== switchNonce) {
          return false;
        }
        const nextName = getBuiltinAgentName(
          agentId,
          listItem?.name ?? fullAgent?.name ?? agentId,
          locale,
        );
        const nextAvatar = listItem?.avatar_url ?? fullAgent?.avatar_url;
        const nextConfig = fullAgent ? buildAgentConfig(fullAgent) : createFallbackRouteConfig(agentId);
        setInlineRouteSelection({
          id: agentId,
          name: nextName,
          avatarUrl: nextAvatar,
          config: nextConfig,
        });
        setInlineRouteSwitchError(null);
        toast.success(t('inlineRouteApplied', { agent: nextName }), { duration: 2000 });
        return true;
      } catch (err) {
        if (abortController.signal.aborted) {
          return false;
        }
        if (inlineRouteSwitchNonceRef.current !== switchNonce) {
          return false;
        }
        console.error('FlowPad inline route switch failed:', err);
        const failedName = getBuiltinAgentName(
          agentId,
          availableAgents.find((agent) => agent.id === agentId)?.name ?? agentId,
          locale,
        );
        // Fail-safe to current session route to avoid accidentally sending with stale override.
        setInlineRouteSelection(null);
        setInlineRouteSwitchError(failedName);
        toast.error(t('inlineRouteApplyFailed'), { duration: 3000 });
        return false;
      } finally {
        if (inlineRouteSwitchAbortRef.current === abortController) {
          inlineRouteSwitchAbortRef.current = null;
        }
        if (inlineRouteSwitchNonceRef.current === switchNonce) {
          setInlineRouteSwitching(false);
        }
      }
    },
    [availableAgents, fetchAgent, inlineRouteSelection?.id, locale, t],
  );

  const handleFallbackToCurrentRoute = useCallback(() => {
    setInlineRouteSelection(null);
    setInlineRouteSwitchError(null);
    summonedRouteRef.current = null;
    toast.success(t('inlineRouteFallbackApplied'), { duration: 2000 });
  }, [t]);

  const handleInstantiateExpertTemplate = useCallback(
    async (template: TemplateListItem, starterPrompt?: string) => {
      if (instantiatingTemplateId || inlineRouteSwitching || isSubmitting) {
        return;
      }
      const normalizedStarterPrompt = starterPrompt?.trim() ?? '';
      const fromSearch = normalizeTemplateSearchText(templateSearchQuery).length > 0;
      const usedUseCase = normalizedStarterPrompt.length > 0;
      const trigger = usedUseCase ? 'use_case_chip' : 'template_card';
      const templateKind = resolveTemplateKind(template.agent_type);
      if (normalizedStarterPrompt) {
        // Preserve existing draft to avoid overriding in-progress user edits.
        setText((prev) => (prev.trim() ? prev : normalizedStarterPrompt));
      }
      setInstantiatingTemplateId(template.id);
      setInlineRouteSwitchError(null);
      try {
        const newAgent = await instantiateTemplateWithMetrics({
          templateId: template.id,
          surface: 'flow_pad_inline',
          trigger,
          templateKind,
          fromSearch,
          usedUseCase,
          contextKey: 'flowpad:inline',
        });
        try {
          await fetchAgents(1, 100, true);
        } catch (refreshError) {
          console.error('FlowPad agent list refresh failed after template instantiate:', refreshError);
        }
        const routeApplied = await handleSelectInlineRouteAgent(newAgent.id, { fromTemplate: true });
        if (routeApplied) {
          recordExpertSummonRouteApplied('flow_pad_inline', trigger, {
            contextKey: 'flowpad:inline',
            templateKind,
            fromSearch,
            usedUseCase,
          });
          summonedRouteRef.current = {
            agentId: newAgent.id,
            trigger,
            templateKind,
            fromSearch,
            usedUseCase,
            firstMessageSent: false,
          };
        } else {
          recordExpertSummonRouteApplyFailed('flow_pad_inline', trigger, {
            contextKey: 'flowpad:inline',
            templateKind,
            fromSearch,
            usedUseCase,
          });
          summonedRouteRef.current = null;
        }
      } catch (error) {
        console.error('FlowPad expert template instantiate failed:', error);
        toast.error(t('inlineRouteTemplateApplyFailed'), { duration: 3000 });
      } finally {
        setInstantiatingTemplateId(null);
      }
    },
    [
      instantiatingTemplateId,
      inlineRouteSwitching,
      isSubmitting,
      templateSearchQuery,
      fetchAgents,
      handleSelectInlineRouteAgent,
      t,
    ],
  );

  const sendWithInlineRoute = useCallback(
    async (message: string) => {
      try {
        if (mode !== 'inline') {
          await sendMessage(message);
          return;
        }

        const inlineRequestId = getCurrentSessionMessageId();
        inlineActiveRequestIdRef.current = inlineRequestId;
        useFlowPadStore.setState({ inlineResult: '', inlineGenerating: true });

        if (inlineRouteSelection) {
          const summoned = summonedRouteRef.current;
          if (summoned && !summoned.firstMessageSent && summoned.agentId === inlineRouteSelection.id) {
            summoned.firstMessageSent = true;
            recordExpertSummonFirstMessageSent('flow_pad_inline', summoned.trigger, {
              contextKey: 'flowpad:inline',
              templateKind: summoned.templateKind,
              fromSearch: summoned.fromSearch,
              usedUseCase: summoned.usedUseCase,
            });
          }
          await sendMessage(
            message,
            inlineRequestId,
            undefined,
            undefined,
            undefined,
            inlineRouteSelection.config,
          );
          return;
        }
        await sendMessage(message, inlineRequestId);
      } catch (error) {
        if (mode === 'inline') {
          inlineActiveRequestIdRef.current = null;
          useFlowPadStore.setState({ inlineGenerating: false });
        }
        throw error;
      }
    },
    [mode, inlineRouteSelection, sendMessage, getCurrentSessionMessageId],
  );

  const handleSubmit = useCallback(async () => {
    const hasCaptures = captures.length > 0;
    const hasText = text.trim().length > 0;

    if (!hasCaptures && !hasText) {return;}
    if (isSubmitting) {return;}
    if (inlineRouteSwitching) {
      toast.warning(t('inlineRouteSwitchingBlocked'), { duration: 2000 });
      return;
    }

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
  }, [
    captures,
    text,
    attachScreenshots,
    sendWithInlineRoute,
    close,
    currentAgentLabel,
    t,
    isSubmitting,
    inlineRouteSwitching,
    mode,
  ]);

  const handleSpeechTranscript = useCallback(
    (transcript: string) => {
      setText((prev) => (prev ? `${prev} ${transcript}` : transcript));
      inputRef.current?.focus();
    },
    [],
  );

  const handleQuickAction = useCallback(
    async (promptKey: 'replyPrompt' | 'summarizePrompt' | 'translatePrompt' | 'explainPrompt') => {
      if (isSubmitting || captures.length === 0) {return;}
      if (inlineRouteSwitching) {
        toast.warning(t('inlineRouteSwitchingBlocked'), { duration: 2000 });
        return;
      }

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
    [
      isSubmitting,
      captures,
      attachScreenshots,
      sendWithInlineRoute,
      close,
      currentAgentLabel,
      t,
      inlineRouteSwitching,
      mode,
    ],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.nativeEvent.isComposing) {return;}

      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const handlePasteBack = useCallback(async () => {
    if (!inlineResult.trim()) {return;}

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
    if (!inlineResult.trim()) {return;}

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

          {hasCaptures && (
            <FlowPadCapturesStrip
              captures={captures}
              collapseLabel={t('collapse')}
              onRemoveCapture={removeCapture}
              onOpenLightbox={setLightboxSrc}
            />
          )}

          {selectedTextPreview && (
            <FlowPadSelectedTextChip selectedText={selectedTextPreview} />
          )}

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
              onSelectInlineRouteAgent={handleSelectInlineRouteAgent}
              onFallbackToCurrentRoute={handleFallbackToCurrentRoute}
              onLoadExpertTemplates={loadExpertTemplates}
              onInstantiateExpertTemplate={handleInstantiateExpertTemplate}
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

      {lightboxSrc && (
        <ImageLightbox src={lightboxSrc} alt="Appshot" onClose={() => setLightboxSrc(null)} />
      )}
    </>
  );
}
