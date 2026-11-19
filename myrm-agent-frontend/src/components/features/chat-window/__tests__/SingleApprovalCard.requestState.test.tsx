'use client';

/**
 * What a card keeps while a person works on it (the text being edited, the folders ticked, the "always allow" scope)
 * belongs to the request on screen: it starts from that request's own input and tool, and a card handed another
 * request starts over instead of carrying the previous request's edits or folder grant into it.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import SingleApprovalCard from '@/components/features/chat-window/SingleApprovalCard';
import type { ToolApprovalRequest } from '@/store/chat/types';

import { approvalRequest } from './approvalKit';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

vi.mock('@/store/useDesktopInspectorStore', () => ({
  default: (selector: (state: { viewData: null }) => unknown) => selector({ viewData: null }),
  selectScopedDesktopViewData: () => null,
}));

vi.mock('@/store/useBrowserInspectorStore', () => ({
  default: (selector: (state: { viewData: null }) => unknown) => selector({ viewData: null }),
  selectScopedBrowserViewData: () => null,
}));

const FOLDERS = [{ path: '/Users/me/Downloads', writable: false }];

const SHELL_SCOPE = { tool: true, args: true, duration: 'session', ttl_seconds: -1 };
const TOOL_SCOPE = { tool: true, duration: 'session', ttl_seconds: -1 };

function fileRead(requestId: string, file: string): ToolApprovalRequest {
  return approvalRequest({
    requestId,
    toolName: 'file_read_tool',
    toolInput: { paths: [`/Users/me/Downloads/${file}`] },
    grantDirectories: FOLDERS,
  });
}

/** Renders the card; `showRequest` hands the same mounted card another request, the way a parent without a key does. */
function renderCard(request: ToolApprovalRequest) {
  const onResolve = vi.fn(async () => {});
  const card = (shown: ToolApprovalRequest) => (
    <SingleApprovalCard request={shown} onResolve={onResolve} isLoading={false} />
  );
  const view = render(card(request));
  return { onResolve, showRequest: (next: ToolApprovalRequest) => view.rerender(card(next)) };
}

function confirmAlwaysAllow() {
  fireEvent.click(screen.getByRole('button', { name: 'allowAlways' }));
  fireEvent.click(screen.getByRole('button', { name: 'allowAlwaysConfirm.confirm' }));
}

describe('SingleApprovalCard state of the request on screen', () => {
  it('opens the edit view on the input of the request', () => {
    renderCard(approvalRequest({ toolInput: { command: 'ls -la' } }));

    fireEvent.click(screen.getByRole('button', { name: 'edit' }));

    expect(screen.getByRole('textbox')).toHaveValue('ls -la');
  });

  it.each([
    ['a shell command', approvalRequest(), SHELL_SCOPE],
    ['a file read', fileRead('req-read', 'a.csv'), TOOL_SCOPE],
  ])('starts "always allow" for %s at the scope its tool calls for', (_label, request, scope) => {
    const { onResolve } = renderCard(request);

    confirmAlwaysAllow();

    expect(onResolve).toHaveBeenCalledWith(request.requestId, 'approve', { allow_always: scope, ttl_seconds: -1 });
  });

  it('starts "always allow" for the next request at the scope of its own tool', () => {
    const { onResolve, showRequest } = renderCard(approvalRequest());

    showRequest(fileRead('req-read', 'a.csv'));
    confirmAlwaysAllow();

    expect(onResolve).toHaveBeenCalledWith('req-read', 'approve', { allow_always: TOOL_SCOPE, ttl_seconds: -1 });
  });

  it('starts over on the input of the next request', () => {
    const { showRequest } = renderCard(approvalRequest({ toolInput: { command: 'ls -la' } }));
    fireEvent.click(screen.getByRole('button', { name: 'edit' }));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'rm -rf build' } });

    showRequest(approvalRequest({ requestId: 'req-2', toolInput: { command: 'pwd' } }));

    expect(screen.queryByRole('textbox')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'edit' }));
    expect(screen.getByRole('textbox')).toHaveValue('pwd');
  });

  it('does not carry a ticked folder grant over to the next request', () => {
    const { onResolve, showRequest } = renderCard(fileRead('req-a', 'a.csv'));
    fireEvent.click(screen.getByRole('checkbox', { name: 'grantDirectory' }));

    showRequest(fileRead('req-b', 'b.csv'));
    fireEvent.click(screen.getByRole('button', { name: 'approve' }));

    expect(onResolve).toHaveBeenCalledWith('req-b', 'approve', {});
  });
});
