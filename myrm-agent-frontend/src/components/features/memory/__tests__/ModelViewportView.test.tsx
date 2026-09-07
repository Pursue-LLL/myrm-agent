/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ModelViewportView from '@/components/features/memory/replay/ModelViewportView';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params && 'count' in params) return `${key}:${params.count}`;
  if (params && 'chars' in params) return `${key}:${params.chars}`;
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

describe('ModelViewportView', () => {
  it('returns null when promptPreview is empty', () => {
    const { container } = render(<ModelViewportView promptPreview="" />);
    expect(container.firstChild).toBeNull();
  });

  it('renders structured viewport cards with role badges and character counts', () => {
    const raw = `[system] Base developer prompt instructions
[user] Show me the system architecture
[assistant] Understood, loading details...
[tool] {"status": "ok", "latency": 12}`;

    render(<ModelViewportView promptPreview={raw} />);

    expect(screen.getByText('modelViewportTitle')).toBeInTheDocument();
    expect(screen.getByText('viewportSystemPrompt')).toBeInTheDocument();
    expect(screen.getByText('viewportUserTurns:1')).toBeInTheDocument();
    expect(screen.getByText('viewportToolCalls:1')).toBeInTheDocument();

    expect(screen.getByText('Base developer prompt instructions')).toBeInTheDocument();
    expect(screen.getByText('Show me the system architecture')).toBeInTheDocument();
    expect(screen.getByText('Understood, loading details...')).toBeInTheDocument();
    expect(screen.getByText('{"status": "ok", "latency": 12}')).toBeInTheDocument();
  });

  it('displays truncation notice when prompt was clipped by telemetry log', () => {
    const raw = `[system] Short prompt
[user] Hello
... [truncated 340 chars]`;

    render(<ModelViewportView promptPreview={raw} />);
    expect(screen.getByText('viewportTruncatedNotice:340')).toBeInTheDocument();
  });

  it('handles copy button click gracefully', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    const raw = `[user] What is event sourcing?`;
    render(<ModelViewportView promptPreview={raw} />);

    const copyBtn = screen.getByTitle('copyRawViewport');
    expect(copyBtn).toBeInTheDocument();

    fireEvent.click(copyBtn);
    expect(writeTextMock).toHaveBeenCalledWith(raw);
  });
});
