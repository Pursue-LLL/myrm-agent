/**
 * [INPUT]
 * - vitest::vi (POS: 模块替身登记)
 * - ../VoiceSessionButton (POS: 被测组件)
 *
 * [OUTPUT]
 * - kit: 替身句柄：语音会话 hook、聊天 store、最近一次朗读的文本、浮层与气泡收到的属性
 * - VOICE_KEYS: 按钮读取的设置键（用户浏览器里已有的存档，属于契约）
 * - resetVoiceKit: 清空存储、语音会话回到空闲、聊天回到安静
 * - mockVoiceSession: 从下一次渲染起语音会话 hook 返回的状态
 * - enableVoice: 在设置里打开语音会话按钮，可顺带写入其他设置
 * - renderVoiceButton: 渲染按钮，附带 refresh（memo 组件需要新属性才会重新读取替身）
 * - voiceOptions: 按钮在最近一次渲染里交给语音会话 hook 的选项
 *
 * [POS]
 * VoiceSessionButton 行为测试的共享底座。必须先于 ../VoiceSessionButton 导入：vi.mock 在本模块求值时登记。
 * 语音会话 hook、聊天 store、浮层与气泡是边界，换成替身；设置存储、停止口令与发送消息的规则是真实的。
 */
import { cleanup, render } from '@testing-library/react';
import type { ComponentProps, ReactNode } from 'react';
import { vi } from 'vitest';
import type { useVoiceSession, VoiceSessionState } from '@/hooks/voice/useVoiceSession';
import { expectDefined } from '@/test-utils/expectDefined';
import VoiceSessionButton from '../VoiceSessionButton';

type VoiceSessionOptions = Parameters<typeof useVoiceSession>[0];
type OverlayProps = ComponentProps<typeof import('@/components/features/voice/VoiceSessionOverlay').default>;
type BubbleProps = ComponentProps<typeof import('@/components/features/voice/VoiceBubble').default>;

export interface VoiceSessionShape {
  sessionState: VoiceSessionState;
  isActive: boolean;
  interimText: string;
  audioLevel: number;
  agentResponseText: string;
  agentToolName: string;
}

interface VoiceSessionStub extends VoiceSessionShape {
  startSession: () => void;
  stopSession: () => void;
  interruptTTS: () => void;
  speakResponse: (text: string, options?: { queue?: boolean }) => void;
  liveNotes: { snapshot: null };
}

interface ChatMessage {
  messageId?: string;
  role: string;
  content: string;
}

const kit = vi.hoisted(() => ({
  t: (key: string) => key,
  voice: {
    startSession: vi.fn<() => void>(),
    stopSession: vi.fn<() => void>(),
    interruptTTS: vi.fn<() => void>(),
    speakResponse: vi.fn<(text: string, options?: { queue?: boolean }) => void>(),
  },
  chat: {
    chatId: 'chat-1' as string | null,
    messages: [] as ChatMessage[],
    loading: false,
    sendMessage: vi.fn<(text: string) => Promise<void>>(),
    setCameraFrames: vi.fn<(frames: string[]) => void>(),
    agentConfig: undefined as { agentId?: string } | undefined,
  },
  useVoiceSession: vi.fn<(options: VoiceSessionOptions) => VoiceSessionStub>(),
  lastSpokenText: vi.fn<() => string | null>(),
  overlayProps: null as OverlayProps | null,
  bubbleProps: null as BubbleProps | null,
}));
export { kit };

vi.mock('next-intl', () => ({ useTranslations: () => kit.t }));
vi.mock('@/hooks/voice/useVoiceSession', () => ({
  useVoiceSession: (options: VoiceSessionOptions) => kit.useVoiceSession(options),
}));
vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: typeof kit.chat) => unknown) => selector(kit.chat),
}));
vi.mock('@/components/features/voice/VoiceSessionOverlay', () => ({
  default: (props: OverlayProps) => {
    kit.overlayProps = props;
    return null;
  },
}));
vi.mock('@/components/features/voice/VoiceBubble', () => ({
  default: (props: BubbleProps) => {
    kit.bubbleProps = props;
    return null;
  },
}));
vi.mock('@/components/features/settings/Tooltip', () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/hooks/voice/useTTS', () => ({ getLastSpokenText: () => kit.lastSpokenText() }));

export const VOICE_KEYS = {
  enabled: 'voiceSessionEnabled',
  fullDuplex: 'voiceFullDuplexEnabled',
  agentBridge: 'voiceAgentBridgeEnabled',
  mode: 'voiceSessionMode',
} as const;

/** A session that is up and waiting to hear the user. */
export const LISTENING = { sessionState: 'listening', isActive: true } as const;

export function mockVoiceSession(shape: Partial<VoiceSessionShape> = {}): void {
  kit.useVoiceSession.mockReturnValue({
    sessionState: 'inactive',
    isActive: false,
    interimText: '',
    audioLevel: 0,
    agentResponseText: '',
    agentToolName: '',
    ...shape,
    ...kit.voice,
    liveNotes: { snapshot: null },
  });
}

export function resetVoiceKit(): void {
  cleanup();
  vi.clearAllMocks();
  localStorage.clear();
  Object.assign(kit.chat, { chatId: 'chat-1', messages: [], loading: false, agentConfig: undefined });
  kit.overlayProps = null;
  kit.bubbleProps = null;
  kit.lastSpokenText.mockReturnValue(null);
  mockVoiceSession();
}

export function enableVoice(settings: Partial<Record<keyof typeof VOICE_KEYS, string>> = {}): void {
  localStorage.setItem(VOICE_KEYS.enabled, 'true');
  for (const [name, value] of Object.entries(settings)) {
    localStorage.setItem(VOICE_KEYS[name as keyof typeof VOICE_KEYS], value);
  }
}

export function renderVoiceButton(props: ComponentProps<typeof VoiceSessionButton> = {}) {
  let generation = 0;
  // A fresh array each time: the button is memoised and only re-reads the doubles when its props change.
  const keyterms = () => (props.keyterms ? [...props.keyterms] : [`generation-${generation}`]);
  const view = render(<VoiceSessionButton {...props} keyterms={keyterms()} />);
  return {
    ...view,
    refresh: () => {
      generation += 1;
      view.rerender(<VoiceSessionButton {...props} keyterms={keyterms()} />);
    },
  };
}

export function voiceOptions(): VoiceSessionOptions {
  const options = kit.useVoiceSession.mock.lastCall?.[0];
  expectDefined(options, 'options given to useVoiceSession');
  return options;
}
