/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getTreeMock = vi.fn();
const getConceptMock = vi.fn();
const applyWikiMock = vi.fn();

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
    constructor(message: string, code = 500) {
      super(message);
      this.code = code;
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
  default: (selector: (state: { agentConfig: { agentId?: string; agentName?: string } | null }) => unknown) =>
    selector({
      agentConfig: {
        agentId: 'research-agent',
        agentName: 'Research Agent',
      },
    }),
}));

vi.mock('@/services/wikiService', () => ({
  wikiService: {
    getTree: (...args: unknown[]) => getTreeMock(...args),
    getConcept: (...args: unknown[]) => getConceptMock(...args),
    applyWiki: (...args: unknown[]) => applyWikiMock(...args),
  },
}));

vi.mock('@/components/features/settings/sections/knowledge/wiki/WikiFolderSelectTree', () => ({
  WikiFolderSelectTree: () => <div data-testid="wiki-folder-tree" />,
}));

import { ApiError } from '@/lib/api';
import SaveToWikiButton from '../SaveToWikiButton';

describe('SaveToWikiButton agent scope', () => {
  beforeEach(() => {
    getTreeMock.mockReset();
    getConceptMock.mockReset();
    applyWikiMock.mockReset();
    getTreeMock.mockResolvedValue([]);
    getConceptMock.mockRejectedValue(new ApiError('Not found', 404));
    applyWikiMock.mockResolvedValue({ success: true, message: 'ok', op: 'create_note', concept_name: 'x' });
  });

  it('loads and saves against the active chat agent wiki scope', async () => {
    render(
      <SaveToWikiButton
        message={{
          chatId: 'chat-1',
          messageId: 'msg-1',
          content: 'Important finding about revenue growth',
          role: 'assistant',
        }}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'settings.wiki.saveToWiki.buttonTitle' }));

    await waitFor(() => {
      expect(getTreeMock).toHaveBeenCalledWith('research-agent');
    });

    expect(screen.getByText('settings.wiki.scopeChip.label:Research Agent')).toBeTruthy();

    fireEvent.click(screen.getByText('settings.wiki.saveToWiki.save'));

    await waitFor(() => {
      expect(getConceptMock).toHaveBeenCalledWith('important-finding-ab', 'research-agent');
      expect(applyWikiMock).toHaveBeenCalledWith(
        expect.objectContaining({
          op: 'create_note',
          concept_name: 'important-finding-ab',
          body: 'Important finding about revenue growth',
          metadata: expect.objectContaining({
            source_chat: 'chat-1',
            source_message: 'msg-1',
          }),
        }),
        'research-agent',
        'chat',
      );
    });
  });
});
