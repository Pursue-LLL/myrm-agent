import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { IncrementalStreamingMarkdownRenderer } from '../IncrementalStreamingMarkdownRenderer';

describe('IncrementalStreamingMarkdownRenderer', () => {
  beforeEach(() => {
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback: FrameRequestCallback) => {
      // 模拟立即或在下一个周期触发 raf
      return window.setTimeout(() => callback(performance.now()), 16);
    });

    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation((id: number) => {
      clearTimeout(id);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders completed markdown with frozen blocks and without streaming cursor', () => {
    const markdown = '# Main Heading\n\nFirst paragraph content.\n\n```python\nprint("hello")\n```';
    render(<IncrementalStreamingMarkdownRenderer content={markdown} isStreaming={false} />);

    expect(screen.getByText('Main Heading')).toBeInTheDocument();
    expect(screen.getByText('First paragraph content.')).toBeInTheDocument();
    expect(screen.getByText('python')).toBeInTheDocument();
    expect(screen.queryByTestId('streaming-pulse-cursor')).toBeNull();
  });

  it('renders active tail block and streaming pulse cursor when streaming is active', () => {
    const markdown = 'Paragraph one completed.\n\nStreaming tail in progress...';
    render(<IncrementalStreamingMarkdownRenderer content={markdown} isStreaming={true} />);

    expect(screen.getByText('Paragraph one completed.')).toBeInTheDocument();
    expect(screen.getByTestId('active-tail-block')).toBeInTheDocument();
    expect(screen.getByTestId('streaming-pulse-cursor')).toBeInTheDocument();
  });

  it('renders performance monitoring HUD when showFpsHud is true', () => {
    const markdown = 'Some streaming content';
    render(
      <IncrementalStreamingMarkdownRenderer
        content={markdown}
        isStreaming={true}
        showFpsHud={true}
      />,
    );

    expect(screen.getByTestId('stream-performance-hud')).toBeInTheDocument();
    expect(screen.getByText(/FPS/)).toBeInTheDocument();
    expect(screen.getByText(/tokens\/s/)).toBeInTheDocument();
  });

  it('renders blockquotes, lists, and tables correctly', () => {
    const complexContent = '> A notable quotation\n\n- Bullet point one\n- Bullet point two\n\n| Col A | Col B |\n|---|---|\n| 1 | 2 |';
    render(<IncrementalStreamingMarkdownRenderer content={complexContent} isStreaming={false} />);

    expect(screen.getByText('A notable quotation')).toBeInTheDocument();
    expect(screen.getByText(/Bullet point one/)).toBeInTheDocument();
    expect(screen.getByText(/Col A/)).toBeInTheDocument();
  });
});
