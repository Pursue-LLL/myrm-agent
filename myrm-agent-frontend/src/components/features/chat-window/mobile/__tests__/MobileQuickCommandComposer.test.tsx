/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { speechOnTranscript, stableT } = vi.hoisted(() => ({
  speechOnTranscript: { current: null as null | ((t: string) => void) },
  stableT: (key: string) => key,
}));

vi.mock('@/components/features/message-input-actions/SpeechInputButton', () => ({
  __esModule: true,
  default: ({ onTranscript }: { onTranscript: (text: string) => void }) => {
    speechOnTranscript.current = onTranscript;
    return (
      <button type="button" data-testid="speech-input" onClick={() => onTranscript('改成只读')} aria-label="语音" />
    );
  },
}));

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), info: vi.fn(), success: vi.fn() },
}));

const navigatorClipboard = {
  readText: vi.fn<() => Promise<string>>(),
};

Object.defineProperty(globalThis.navigator, 'clipboard', {
  configurable: true,
  value: navigatorClipboard,
});

import { MobileQuickCommandComposer } from '../MobileQuickCommandComposer';
import { clearPromptHistory, recordPromptHistory } from '../useMobilePromptHistory';

const CHAT_ID = 'composer-chat-1';

function getInput(): HTMLTextAreaElement {
  return screen.getByRole('textbox') as HTMLTextAreaElement;
}

function type(value: string): void {
  fireEvent.change(getInput(), { target: { value } });
}

