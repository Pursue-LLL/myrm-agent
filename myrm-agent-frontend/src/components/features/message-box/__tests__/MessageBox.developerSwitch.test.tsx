'use client';

/**
 * 开发者模式开关的写端（设置页）与读端（聊天里的 system 行）共用同一个存储键和同一个通知事件：
 * 设置页一拨动，已经渲染出来的 system 行就跟着显示或隐藏。
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import MessageBox from '@/components/features/message-box/MessageBox';
import DeveloperSection from '@/components/features/settings/sections/system/DeveloperSection';
import type { Message } from '@/store/chat/types';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('next/dynamic', () => ({ default: () => () => null }));
vi.mock('@/components/features/settings/sections/ai-core/EvaluationSection', () => ({ EvaluationSection: () => null }));
vi.mock('@/components/features/settings/sections/system/SystemHealthPanel', () => ({ default: () => null }));
vi.mock('@/components/features/settings/sections/system/TelemetryPostureCard', () => ({ default: () => null }));

vi.mock('@/store/useChatStore', () => ({
  default: Object.assign(
    (selector: (state: Record<string, unknown>) => unknown) =>
      selector({ chatId: 'chat-dev', messages: [], sendMessage: vi.fn() }),
    { getState: () => ({ chatId: 'chat-dev', messages: [], sendMessage: vi.fn() }), setState: vi.fn() },
  ),
}));
vi.mock('@/store/useConfigStore', () => ({
  default: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({ enableEvalLab: false, reasoningDisplayMode: 'collapsed', personalSettings: {} }),
}));
vi.mock('@/components/features/message-box/MarkdownContent', () => ({
  default: ({ content }: { content: string }) => <div>{content}</div>,
}));
vi.mock('@/components/features/message-box/progress-steps/ProgressSteps', () => ({ default: () => null }));
vi.mock('@/components/features/message-box/ConsensusThinkingPanel', () => ({ default: () => null }));
vi.mock('@/components/features/chat-window/approval/VisualApprovalInlineSection', () => ({ default: () => null }));
vi.mock('@/components/features/artifacts/ArtifactsDisplay', () => ({ default: () => null }));
vi.mock('@/components/features/artifacts/ArtifactErrorBoundary', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('@/components/features/message-box/MessageActionBar', () => ({ default: () => null }));
vi.mock('@/store/chat/goals/usePlanStore', () => ({
  usePlanStore: { getState: () => ({ fetchPlan: vi.fn() }) },
}));
vi.mock('@/components/features/message-box/Suggestions', () => ({ default: () => null }));
vi.mock('@/components/features/message-box/QuoteToolbar', () => ({
  QuoteToolbar: () => null,
  useQuoteSelection: () => ({ state: null, dismiss: vi.fn() }),
}));
vi.mock('@/components/features/message-box/MemoryInsightPanel', () => ({ default: () => null }));
vi.mock('@/components/features/message-box/McpAppSection', () => ({ McpAppSection: () => null }));
vi.mock('@/services/chat', () => ({
  regenerateLastTurn: vi.fn(),
  cancelAgentRequest: vi.fn(),
  truncateAfterMessage: vi.fn(),
}));

const SYSTEM_PROMPT: Message = {
  messageId: 's1',
  chatId: 'chat-dev',
  role: 'system',
  content: 'content of s1',
  createdAt: new Date('2026-10-13T00:00:00.000Z'),
};

function renderSettingsBesideChat() {
  return render(
    <>
      <DeveloperSection />
      <MessageBox message={SYSTEM_PROMPT} messageIndex={0} loading={false} isLast={false} />
    </>,
  );
}

describe('developer-mode switch across the settings page and the chat', () => {
  afterEach(() => {
    localStorage.removeItem('developer_show_system_messages');
  });

  it('reveals and hides the rendered system row as the settings switch is toggled', () => {
    renderSettingsBesideChat();
    expect(screen.queryByText('systemPromptDeveloperMode')).toBeNull();

    fireEvent.click(screen.getByRole('switch'));
    expect(screen.getByText('systemPromptDeveloperMode')).toBeTruthy();

    fireEvent.click(screen.getByRole('switch'));
    expect(screen.queryByText('systemPromptDeveloperMode')).toBeNull();
  });

  it('keeps the row visible after a reload while the switch was left on', () => {
    localStorage.setItem('developer_show_system_messages', 'true');

    renderSettingsBesideChat();

    expect(screen.getByText('systemPromptDeveloperMode')).toBeTruthy();
    expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('true');
  });
});
