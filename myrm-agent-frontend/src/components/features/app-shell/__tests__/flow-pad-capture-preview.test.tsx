/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CapturePreview } from '../FlowPadModalParts';
import type { FlowPadCapture } from '@/store/useFlowPadStore';

function makeCapture(overrides: Partial<FlowPadCapture> = {}): FlowPadCapture {
  return {
    screenshot: 'ZmFrZQ==',
    windowTitle: 'Editor',
    extractedText: 'hello',
    timestamp: 1,
    ...overrides,
  };
}

describe('CapturePreview screenshot alt text', () => {
  it('uses the window title when the capture has one', () => {
    render(
      <CapturePreview capture={makeCapture()} onImageClick={vi.fn()} onRemove={vi.fn()} collapseLabel="collapse" />,
    );

    expect(screen.getByAltText('Editor')).toBeInTheDocument();
  });

  it('falls back to the translated label when the window title is empty', () => {
    render(
      <CapturePreview
        capture={makeCapture({ windowTitle: '' })}
        onImageClick={vi.fn()}
        onRemove={vi.fn()}
        collapseLabel="collapse"
      />,
    );

    expect(screen.getByAltText('captureAlt')).toBeInTheDocument();
  });
});
