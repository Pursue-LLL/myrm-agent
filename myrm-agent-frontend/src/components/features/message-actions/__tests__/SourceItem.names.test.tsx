/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { MockLocale } from '@/test-utils/realIntl';
import type { Source } from '@/store/chat/types';

const intl = vi.hoisted(() => ({ locale: 'zh' as MockLocale }));
vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));

import { SourceItem } from '../SourceItem';

const KNOWLEDGE: Source = {
  index: 1,
  type: 'knowledge',
  kb_name: 'Work',
  filename: 'deploy-notes',
  section: 'Rollback',
};

describe('SourceItem names', () => {
  it.each([
    ['zh', '目录索引'],
    ['en', 'Catalog index'],
  ] as const)('words the catalog section of a wiki hit in the interface language (%s)', (locale, catalogSection) => {
    intl.locale = locale;

    render(<SourceItem source={{ ...KNOWLEDGE, filename: 'index', section: 'index_routing' }} />);

    expect(screen.getByText(`index § ${catalogSection}`)).toBeInTheDocument();
  });

  it('shows any other section of a wiki hit as the server sent it', () => {
    intl.locale = 'zh';

    render(<SourceItem source={KNOWLEDGE} />);

    expect(screen.getByText('deploy-notes § Rollback')).toBeInTheDocument();
  });

  it.each([
    ['zh', '未命名', '历史会话', 'MCP 技能'],
    ['en', 'Untitled', 'Conversation history', 'MCP skill'],
  ] as const)(
    'stands in for a source that has no name with the interface wording (%s)',
    (locale, untitled, conversation, mcp) => {
      intl.locale = locale;
      const nameless: Source[] = [
        { index: 1, type: 'web_search', url: 'https://example.com/a' },
        { index: 2, type: 'conversation_history' },
        { index: 3, type: 'mcp' },
      ];

      render(
        <>
          {nameless.map((source) => (
            <SourceItem key={source.index} source={source} />
          ))}
        </>,
      );

      expect(screen.getByText(untitled)).toBeInTheDocument();
      expect(screen.getByText(conversation)).toBeInTheDocument();
      expect(screen.getByText(mcp)).toBeInTheDocument();
    },
  );

  it('keeps the product name for a wiki hit that names neither its file nor its knowledge base', () => {
    intl.locale = 'zh';

    render(<SourceItem source={{ index: 1, type: 'knowledge' }} />);

    expect(screen.getByText('LLM-Wiki')).toBeInTheDocument();
  });

  it('names a web page and a past conversation by their title', () => {
    intl.locale = 'zh';

    render(
      <>
        <SourceItem
          source={{ index: 1, type: 'web_search', title: 'Deploy guide', url: 'https://docs.example.com/g' }}
        />
        <SourceItem source={{ index: 2, type: 'conversation_history', title: 'Planning the launch' }} />
      </>,
    );

    expect(screen.getByText('Deploy guide')).toBeInTheDocument();
    expect(screen.getByText('Planning the launch')).toBeInTheDocument();
  });
});
