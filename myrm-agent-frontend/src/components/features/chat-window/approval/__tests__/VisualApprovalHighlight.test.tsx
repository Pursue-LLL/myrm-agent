'use client';

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import VisualApprovalHighlight from '@/components/features/chat-window/approval/VisualApprovalHighlight';
import type { VisualApprovalContext } from '@/lib/approval/visualApprovalContext';

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));

const visualContext: VisualApprovalContext = {
  base64: 'abc123',
  mimeType: 'image/jpeg',
  bbox: { x: 100, y: 200, width: 80, height: 32 },
  viewportWidth: 1920,
  viewportHeight: 1080,
  targetLabel: 'e1',
  highlightKind: 'ref',
};

describe('VisualApprovalHighlight', () => {
  it('renders screenshot and percentage-based bbox overlay', () => {
    render(<VisualApprovalHighlight visualContext={visualContext} />);

    expect(screen.getByTestId('visual-approval-highlight')).toBeInTheDocument();
    const bbox = screen.getByTestId('visual-approval-bbox');
    expect(bbox).toHaveStyle({
      left: `${(100 / 1920) * 100}%`,
      top: `${(200 / 1080) * 100}%`,
      width: `${(80 / 1920) * 100}%`,
      height: `${(32 / 1080) * 100}%`,
    });
  });
});
