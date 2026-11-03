/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const stableT = (key: string, values?: Record<string, unknown>) =>
  values ? `${key}:${Object.values(values).join('/')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const memoryServiceMock = vi.hoisted(() => ({
  previewRulesSafe: vi.fn(),
  exportRulesSafe: vi.fn(),
}));
vi.mock('@/services/memory', () => memoryServiceMock);

const toastMock = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/shared/useToast', () => ({ toast: toastMock }));

import ShareRulesDialog from '../ShareRulesDialog';

const RULES = [
  { id: 'r1', content: 'Always run tests', rendered: '# Rule 1' },
  { id: 'r2', content: 'Prefer small commits', rendered: '# Rule 2' },
];

beforeEach(() => {
  memoryServiceMock.previewRulesSafe.mockReset().mockResolvedValue(RULES);
  memoryServiceMock.exportRulesSafe.mockReset().mockResolvedValue(undefined);
  toastMock.mockReset();
});

describe('ShareRulesDialog localized copy', () => {
  it('renders header, selection controls and footer actions from translations', async () => {
    render(<ShareRulesDialog open onOpenChange={() => undefined} />);

    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.getByText('privacyBadge')).toBeInTheDocument();
    expect(screen.getByText('description')).toBeInTheDocument();
    expect(await screen.findByText('Always run tests')).toBeInTheDocument();
    expect(screen.getByText('selectedCount:2/2')).toBeInTheDocument();
    expect(screen.getByText('deselectAll')).toBeInTheDocument();
    expect(screen.getByText('copyButton')).toBeInTheDocument();
    expect(screen.getByText('downloadZip')).toBeInTheDocument();
    expect(screen.getAllByTitle('previewSanitized')).toHaveLength(2);
  });

  it('toggles the select-all label when every rule is deselected', async () => {
    render(<ShareRulesDialog open onOpenChange={() => undefined} />);

    await userEvent.click(await screen.findByText('deselectAll'));

    expect(screen.getByText('selectAll')).toBeInTheDocument();
    expect(screen.getByText('selectedCount:0/2')).toBeInTheDocument();
  });

  it('shows the empty-state message when no rules exist', async () => {
    memoryServiceMock.previewRulesSafe.mockResolvedValue([]);
    render(<ShareRulesDialog open onOpenChange={() => undefined} />);

    expect(await screen.findByText('empty')).toBeInTheDocument();
  });

  it('switches the copy button to its copied label after copying', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    render(<ShareRulesDialog open onOpenChange={() => undefined} />);

    await userEvent.click(await screen.findByText('copyButton'));

    await waitFor(() => expect(screen.getByText('copiedButton')).toBeInTheDocument());
    expect(writeText).toHaveBeenCalledWith('# Rule 1\n\n---\n\n# Rule 2');
    expect(toastMock).toHaveBeenCalledWith({ title: 'copied:2' });
  });
});
