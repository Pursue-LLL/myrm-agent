/** @vitest-environment jsdom */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

import { MaxIterationsSection } from '../AgentCapabilitiesTabSections';
import type { useTranslations } from 'next-intl';

const t = stableT as unknown as ReturnType<typeof useTranslations>;

type EditorLike = {
  maxIterations: number | null;
  setMaxIterations: (value: number | null) => void;
};

function renderSection(editor: EditorLike) {
  return render(<MaxIterationsSection editor={editor} t={t} />);
}

describe('MaxIterationsSection', () => {
  let setMaxIterations: ReturnType<typeof vi.fn>;
  let editor: EditorLike;

  beforeEach(() => {
    setMaxIterations = vi.fn();
    editor = { maxIterations: null, setMaxIterations };
  });

  it('renders the number input with backend bounds and placeholder', () => {
    renderSection(editor);
    const input = screen.getByPlaceholderText('agent.maxIterationsPlaceholder');
    expect(input).toHaveAttribute('type', 'number');
    expect(input).toHaveAttribute('min', '5');
    expect(input).toHaveAttribute('max', '500');
  });

  it('shows an empty input when maxIterations is null (default)', () => {
    renderSection(editor);
    expect(screen.getByPlaceholderText('agent.maxIterationsPlaceholder')).toHaveValue(null);
  });

  it('shows the stored value when maxIterations is set', () => {
    editor.maxIterations = 120;
    renderSection(editor);
    expect(screen.getByPlaceholderText('agent.maxIterationsPlaceholder')).toHaveValue(120);
  });

  it('clamps a value above the max down to 500', () => {
    renderSection(editor);
    fireEvent.change(screen.getByPlaceholderText('agent.maxIterationsPlaceholder'), {
      target: { value: '999' },
    });
    expect(setMaxIterations).toHaveBeenCalledWith(500);
  });

  it('clamps a negative value up to 5', () => {
    renderSection(editor);
    fireEvent.change(screen.getByPlaceholderText('agent.maxIterationsPlaceholder'), {
      target: { value: '-3' },
    });
    expect(setMaxIterations).toHaveBeenCalledWith(5);
  });

  it('coerces zero to the minimum 5', () => {
    renderSection(editor);
    fireEvent.change(screen.getByPlaceholderText('agent.maxIterationsPlaceholder'), {
      target: { value: '0' },
    });
    expect(setMaxIterations).toHaveBeenCalledWith(5);
  });

  it('passes through an in-range value unchanged', () => {
    renderSection(editor);
    fireEvent.change(screen.getByPlaceholderText('agent.maxIterationsPlaceholder'), {
      target: { value: '50' },
    });
    expect(setMaxIterations).toHaveBeenCalledWith(50);
  });

  it('maps an empty input back to null (restore system default)', () => {
    editor.maxIterations = 50;
    renderSection(editor);
    fireEvent.change(screen.getByPlaceholderText('agent.maxIterationsPlaceholder'), {
      target: { value: '' },
    });
    expect(setMaxIterations).toHaveBeenCalledWith(null);
  });
});
