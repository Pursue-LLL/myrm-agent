'use client';

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import VisualApprovalArtifactCard from '@/components/features/chat-window/approval/VisualApprovalArtifactCard';
import type { ToolApprovalRequest } from '@/store/chat/types';
import type { InspectorViewSnapshot } from '@/lib/approval/visualApprovalContext';

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: Record<string, string>) => {
    if (values) {
      return `${namespace}.${key}:${JSON.stringify(values)}`;
    }
    return `${namespace}.${key}`;
  },
}));

vi.mock('@/components/features/chat-window/SingleApprovalCard', () => ({
  default: () => <div data-testid="single-approval-card-stub" />,
}));

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => true,
}));

const overlaySurfaceMock = vi.hoisted(() => ({ degraded: false }));

vi.mock('@/lib/approval/visualApprovalOsOverlaySurface', () => ({
  useVisualApprovalOsOverlaySurface: () => ({ degraded: overlaySurfaceMock.degraded }),
}));

const viewData: InspectorViewSnapshot = {
  screenshotBase64: 'abc123',
  mimeType: 'image/jpeg',
  viewportWidth: 1920,
  viewportHeight: 1080,
  refs: {
    e1: {
      role: 'button',
      name: 'Delete',
      nth: null,
      bbox: {
        x: 100,
        y: 5900,
        width: 80,
        height: 32,
        centerX: 140,
        centerY: 5916,
        viewport_x: 100,
        viewport_y: 200,
        viewport_width: 80,
        viewport_height: 32,
      },
      position: null,
    },
  },
};

const request: ToolApprovalRequest = {
  requestId: 'req-1',
  toolName: 'browser_click',
  toolInput: { ref: 'e1' },
  reason: 'Click delete',
  timeoutSeconds: 60,
  expiresAt: Math.floor(Date.now() / 1000) + 60,
  timeoutBehavior: 'deny',
  messageId: 'msg-1',
  displayMode: 'approval',
  chatId: 'chat-1',
  actionMode: 'agent',
};

describe('VisualApprovalArtifactCard', () => {
  it('renders visual approval artifact shell with highlight and action stub', () => {
    render(
      <VisualApprovalArtifactCard
        request={request}
        desktopViewData={null}
        browserViewData={viewData}
        onResolve={async () => {}}
        isLoading={false}
      />,
    );

    expect(screen.getByTestId('visual-approval-artifact-card')).toBeInTheDocument();
    expect(screen.getByTestId('visual-approval-highlight')).toBeInTheDocument();
    expect(screen.getByTestId('single-approval-card-stub')).toBeInTheDocument();
    expect(screen.getByText('toolApproval.visualApprovalArtifactTitle')).toBeInTheDocument();
  });

  it('shows ToC hint when native OS highlight is degraded for desktop approvals', () => {
    overlaySurfaceMock.degraded = true;
    const desktopRequest: ToolApprovalRequest = {
      ...request,
      toolName: 'desktop_click',
      toolInput: { ref: 'e1' },
    };

    render(
      <VisualApprovalArtifactCard
        request={desktopRequest}
        desktopViewData={viewData}
        browserViewData={null}
        onResolve={async () => {}}
        isLoading={false}
      />,
    );

    expect(screen.getByText('toolApproval.visualApprovalOsHighlightUnavailable')).toBeInTheDocument();
    overlaySurfaceMock.degraded = false;
  });
});
