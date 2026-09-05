import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ToolCallingModelChecklist } from '../ToolCallingModelChecklist';
import { UnverifiedModelCallout } from '../UnverifiedModelCallout';

// Mock next-intl
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, unknown>) => {
    if (params?.model) return `${key}:${params.model}`;
    return key;
  },
}));

describe('ToolCallingModelChecklist Component', () => {
  it('renders benchmark models correctly', () => {
    const onSelect = vi.fn();
    render(<ToolCallingModelChecklist onSelectModel={onSelect} />);

    expect(screen.getByTestId('tool-calling-checklist')).toBeInTheDocument();
    expect(screen.getByText('Claude 3.5 Sonnet')).toBeInTheDocument();
    expect(screen.getByText('GPT-4o')).toBeInTheDocument();
    expect(screen.getByText('DeepSeek-V3')).toBeInTheDocument();
    expect(screen.getByText('Qwen 2.5 Coder 32B')).toBeInTheDocument();

    const gptBtn = screen.getByTestId('btn-select-model-gpt-4o');
    fireEvent.click(gptBtn);
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'gpt-4o', name: 'GPT-4o' })
    );
  });
});

describe('UnverifiedModelCallout Component', () => {
  it('renders verified callout when model is verified', () => {
    render(<UnverifiedModelCallout modelName="gpt-4o" />);
    expect(screen.getByTestId('callout-verified')).toBeInTheDocument();
    expect(screen.queryByTestId('callout-unverified')).not.toBeInTheDocument();
  });

  it('renders unverified warning callout when model is not verified', () => {
    render(<UnverifiedModelCallout modelName="llama-3-8b-instruct" />);
    expect(screen.getByTestId('callout-unverified')).toBeInTheDocument();
    expect(screen.queryByTestId('callout-verified')).not.toBeInTheDocument();
  });

  it('renders nothing when modelName is empty', () => {
    const { container } = render(<UnverifiedModelCallout modelName="" />);
    expect(container.firstChild).toBeNull();
  });
});
