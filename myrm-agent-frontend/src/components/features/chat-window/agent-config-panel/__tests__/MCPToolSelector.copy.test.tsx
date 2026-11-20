import { act, cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { MockLocale } from '@/test-utils/realIntl';
import { destructiveTool, kit, readOnlyTool, toolsRead, writableTool } from './mcpToolKit';
import { renderSelector, toolBox } from './mcpToolRender';

const { intl } = vi.hoisted(() => ({ intl: { locale: 'en' as MockLocale } }));

vi.mock('@/services/llm-config', async () => (await import('./mcpToolKit')).llmConfigMock());
vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));

beforeEach(() => {
  intl.locale = 'en';
  kit.fetchMCPTools.mockReset();
});

afterEach(() => {
  cleanup();
});

/** Opens the filter by its closed state: with the real wording its name is no key any more. */
async function openFilter(): Promise<void> {
  fireEvent.click(screen.getByRole('button', { expanded: false }));
  await act(async () => undefined);
}

/** The risk a row reads out to a screen reader: what the user is told about the tool. */
const riskOf = (name: string) => toolBox(name).closest('label')?.querySelector('.sr-only')?.textContent;

describe('MCPToolSelector wording', () => {
  it.each([
    ['en', 'Declared read-only', 'Not declared read-only', 'Declared destructive'],
    ['zh', '声明只读', '未声明只读', '声明破坏性'],
  ] as const)(
    'words what a server declares about its tools in %s',
    async (locale, readOnly, notReadOnly, destructive) => {
      intl.locale = locale;
      kit.fetchMCPTools.mockResolvedValue(
        toolsRead(readOnlyTool('look'), writableTool('edit'), destructiveTool('wipe')),
      );
      renderSelector();
      await openFilter();

      expect(riskOf('look')).toBe(readOnly);
      expect(riskOf('edit')).toBe(notReadOnly);
      expect(riskOf('wipe')).toBe(destructive);
    },
  );

  it('counts the destructive tools that are off with the right plural in English', async () => {
    kit.fetchMCPTools.mockResolvedValue(
      toolsRead(readOnlyTool('look'), destructiveTool('wipe'), destructiveTool('drop')),
    );
    const { update } = renderSelector({ selectedTools: ['look'] });
    await openFilter();
    expect(screen.getByText('2 tools declared destructive are off')).toBeInTheDocument();

    update({ selectedTools: ['look', 'wipe'] });
    expect(screen.getByText('1 tool declared destructive is off')).toBeInTheDocument();
  });

  it('counts the destructive tools that are off in Chinese', async () => {
    intl.locale = 'zh';
    kit.fetchMCPTools.mockResolvedValue(toolsRead(readOnlyTool('look'), destructiveTool('wipe')));
    renderSelector({ selectedTools: ['look'] });
    await openFilter();

    expect(screen.getByText('1 个声明破坏性的工具未启用')).toBeInTheDocument();
  });
});
