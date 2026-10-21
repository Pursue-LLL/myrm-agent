/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getTreeMock = vi.fn();
const compoundWikiMock = vi.fn();
const pushMock = vi.fn();

const chatStoreState = vi.hoisted(() => ({
  incognitoMode: false,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
}));

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: Record<string, string>) => {
    if (values?.scope) {
      return `${namespace}.${key}:${values.scope}`;
    }
    return `${namespace}.${key}`;
  },
  useLocale: () => 'en',
}));

vi.mock('@/lib/api', () => ({
  ApiError: class ApiError extends Error {
    code: number;
    businessCode?: string;

    constructor(message: string, code = 500, _details: unknown[] = [], _traceId?: string, businessCode?: string) {
      super(message);
      this.code = code;
      this.businessCode = businessCode;
    }
  },
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

vi.mock('@/components/agent/builtin-agent-i18n', () => ({
  getBuiltinAgentName: (_id: string, name: string) => name,
}));

vi.mock('@/store/useChatStore', () => ({
  default: (
    selector: (state: {
      agentConfig: { agentId?: string; agentName?: string; enabledBuiltinTools?: string[] } | null;
      currentBuiltinTools: string[];
      incognitoMode: boolean;
      messages: Array<{ role: string; content: string }>;
    }) => unknown,
  ) =>
    selector({
      agentConfig: {
        agentId: 'research-agent',
        agentName: 'Research Agent',
        enabledBuiltinTools: ['wiki'],
      },
      currentBuiltinTools: ['wiki'],
      incognitoMode: chatStoreState.incognitoMode,
      messages: [
        { role: 'user', content: 'What is revenue growth?' },
        { role: 'assistant', content: 'Important finding about revenue growth' },
      ],
    }),
}));

vi.mock('@/services/wikiService', () => ({
  wikiService: {
    getTree: (...args: unknown[]) => getTreeMock(...args),
    compoundWiki: (...args: unknown[]) => compoundWikiMock(...args),
  },
}));

vi.mock('@/components/features/settings/sections/knowledge/wiki/WikiFolderSelectTree', () => ({
  WikiFolderSelectTree: () => <div data-testid="wiki-folder-tree" />,
}));

import SaveToWikiButton from '../SaveToWikiButton';

describe('SaveToWikiButton agent scope', () => {
  beforeEach(() => {
    chatStoreState.incognitoMode = false;
    getTreeMock.mockReset();
    compoundWikiMock.mockReset();
    pushMock.mockReset();
    getTreeMock.mockResolvedValue([]);
    compoundWikiMock.mockResolvedValue({
      success: true,
      pending_edit_id: 42,
      concept_name: 'ChatCompounds/2026-08/important-finding-ab',
      message: 'ok',
    });
  });

  it('stages compound draft against the active chat agent wiki scope', async () => {
    render(
      <SaveToWikiButton
        message={{
          chatId: 'chat-1',
          messageId: 'msg-1',
          content: 'Important finding about revenue growth',
          role: 'assistant',
          createdAt: new Date(),
        }}
        messageIndex={1}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'settings.wiki.saveToWiki.buttonTitle' }));

    await waitFor(() => {
      expect(getTreeMock).toHaveBeenCalledWith('research-agent');
    });

    expect(screen.getByText('settings.wiki.scopeChip.label:Research Agent')).toBeTruthy();

    fireEvent.click(screen.getByText('settings.wiki.saveToWiki.save'));

    await waitFor(() => {
      expect(compoundWikiMock).toHaveBeenCalledWith(
        expect.objectContaining({
          concept_name: expect.stringContaining('important-finding-ab'),
          source_chat: 'chat-1',
          source_message: 'msg-1',
        }),
        'research-agent',
      );
    });
  });

  it('shows localized toast when the source message is no longer available', async () => {
    const { ApiError } = await import('@/lib/api');
    const { toast } = await import('sonner');
    compoundWikiMock.mockRejectedValueOnce(
      new ApiError('Chat message not found', 404, [], undefined, 'message_not_found'),
    );

    render(
      <SaveToWikiButton
        message={{
          chatId: 'chat-1',
          messageId: 'msg-missing',
          content: 'Important finding about revenue growth',
          role: 'assistant',
          createdAt: new Date(),
        }}
        messageIndex={1}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'settings.wiki.saveToWiki.buttonTitle' }));
    fireEvent.click(await screen.findByText('settings.wiki.saveToWiki.save'));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('settings.wiki.saveToWiki.messageNotFound');
    });
  });

  it('does not render in incognito mode', () => {
    chatStoreState.incognitoMode = true;

    render(
      <SaveToWikiButton
        message={{
          chatId: 'chat-1',
          messageId: 'msg-1',
          content: 'Important finding about revenue growth',
          role: 'assistant',
          createdAt: new Date(),
        }}
        messageIndex={1}
      />,
    );

    expect(screen.queryByRole('button', { name: 'settings.wiki.saveToWiki.buttonTitle' })).toBeNull();
  });
});
