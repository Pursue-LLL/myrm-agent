/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Source } from '@/store/chat/types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

import { SourceItem } from '../SourcesButton';

describe('SourceItem for MCP skills', () => {
  it('shows the skill name when the source carries one', () => {
    const source: Source = { index: 1, type: 'mcp', skill_name: 'notion-search' };
    render(<SourceItem source={source} />);

    expect(screen.getByText('notion-search')).toBeInTheDocument();
  });

  it('falls back to a localized label when the skill has no name', () => {
    const source: Source = { index: 2, type: 'mcp' };
    render(<SourceItem source={source} />);

    expect(screen.getByText('mcpSkillFallback')).toBeInTheDocument();
  });
});
