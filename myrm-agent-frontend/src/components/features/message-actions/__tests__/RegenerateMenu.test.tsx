import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import RegenerateMenu from '../RegenerateMenu';

const stableT = (key: string) => {
  const translations: Record<string, string> = {
    regenerate: 'Regenerate',
    regenerate_try_again: 'Try Again',
    regenerate_frontier: '✨ Retry with Frontier Model',
    regenerate_concise: 'More Concise',
    regenerate_detailed: 'More Detailed',
    regenerate_creative: 'More Creative',
    regenerate_custom: 'Custom Instruction...',
    regenerate_custom_placeholder: 'Tell the AI how to respond...',
    regenerate_submit: 'Submit',
  };
  return translations[key] || key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('RegenerateMenu', () => {
  const onRegenerateMock = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders default regenerate button and triggers basic retry without instruction', async () => {
    render(<RegenerateMenu onRegenerate={onRegenerateMock} />);
    const mainBtn = screen.getByTitle('Regenerate');
    expect(mainBtn).toBeInTheDocument();

    fireEvent.click(mainBtn);
    expect(onRegenerateMock).toHaveBeenCalledWith(undefined);
  });

  it('opens dropdown menu and shows frontier model retry option with highlighted CTA', () => {
    render(<RegenerateMenu onRegenerate={onRegenerateMock} />);
    const expandBtn = screen.getByLabelText('Regenerate options');
    fireEvent.click(expandBtn);

    const frontierBtn = screen.getByText('✨ Retry with Frontier Model');
    expect(frontierBtn).toBeInTheDocument();

    fireEvent.click(frontierBtn);
    expect(onRegenerateMock).toHaveBeenCalledWith(
      'Retry with frontier model reasoning and comprehensive deep analysis',
    );
  });

  it('allows custom instruction submission', () => {
    render(<RegenerateMenu onRegenerate={onRegenerateMock} />);
    const expandBtn = screen.getByLabelText('Regenerate options');
    fireEvent.click(expandBtn);

    const customOption = screen.getByText('Custom Instruction...');
    fireEvent.click(customOption);

    const input = screen.getByPlaceholderText('Tell the AI how to respond...');
    expect(input).toBeInTheDocument();

    fireEvent.change(input, { target: { value: 'Translate to French' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onRegenerateMock).toHaveBeenCalledWith('Translate to French');
  });
});
