/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const adoptProjectMock = vi.hoisted(() => vi.fn());
vi.mock('@/store/useProjectStore', () => ({
  useProjectStore: (selector: (s: { adoptProject: typeof adoptProjectMock }) => unknown) =>
    selector({ adoptProject: adoptProjectMock }),
}));
vi.mock('@/store/useChatStore', () => ({
  default: (selector: (s: { chatId: null; setWorkspaceDir: () => void }) => unknown) =>
    selector({ chatId: null, setWorkspaceDir: () => undefined }),
}));
vi.mock('@/services/chat', () => ({ browseDirectories: vi.fn() }));
vi.mock('@/lib/desktopBridge', () => ({ desktopBridge: { isDesktop: () => false } }));
vi.mock('@/lib/tauri', () => ({ isTauriEnvironment: () => false }));
vi.mock('@/hooks/shared/useToast', () => ({ toast: vi.fn() }));

import ProjectWorkspaceAdoptDialog from '../ProjectWorkspaceAdoptDialog';

beforeEach(() => {
  adoptProjectMock.mockReset();
  localStorage.clear();
});

describe('ProjectWorkspaceAdoptDialog localized copy', () => {
  it('labels the name field, placeholder, cancel and submit controls', () => {
    render(<ProjectWorkspaceAdoptDialog open onOpenChange={() => undefined} initialPath="/Users/me/notes" />);

    expect(screen.getByText('adoptProjectName')).toBeInTheDocument();
    expect(screen.getByLabelText('adoptProjectName')).toHaveValue('notes');
    expect(screen.getByText('adoptCancel')).toBeInTheDocument();
    expect(screen.getByText('adoptSubmit')).toBeInTheDocument();
  });

  it('switches the submit label while the adoption is running', async () => {
    adoptProjectMock.mockReturnValue(new Promise(() => undefined));
    render(<ProjectWorkspaceAdoptDialog open onOpenChange={() => undefined} initialPath="/Users/me/notes" />);

    await userEvent.click(screen.getByText('adoptSubmit'));

    await waitFor(() => expect(screen.getByText('adoptSubmitting')).toBeInTheDocument());
    expect(adoptProjectMock).toHaveBeenCalledWith('/Users/me/notes', 'notes');
  });

  it('closes through the cancel button', async () => {
    const onOpenChange = vi.fn();
    render(<ProjectWorkspaceAdoptDialog open onOpenChange={onOpenChange} initialPath="/Users/me/notes" />);

    await userEvent.click(screen.getByText('adoptCancel'));

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
