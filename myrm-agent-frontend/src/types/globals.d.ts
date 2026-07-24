/**
 * 全局类型声明
 */

interface Window {
  SpeechRecognition?: typeof SpeechRecognition;
  webkitSpeechRecognition?: typeof SpeechRecognition;
  __MYRM_TRACE_ID__?: string;
  /** Chrome E2E SHPOIB: private backend API base injected before chat automation. */
  __MYRM_E2E_API_BASE__?: string;
  /** SHPOIB Chrome E2E: force POST agent-stream direct SSE (skip workspace multiplex). */
  __MYRM_E2E_DIRECT_SSE__?: boolean;
  /** Chrome E2E: block outbound ConfigSync for searchServices (gap toast tests). */
  __MYRM_E2E_BLOCK_SEARCH_SYNC__?: boolean;
  /** SHPOIB E2E: last attach fallback diagnostics from streamConsumer. */
  __MYRM_E2E_ATTACH_DIAG__?: {
    attached: boolean;
    queueLen: number;
    attempt?: number;
    error?: string;
  };
  /** Page-local private runtime identity parsed from window.name before hydration. */
  __MYRM_E2E_RUNTIME__?: Readonly<{
    version: 1;
    runId: string;
    runtimeId: string;
    apiBase: string;
    uiOrigin: string;
  }>;
  /** Rejects before any routed API fetch when the page is bound to the wrong Backend. */
  __MYRM_E2E_RUNTIME_READY__?: Promise<Readonly<{
    version: 1;
    runId: string;
    runtimeId: string;
    apiBase: string;
    uiOrigin: string;
  }>>;
  __TAURI_INTERNALS__?: unknown;
  /** Dev-only bridge for CDP Chrome E2E (AppLayout E2EChatBridge). */
  __MYRM_E2E_CHAT__?: {
    __e2eFallback: boolean;
    setInputMessage: (message: string) => void;
    sendChatMessage?: (
      text: string,
      opts?: {
        baselineUserCount?: number;
        waitForStreamCompletion?: boolean;
        preserveActionMode?: boolean;
      },
    ) => Promise<{ ok: boolean; err?: string; chatId?: string | null; mode?: string; debug?: Record<string, unknown> }>;
    handleSubmit: () => void | Promise<void>;
    getInputMessage: () => string;
    ensureProviders?: () => Promise<void>;
    prepareAutomationSend?: () => void;
    ensureChatSession?: (opts?: { preserveActionMode?: boolean }) => Promise<void>;
    attachToChat?: (chatId: string) => Promise<void>;
    resetChat?: () => void;
    isSendReady?: () => boolean;
    isProvidersInitialized?: () => boolean;
    debugProviderState?: () => Record<string, unknown>;
    clearStreamRequestMessageId?: () => void;
    /** CDP E2E: API-confirmed user message count before submit. */
    _submitBaselineUsers?: number;
    turnSnapshot: () => {
      chatId: string | null;
      userCount: number;
      isStreaming: boolean;
      hasOk: boolean;
      hasDone: boolean;
      lastAssistantSample: string;
    };
    lastSubmitResult?: { ok: boolean; err?: string; chatId?: string | null; debug?: Record<string, unknown> };
    setGoalMode: (enabled: boolean) => void;
    setGoalBudgetTokens: (tokens: number | null) => void;
    setGoalConvergenceWindow?: (window: number | null) => void;
    getGoalMode: () => boolean;
    getActiveGoalSnapshot?: () => {
      status: string;
      reason: string | null;
      objective: string;
    } | null;
    loadActiveGoalFromApi?: () => Promise<{
      ok: boolean;
      err?: string;
      status?: string;
      reason?: string | null;
    }>;
    getGoalDraftState?: () => {
      composerObjective: string;
      acceptanceCount: number;
      constraintsCount: number;
      draftButtonDisabled: boolean;
    };
    runGoalDraftFromComposer?: () => Promise<{
      ok: boolean;
      err?: string;
      acceptanceCount?: number;
      constraintsCount?: number;
    }>;
    dispatchSystemNotification?: (detail: Record<string, unknown>) => void;
    dispatchBackgroundJobFinishAndRefresh?: (chatId: string) => Promise<{
      ok: boolean;
      err?: string;
      status?: string | null;
      reason?: string | null;
    }>;
    setCurrentBuiltinTools?: (tools: string[]) => void;
    getCurrentBuiltinTools?: () => string[];
    /** CDP E2E: pin agent chat to defaultModelConfig.liteModel (matches API get_lite_model_selection). */
    pinLiteModelForE2e?: () => Promise<{ providerId: string; model: string }>;
    /** CDP E2E SHPOIB: mirror private-backend searchServices into useConfigStore. */
    syncSearchServicesFromE2eApi?: () => Promise<{ ok: boolean; err?: string; count?: number }>;
    /** CDP E2E: pin agent chat to defaultModelConfig.baseModel (matches API get_model_selection). */
    pinBasicModelForE2e?: () => Promise<{ providerId: string; model: string }>;
    /** CDP E2E: abort in-flight SSE so API agent-stream resume can proceed (no cancel API). */
    releaseActiveStreamForApiResume?: () => { ok: boolean; released: boolean };
    /** CDP E2E: resume active clarification with empty answer (Skip parity). */
    skipActiveClarificationForE2e?: () => { messageId: string };
    setBrowserSource?: (source: string) => void;
    getBrowserSource?: () => string | null | undefined;
    ensureComputerUseReady?: () => void;
    getActionMode?: () => string;
    setActionMode?: (mode: string) => void;
    getBrowserToolProgress?: () => {
      active: boolean;
      takeoverPending: boolean;
      takeoverUiMode: 'managed' | 'extension' | null;
      stepCount: number;
      lastTool: string;
    };
    getDesktopToolProgress?: () => {
      active: boolean;
      isStreaming?: boolean;
      pending: boolean;
      requestId: string;
      stepCount: number;
      lastTool: string;
    };
    getFirstDesktopDref?: () => string | null;
    getDesktopApprovalSnapshot?: () => {
      pending: boolean;
      requestId: string;
      reason: string;
      operation: string;
      appName: string;
      requireAppApproval: boolean;
    };
    syncDesktopControlApproval?: (payload: {
      request_id: string;
      reason: string;
      operation: string;
      app_name?: string;
      window_title?: string;
      require_app_approval?: boolean;
    }) => void;
    hideApprovalDrawer?: () => void;
    isApprovalDrawerOpen?: () => boolean;
    triggerBrowserTakeover?: (payload: {
      reason: string;
      ui_mode?: 'managed' | 'extension';
      auto_detect_completion?: boolean;
      messageId?: string;
      url?: string;
    }) => void;
    getBrowserTakeoverSnapshot?: () => {
      pending: boolean;
      uiMode: 'managed' | 'extension';
      autoDetectCompletion: boolean;
      reason: string;
    };
    dismissBrowserTakeover?: () => void;
  };
  /** Dev-only bridge for subagent dashboard Chrome E2E hydration. */
  __MYRM_E2E_SUBAGENT__?: {
    hydrate: (rows: Array<Record<string, unknown>>) => void;
    refresh: () => void | Promise<void>;
  };
}

declare class SpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;

  start(): void;
  stop(): void;
  abort(): void;

  onstart: ((this: SpeechRecognition, ev: Event) => unknown) | null;
  onend: ((this: SpeechRecognition, ev: Event) => unknown) | null;
  onerror: ((this: SpeechRecognition, ev: SpeechRecognitionErrorEvent) => unknown) | null;
  onresult: ((this: SpeechRecognition, ev: SpeechRecognitionEvent) => unknown) | null;
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
  message: string;
}

interface SpeechRecognitionEvent extends Event {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionResultList {
  length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionResult {
  length: number;
  isFinal: boolean;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
}

interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}

declare module '@novnc/novnc' {
  interface NoVncOptions {
    credentials?: {
      username?: string;
      password?: string;
      target?: string;
    };
  }

  export default class RFB extends EventTarget {
    constructor(target: HTMLElement, url: string, options?: NoVncOptions);
    scaleViewport: boolean;
    resizeSession: boolean;
    disconnect(): void;
  }
}
