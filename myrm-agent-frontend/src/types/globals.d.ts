/**
 * 全局类型声明
 */

interface Window {
  SpeechRecognition?: typeof SpeechRecognition;
  webkitSpeechRecognition?: typeof SpeechRecognition;
  __MYRM_TRACE_ID__?: string;
  /** Chrome E2E SHPOIB: private backend API base injected before chat automation. */
  __MYRM_E2E_API_BASE__?: string;
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
    handleSubmit: () => void | Promise<void>;
    getInputMessage: () => string;
    ensureProviders?: () => Promise<void>;
    prepareAutomationSend?: () => void;
    ensureChatSession?: () => Promise<void>;
    attachToChat?: (chatId: string) => Promise<void>;
    resetChat?: () => void;
    isSendReady?: () => boolean;
    isProvidersInitialized?: () => boolean;
    debugProviderState?: () => Record<string, unknown>;
    turnSnapshot: () => {
      chatId: string | null;
      userCount: number;
      isStreaming: boolean;
      hasOk: boolean;
      lastAssistantSample: string;
    };
    lastSubmitResult?: { ok: boolean; err?: string; chatId?: string | null; debug?: Record<string, unknown> };
    setGoalMode: (enabled: boolean) => void;
    setGoalBudgetTokens: (tokens: number | null) => void;
    getGoalMode: () => boolean;
    setCurrentBuiltinTools?: (tools: string[]) => void;
    getCurrentBuiltinTools?: () => string[];
    getDesktopApprovalSnapshot?: () => {
      pending: boolean;
      requestId: string;
      reason: string;
      operation: string;
      appName: string;
      requireAppApproval: boolean;
    };
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