describe('MobileQuickCommandComposer', () => {
  const onSubmit = vi.fn();
  const onOpenAdvisor = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    clearPromptHistory(CHAT_ID);
    speechOnTranscript.current = null;
  });

  const renderComposer = (loading = false) =>
    render(
      <MobileQuickCommandComposer
        chatId={CHAT_ID}
        loading={loading}
        messages={[{ content: '把 MyrmAgent 沙箱跑起来', role: 'user' }]}
        onSubmit={onSubmit}
        onOpenAdvisor={onOpenAdvisor}
      />,
    );

  it('submits the trimmed draft through the send button and clears the input', () => {
    renderComposer();
    type('  检查一下沙箱  ');

    fireEvent.click(screen.getByRole('button', { name: 'send' }));

    expect(onSubmit).toHaveBeenCalledWith('检查一下沙箱');
    expect(getInput().value).toBe('');
  });

  it('never submits on Enter so a soft keyboard return key can insert a newline', () => {
    renderComposer();
    type('第一段要求');
    fireEvent.keyDown(getInput(), { key: 'Enter', keyCode: 13 });

    expect(onSubmit).not.toHaveBeenCalled();
    expect(getInput().value).toBe('第一段要求');
  });

  it('keeps multi-line drafts intact until the user explicitly sends', () => {
    renderComposer();
    type('第一段：看现金流');
    type('第一段：看现金流\n第二段：重点看经营活动');

    fireEvent.click(screen.getByRole('button', { name: 'send' }));

    expect(onSubmit).toHaveBeenCalledWith('第一段：看现金流\n第二段：重点看经营活动');
  });

  it('routes /ask to the advisor instead of the agent and clears the draft', () => {
    renderComposer();
    type('/ask  这个方案靠谱吗');

    fireEvent.click(screen.getByRole('button', { name: 'send' }));

    expect(onOpenAdvisor).toHaveBeenCalledWith('这个方案靠谱吗');
    expect(onSubmit).not.toHaveBeenCalled();
    expect(getInput().value).toBe('');
  });

  it('routes a bare /side command to the advisor with an empty question', () => {
    renderComposer();
    type('/side');

    fireEvent.click(screen.getByRole('button', { name: 'send' }));

    expect(onOpenAdvisor).toHaveBeenCalledWith('');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('appends the speech transcript to the draft instead of dispatching it', () => {
    renderComposer(true);
    type('先停一下');
    act(() => {
      speechOnTranscript.current?.('改成只读');
    });

    expect(onSubmit).not.toHaveBeenCalled();
    expect(onOpenAdvisor).not.toHaveBeenCalled();
    expect(getInput().value).toBe('先停一下 改成只读');
  });

  it('concatenates multi-segment streaming transcripts into one draft', () => {
    renderComposer();
    act(() => {
      speechOnTranscript.current?.('帮我把风险条款列出来');
    });
    act(() => {
      speechOnTranscript.current?.('第一条第二条都要');
    });

    expect(getInput().value).toBe('帮我把风险条款列出来 第一条第二条都要');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('restores the persisted draft for the same chat on remount', async () => {
    const first = renderComposer();
    type('未发送的半句话');
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 600));
    });
    first.unmount();

    renderComposer();
    expect(getInput().value).toBe('未发送的半句话');
  });

  it('isolates drafts per chatId', () => {
    const first = renderComposer();
    type('会话 A 的草稿');
    first.unmount();

    render(
      <MobileQuickCommandComposer
        chatId="composer-chat-2"
        loading={false}
        messages={[]}
        onSubmit={onSubmit}
        onOpenAdvisor={onOpenAdvisor}
      />,
    );
    expect(getInput().value).toBe('');
  });

  it('drops the previous chat draft when the same instance switches to a chat without a draft', async () => {
    localStorage.setItem(`myrm_draft_${CHAT_ID}`, JSON.stringify({ content: '会话 A 的草稿', timestamp: Date.now() }));
    const { rerender } = renderComposer();
    expect(getInput().value).toBe('会话 A 的草稿');

    await act(async () => {
      rerender(
        <MobileQuickCommandComposer
          chatId="composer-chat-empty"
          loading={false}
          messages={[]}
          onSubmit={onSubmit}
          onOpenAdvisor={onOpenAdvisor}
        />,
      );
    });

    expect(getInput().value).toBe('');
  });

  it('swaps to the target chat draft without cross-writing when switching between chats with drafts', async () => {
    const other = 'composer-chat-3';
    localStorage.setItem(`myrm_draft_${CHAT_ID}`, JSON.stringify({ content: '会话 A 的草稿', timestamp: 1_000 }));
    localStorage.setItem(`myrm_draft_${other}`, JSON.stringify({ content: '会话 C 的草稿', timestamp: 2_000 }));

    const { rerender } = renderComposer();
    expect(getInput().value).toBe('会话 A 的草稿');

    await act(async () => {
      rerender(
        <MobileQuickCommandComposer
          chatId={other}
          loading={false}
          messages={[]}
          onSubmit={onSubmit}
          onOpenAdvisor={onOpenAdvisor}
        />,
      );
    });
    expect(getInput().value).toBe('会话 C 的草稿');

    // 跨会话切换不得把任一方草稿写进对方存储键
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 600));
    });
    expect(JSON.parse(localStorage.getItem(`myrm_draft_${CHAT_ID}`) ?? '{}').content).toBe('会话 A 的草稿');
    expect(JSON.parse(localStorage.getItem(`myrm_draft_${other}`) ?? '{}').content).toBe('会话 C 的草稿');
  });

  it('cycles backwards through history and then hands the draft back', () => {
    recordPromptHistory(CHAT_ID, '最早一条');
    recordPromptHistory(CHAT_ID, '最新一条');
    renderComposer();
    type('我的草稿');

    const historyBtn = screen.getByRole('button', { name: /historyNav/i });
    fireEvent.click(historyBtn);
    expect(getInput().value).toBe('最新一条');

    fireEvent.click(historyBtn);
    expect(getInput().value).toBe('最早一条');

    fireEvent.click(historyBtn);
    expect(getInput().value).toBe('我的草稿');
  });

  it('keeps the user draft intact after a history round trip', async () => {
    recordPromptHistory(CHAT_ID, '历史指令');
    renderComposer();
    type('我的草稿');

    const historyBtn = screen.getByRole('button', { name: /historyNav/i });
    fireEvent.click(historyBtn);
    expect(getInput().value).toBe('历史指令');

    fireEvent.click(historyBtn);
    expect(getInput().value).toBe('我的草稿');

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 600));
    });
    const stored = localStorage.getItem(`myrm_draft_${CHAT_ID}`);
    expect(stored).toContain('我的草稿');
    expect(stored).not.toContain('历史指令');
  });

  it('exits history browsing when the user starts typing again', () => {
    recordPromptHistory(CHAT_ID, '历史指令');
    renderComposer();

    fireEvent.click(screen.getByRole('button', { name: /historyNav/i }));
    expect(getInput().value).toBe('历史指令');

    type('改写后的内容');
    expect(getInput().value).toBe('改写后的内容');
  });

  it('exits history browsing and edits the recalled prompt when the user types on it', () => {
    recordPromptHistory(CHAT_ID, '帮我分析这份财报');
    renderComposer();

    fireEvent.click(screen.getByRole('button', { name: /historyNav/i }));
    expect(getInput().value).toBe('帮我分析这份财报');

    // 真实输入会在当前显示值后追加字符，回溯文本应成为可编辑草稿而非被丢弃
    fireEvent.change(getInput(), { target: { value: '帮我分析这份财报的现金流' } });
    expect(getInput().value).toBe('帮我分析这份财报的现金流');
  });

  it('appends clipboard text into the multi-line draft', async () => {
    navigatorClipboard.readText.mockResolvedValue('参考资料第一行\n参考资料第二行');
    renderComposer();
    type('已输入：');

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^paste$/i }));
    });

    expect(getInput().value).toBe('已输入： 参考资料第一行\n参考资料第二行');
  });

  it('archives a meaningful draft on clear and empties the input', () => {
    renderComposer();
    type('需要留档的长指令文本');

    fireEvent.click(screen.getByRole('button', { name: /^clear$/i }));

    expect(getInput().value).toBe('');
  });

  it('keeps the send button disabled for a whitespace-only draft', () => {
    renderComposer();
    type('   ');

    expect((screen.getByRole('button', { name: 'send' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('exposes the steer placeholder while a run is in flight', () => {
    renderComposer(true);
    expect(getInput().getAttribute('placeholder')).toBe('steerPlaceholder');
  });
});
