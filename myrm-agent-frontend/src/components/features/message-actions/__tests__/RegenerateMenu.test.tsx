import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import RegenerateMenu from '../RegenerateMenu';

const stableT = (key: string) => {
  const translations: Record<string, string> = {
    regenerate: 'Regenerate',
    regenerate_try_again: 'Try Again',
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

  it.each<[string, string | undefined]>([
    ['Try Again', undefined],
    ['More Concise', 'Be more concise and to the point'],
  ])('sends the matching instruction for the "%s" preset', (label, instruction) => {
    render(<RegenerateMenu onRegenerate={onRegenerateMock} />);
    fireEvent.click(screen.getByLabelText('Regenerate options'));

    fireEvent.click(screen.getByText(label));

    expect(onRegenerateMock).toHaveBeenCalledWith(instruction);
  });

  it('keeps a single plain retry instead of a separate stronger-model entry', () => {
    render(<RegenerateMenu onRegenerate={onRegenerateMock} />);
    fireEvent.click(screen.getByLabelText('Regenerate options'));

    expect(screen.getAllByRole('button').map((button) => button.textContent)).not.toContain('regenerate_frontier');
    expect(screen.getByText('Try Again')).toBeInTheDocument();
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
