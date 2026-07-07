'use client';

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

const mockStore: Record<string, unknown> = {
  actionMode: 'agent',
  inputMessage: '',
  agentConfig: null,
};

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: typeof mockStore) => unknown) => selector(mockStore),
}));

import SamplePrompts from '../SamplePrompts';

describe('SamplePrompts', () => {
  beforeEach(() => {
    mockStore.actionMode = 'agent';
    mockStore.agentConfig = null;
  });

  it('renders prompt chips for agent mode', () => {
    render(<SamplePrompts />);
    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(4);
  });

  it('renders prompt chips for fast mode', () => {
    mockStore.actionMode = 'fast';
    render(<SamplePrompts />);
    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(4);
  });

  it('falls back to agent mode for deep_research (hidden product mode)', () => {
    mockStore.actionMode = 'deep_research';
    render(<SamplePrompts />);
    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(4);
    buttons.forEach((btn) => {
      expect(btn.textContent).toMatch(/^samplePrompts\.agent_/);
    });
  });

  it('falls back to agent mode for unsupported modes', () => {
    mockStore.actionMode = 'consensus';
    render(<SamplePrompts />);
    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(4);
    buttons.forEach((btn) => {
      expect(btn.textContent).toMatch(/^samplePrompts\.agent_/);
    });
  });

  it('uses agent custom suggestion prompts when available', () => {
    mockStore.agentConfig = {
      suggestionPrompts: ['Custom prompt A', 'Custom prompt B', 'Custom prompt C', 'Custom prompt D', 'Custom prompt E'],
    };
    render(<SamplePrompts />);
    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(4);
    const texts = buttons.map((btn) => btn.textContent);
    texts.forEach((text) => {
      expect(text).toMatch(/^Custom prompt/);
    });
  });
});
