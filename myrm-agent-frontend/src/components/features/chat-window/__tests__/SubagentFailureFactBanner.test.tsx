'use client';

/**
 * [INPUT]: SubagentFailureFactBanner.tsx 与 mock 失败事实数据
 * [OUTPUT]: 验证子智能体脱敏结构化失败事实、单行安全诊断 Header 复制与自愈建议交互
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/__tests__/SubagentFailureFactBanner.test.tsx
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  SubagentFailureFactBanner,
  StructuredFailureFactItem,
} from '../SubagentFailureFactBanner';

const mockFact: StructuredFailureFactItem = {
  product: 'codex-worker-01',
  stage: 'turn',
  category: 'contextWindowExceeded',
  httpStatus: 400,
  exitCode: 1,
  signal: 'none',
  sanitizedMessage: 'Model context window limit exceeded (128000 tokens). [PATH_REDACTED]/runner.py',
  remediation: 'compact_and_resume',
  safeDiagnosticHeader:
    'Product subagent failure (product: codex-worker-01; stage: turn; category: contextWindowExceeded; HTTP status: 400; exit code: 1; signal: none)',
  byteSize: 320,
  timestamp: 1720000000,
  metadata: {
    worker_id: 'wrk_999',
    trace_path: '[PATH_REDACTED]/trace.json',
  },
};

describe('SubagentFailureFactBanner', () => {
  it('renders top banner metadata with product, stage, category, and privacy scrubbed badges', () => {
    render(<SubagentFailureFactBanner chatId="chat_session_facts_01" fact={mockFact} />);

    expect(screen.getByTestId('subagent-failure-fact-banner')).toBeInTheDocument();
    expect(screen.getByTestId('fact-product-badge')).toHaveTextContent('codex-worker-01');
    expect(screen.getByTestId('fact-stage-badge')).toHaveTextContent('stage:turn');
    expect(screen.getByTestId('fact-category-badge')).toHaveTextContent('contextWindowExceeded');
    expect(screen.getByTestId('fact-privacy-badge')).toHaveTextContent('Privacy Scrubbed');
    expect(screen.getByTestId('fact-bytes-badge')).toHaveTextContent('320 / 4096 B');
  });

  it('renders single-line diagnostic header and handles copy action', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(<SubagentFailureFactBanner chatId="chat_session_facts_02" fact={mockFact} />);

    const headerElement = screen.getByTestId('safe-diagnostic-header');
    expect(headerElement).toHaveTextContent(mockFact.safeDiagnosticHeader);

    const copyBtn = screen.getByTestId('copy-diagnostic-header-btn');
    fireEvent.click(copyBtn);

    expect(writeTextMock).toHaveBeenCalledWith(mockFact.safeDiagnosticHeader);
    await waitFor(() => {
      expect(screen.getByText('Copied')).toBeInTheDocument();
    });
  });

  it('renders remediation guidance card and fires onApplyRemediation', () => {
    const handleApply = vi.fn();

    render(
      <SubagentFailureFactBanner
        chatId="chat_session_facts_03"
        fact={mockFact}
        onApplyRemediation={handleApply}
      />
    );

    expect(screen.getByTestId('remediation-guidance-card')).toBeInTheDocument();
    expect(screen.getByText('Recommended Self-Healing: Compact Context & Resume')).toBeInTheDocument();

    const applyBtn = screen.getByTestId('apply-remediation-btn');
    fireEvent.click(applyBtn);

    expect(handleApply).toHaveBeenCalledWith('compact_and_resume', mockFact);
  });

  it('toggles scrubbed failure trace details and metadata', () => {
    render(<SubagentFailureFactBanner chatId="chat_session_facts_04" fact={mockFact} />);

    expect(screen.queryByTestId('expanded-fact-details')).not.toBeInTheDocument();

    const toggleBtn = screen.getByTestId('toggle-fact-details-btn');
    fireEvent.click(toggleBtn);

    expect(screen.getByTestId('expanded-fact-details')).toBeInTheDocument();
    expect(screen.getByText(/Model context window limit exceeded/)).toBeInTheDocument();
    expect(screen.getByText(/trace_path/)).toBeInTheDocument();
  });

  it('fires onDismiss callback when close button is clicked', () => {
    const handleDismiss = vi.fn();

    render(
      <SubagentFailureFactBanner
        chatId="chat_session_facts_05"
        fact={mockFact}
        onDismiss={handleDismiss}
      />
    );

    const dismissBtn = screen.getByTestId('dismiss-fact-btn');
    fireEvent.click(dismissBtn);

    expect(handleDismiss).toHaveBeenCalled();
  });
});
