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

  it('maps screen-space desktop bbox into sent-image space for overlay percentages', () => {
    render(
      <VisualApprovalHighlight
        visualContext={{
          ...visualContext,
          bbox: { x: 500, y: 300, width: 40, height: 30 },
          viewportWidth: 1280,
          viewportHeight: 800,
          screenWidth: 1440,
          screenHeight: 900,
        }}
      />,
    );

    const bbox = screen.getByTestId('visual-approval-bbox');
    const expectedX = (500 * (1280 / 1440)) / 1280 * 100;
    const expectedY = (300 * (800 / 900)) / 800 * 100;
    expect(bbox).toHaveStyle({
      left: `${expectedX}%`,
      top: `${expectedY}%`,
    });
  });
});
